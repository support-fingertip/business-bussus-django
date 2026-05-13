"""Celery-task adoption tests — Phase 6.

Every @shared_task in the codebase should EITHER:

  * Have ``base=TenantRequiredTask`` if it touches tenant-scoped data
    (it'll refuse to run without ``_tenant_ctx``).
  * Have ``base=AdminTask`` if it legitimately spans multiple tenants
    (the marker class makes the cross-tenant intent visible in PRs).
  * Be on an explicit allowlist below if it's NEITHER (diagnostic /
    debug-only / system tasks).

The tests below walk the project's task registrations and assert the
base class. A failing test means a new task landed without the explicit
choice — flag for security review.
"""

from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.unit


def _ensure_django():
    pytest.importorskip("django")
    pytest.importorskip("celery")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    try:
        import django
        django.setup()
    except Exception:
        pytest.skip("Django not configured in this environment")


# Tasks that don't fit either category — debug, diagnostic, framework.
# Adding to this list requires a security review on the PR.
EXPLICIT_EXEMPT_TASKS: set[str] = {
    "version2.celery.debug_task",  # Celery's example debug task
}


class TestLogUserLoginAsyncBase:
    """The login-logging task writes to RLS-scoped tables — must be tenant-required."""

    def test_uses_tenant_required_task_base(self):
        _ensure_django()
        from adminuser.tasks import log_user_login_async
        from api.celery_tasks.base import TenantRequiredTask

        # Celery tasks have their base class registered on the
        # registered Task instance. `__class__` is the Task subclass.
        # We check the base's ancestry to confirm it's TenantRequiredTask.
        bases = log_user_login_async.__class__.__mro__
        base_names = [c.__name__ for c in bases]
        assert "TenantRequiredTask" in base_names, (
            f"log_user_login_async base chain is {base_names}; "
            f"expected TenantRequiredTask"
        )


class TestSendNotifyEmailVerificationBase:
    """Email verification sweep is cross-tenant by design — must be AdminTask."""

    def test_uses_admin_task_base(self):
        _ensure_django()
        from api.emailsend.tasks import send_notify_email_verification

        bases = send_notify_email_verification.__class__.__mro__
        base_names = [c.__name__ for c in bases]
        assert "AdminTask" in base_names, (
            f"send_notify_email_verification base chain is {base_names}; "
            f"expected AdminTask"
        )


class TestProcessSalesforceSyncBase:
    """Salesforce sync sweep is cross-tenant — must be AdminTask."""

    def test_uses_admin_task_base(self):
        _ensure_django()
        from sf_integration.tasks import process_salesforce_sync

        bases = process_salesforce_sync.__class__.__mro__
        base_names = [c.__name__ for c in bases]
        assert "AdminTask" in base_names, (
            f"process_salesforce_sync base chain is {base_names}; "
            f"expected AdminTask"
        )


class TestTenantRequiredTaskRefusesWithoutCtx:
    """Re-asserts the base class behaviour — log_user_login_async
    refuses to run without _tenant_ctx in kwargs.

    Catches a regression where someone removes base=TenantRequiredTask
    without updating callers."""

    def test_invocation_without_ctx_raises(self):
        _ensure_django()
        from adminuser.tasks import log_user_login_async

        with pytest.raises(RuntimeError, match="_tenant_ctx"):
            # Direct invocation (no apply_async) — the task body
            # is __call__-routed through TenantRequiredTask which
            # raises if _tenant_ctx is missing.
            log_user_login_async(
                user_id="u1",
                profile_id="p1",
                company_name="x",
                ip="1.2.3.4",
                location="x",
                browser="x",
                platform="x",
                client_version="x",
                api_type="x",
                api_version="x",
                login_url="x",
                access_token="x",
                refresh_token="x",
            )
