"""Tenant-aware Celery task bases — Phase 6 foundation.

Background work is the #1 source of cross-tenant leaks in real-world
multi-tenant outages. A Celery task that runs without a tenant
context will, with current code, either (a) execute against the
``public`` schema and silently miss data, or (b) reuse a connection
from the pool that's still pinned to a different tenant.

This module gives every task a tenant-required default plus an
explicit opt-out for the (few) admin tasks that genuinely iterate
across tenants. Both options are documented and CI-enforceable so a
task can never accidentally land without an isolation story.

Two task bases
--------------

* :class:`TenantRequiredTask` — the default. Refuses to run unless
  the caller passes ``_tenant_ctx`` in kwargs. Wraps the task body in
  ``with_tenant_schema(ctx.schema)`` so ORM queries auto-scope.

* :class:`AdminTask` — explicit opt-out for cross-tenant work
  (nightly billing roll-up, fleet-wide migrations). Requires an
  obvious import + decorator combo so PR review notices when a new
  task uses it.

Usage — tenant-scoped task
--------------------------

    from celery import shared_task
    from api.celery_tasks.base import TenantRequiredTask

    @shared_task(base=TenantRequiredTask, bind=True)
    def send_due_email_campaigns(self, ctx, batch_size=50):
        # ctx is automatically injected by TenantRequiredTask.__call__
        # search_path is already pinned to ctx.schema for this task body.
        Campaign.objects.for_tenant(ctx).filter(status="due")[:batch_size]
        ...

    # Scheduling from a view:
    send_due_email_campaigns.apply_async(
        kwargs={"_tenant_ctx": request.tenant_ctx.to_dict()},
    )

Usage — cross-tenant admin task
-------------------------------

    from celery import shared_task
    from api.celery_tasks.base import AdminTask

    @shared_task(base=AdminTask, bind=True)
    def nightly_billing_rollup(self):
        for org in Organization.objects.iterator():
            with with_tenant_schema(org.database_schema) as _:
                # do tenant-scoped work here
                ...

Migration notes
---------------

Existing tasks decorated with bare ``@shared_task`` keep working —
they don't pick up the new base. Phase 6 ramps up by:

  1. (this commit) Add the bases. Document them. Tests exist.
  2. Convert known-tenant tasks (email campaigns, audit log writes,
     workflow steppers) to ``TenantRequiredTask`` one at a time.
  3. Audit the remaining tasks; those that genuinely cross tenants
     get ``AdminTask`` explicitly; everything else gets
     ``TenantRequiredTask``.
  4. Configure ``celery_app.Task = TenantRequiredTask`` as the
     global default, so a forgotten ``base=`` raises by default.
"""

from __future__ import annotations

import logging
from typing import Any

from celery import Task

logger = logging.getLogger(__name__)


class TenantRequiredTask(Task):
    """Base task — refuses to run without a TenantContext.

    Pulls ``_tenant_ctx`` from ``kwargs``, reconstructs the
    :class:`TenantContext`, wraps the task body in
    :func:`api.security.tenant_context.with_tenant_schema`, and
    injects the context as ``ctx=`` for the task body.
    """

    abstract = True

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        raw_ctx = kwargs.pop("_tenant_ctx", None)
        if not raw_ctx:
            raise RuntimeError(
                f"Task {self.name!r} requires the `_tenant_ctx` kwarg. "
                f"Schedule with `apply_async(kwargs={{'_tenant_ctx': ctx.to_dict()}})`. "
                f"If this task genuinely runs across tenants, use the "
                f"AdminTask base instead (and have a security review approve it)."
            )

        # Reconstruct the dataclass from the wire-friendly dict form.
        # Importing inside __call__ keeps this module importable
        # even in stripped environments where Django isn't configured.
        from api.security.schema_authority import TenantContext
        from api.security.tenant_context import with_tenant_schema

        if isinstance(raw_ctx, TenantContext):
            ctx = raw_ctx
        elif isinstance(raw_ctx, dict):
            ctx = TenantContext(
                org_id=raw_ctx["org_id"],
                schema=raw_ctx["schema"],
                profile_id=raw_ctx.get("profile_id"),
            )
        else:
            raise RuntimeError(
                f"Task {self.name!r}: _tenant_ctx must be a TenantContext or "
                f"a dict with keys (org_id, schema, profile_id); got "
                f"{type(raw_ctx).__name__}."
            )

        user_id = kwargs.pop("_tenant_user_id", None)

        with with_tenant_schema(ctx.schema, user_id=user_id):
            # The task body sees `ctx` as a positional argument injected
            # before its own args. Tasks declare `def run(self, ctx, ...)`.
            return self.run(ctx, *args, **kwargs)


class AdminTask(Task):
    """Base task for jobs that legitimately iterate across tenants.

    No automatic tenant pinning — the task body is responsible for
    opening a ``with_tenant_schema`` block for each tenant it touches.

    Use sparingly. Every new ``AdminTask`` must have:
      * a docstring justifying the cross-tenant scope
      * a security review on the PR
      * a non-trivial unit test exercising at least 2 tenants
    """

    abstract = True

    # The body MUST manage its own tenant context. We can't enforce
    # that at runtime cheaply, but documenting + grep-able marker
    # ("AdminTask") makes the choice visible in PRs.
    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        logger.info(
            "AdminTask %r running (cross-tenant by design)",
            self.name,
        )
        return super().__call__(*args, **kwargs)


def serialize_ctx(ctx: "Any") -> dict:
    """Wire-friendly dict form of a TenantContext for Celery payloads.

    Centralises the (org_id, schema, profile_id) shape so callers and
    ``TenantRequiredTask.__call__`` agree on the contract.
    """
    return {
        "org_id": getattr(ctx, "org_id", None),
        "schema": getattr(ctx, "schema", None),
        "profile_id": getattr(ctx, "profile_id", None),
    }
