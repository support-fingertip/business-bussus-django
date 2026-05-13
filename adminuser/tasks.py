"""Celery tasks for adminuser app.

Phase 6 adoption
----------------

``log_user_login_async`` writes to ``public.session_log`` and
``public.user_login_history`` — both shared tables that Phase 4 part 2
locked down with Row-Level Security keyed on ``organization_id``. A
task that runs without ``app.current_org_id`` set will either:

  * Hit ``WITH CHECK`` and refuse the write, OR
  * Insert a row with NULL ``organization_id`` (allowed during the
    rollout window, but every NULL is a follow-up triage item).

Either way: this task MUST run under a tenant context. Migrating
from bare ``@shared_task`` to ``TenantRequiredTask`` makes that a
hard runtime contract — forgetting ``_tenant_ctx`` raises before
any DB write, instead of silently producing a broken row.
"""

from celery import shared_task
from django.db import transaction
from django.utils.timezone import now

from api.celery_tasks.base import TenantRequiredTask
from api.models import SessionLog, UserLoginHistory, User
import logging

logger = logging.getLogger(__name__)


@shared_task(base=TenantRequiredTask, bind=True, max_retries=3)
def log_user_login_async(
    self,
    ctx,
    user_id,
    profile_id,
    company_name,
    ip,
    location,
    browser,
    platform,
    client_version,
    api_type,
    api_version,
    login_url,
    access_token,
    refresh_token,
):
    """Log a user login to session_log + user_login_history.

    Phase 6 signature change: first positional arg is now ``ctx`` —
    the :class:`TenantContext` injected by :class:`TenantRequiredTask`.
    Callers MUST schedule with ``_tenant_ctx`` in kwargs::

        from api.celery_tasks.base import serialize_ctx
        log_user_login_async.apply_async(
            kwargs={
                '_tenant_ctx': serialize_ctx(request.tenant_ctx),
                'user_id': user_id,
                'profile_id': profile_id,
                ...
            },
        )

    Forgetting ``_tenant_ctx`` raises ``RuntimeError`` from
    ``TenantRequiredTask.__call__`` — visible in worker logs.
    """
    try:
        with transaction.atomic():
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                logger.error(f"User {user_id} not found for login logging")
                return {"status": "failed", "error": "User not found"}

            # organization_id pulled from the injected TenantContext so
            # the row matches its owning tenant. RLS WITH CHECK accepts
            # this; without it, the INSERT would fail once FORCE ROW
            # LEVEL SECURITY is flipped on (Phase 4 part 3).
            SessionLog.objects.create(
                user=user,
                organization_id=ctx.org_id,
                profile_id=profile_id,
                company_name=company_name,
                login_time=now(),
                access_token=str(access_token),
                refresh_token=str(refresh_token),
                ip_address=ip,
            )

            UserLoginHistory.objects.create(
                user=user,
                organization_id=ctx.org_id,
                ip_address=ip,
                location=location,
                login_type='success',
                status='Success',
                browser=browser,
                platform=platform,
                application='Web',
                client_version=client_version or 'Unknown',
                api_type=api_type or 'Unknown',
                api_version=api_version or '1.0',
                login_url=login_url,
            )

        logger.info(
            "Successfully logged login for user %s (org=%s)",
            user_id, ctx.org_id,
        )
        return {"status": "success", "user_id": user_id}

    except Exception as e:
        logger.error(f"Error logging user login for {user_id}: {str(e)}")
        try:
            self.retry(countdown=60, exc=e)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for logging user {user_id} login")
            return {"status": "failed", "error": str(e)}
