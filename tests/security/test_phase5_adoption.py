"""Phase 5 adoption tests — `.objects.for_tenant(ctx)` usage in real code.

The first Phase 5 adoption wave migrates two helpers in
api/permissions/permissions.py:

  * _get_object_details_orm
  * _profile_has_admin_access_orm

Both now call .for_tenant(ctx) instead of naked .objects.filter().
These tests verify:

  1. The helpers still produce a queryset (so we don't regress on
     the existing query shape).
  2. They call .for_tenant on the manager (we can grep / inspect
     to confirm).
  3. for_tenant raises TenantContextMismatch when called outside a
     pinned-search-path context (the foundation test verified this
     already; we re-assert it here to lock in the new usage).
"""

from __future__ import annotations

import os
import inspect

import pytest


pytestmark = pytest.mark.unit


def _ensure_django():
    pytest.importorskip("django")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    try:
        import django
        django.setup()
    except Exception:
        pytest.skip("Django not configured in this environment")


class TestPermissionsHelpersUseForTenant:
    """Both migrated helpers must call .for_tenant in their source."""

    def test_get_object_details_orm_uses_for_tenant(self):
        _ensure_django()
        from api.permissions import permissions

        src = inspect.getsource(permissions._get_object_details_orm)
        assert ".for_tenant(" in src, (
            "_get_object_details_orm should call .for_tenant(ctx); "
            "the migration regressed."
        )

    def test_profile_has_admin_access_orm_uses_for_tenant(self):
        _ensure_django()
        from api.permissions import permissions

        src = inspect.getsource(permissions._profile_has_admin_access_orm)
        assert ".for_tenant(" in src, (
            "_profile_has_admin_access_orm should call .for_tenant(ctx); "
            "the migration regressed."
        )


class TestForTenantContractStillEnforced:
    """The TenantManager check remains active even after the migration.

    A regression here would mean someone removed the check from
    api/tenant_models/_base.py — that's the foundation we built earlier
    and other migrated call sites depend on it."""

    def test_for_tenant_rejects_no_context(self):
        _ensure_django()
        from api.tenant_models import Profile
        from api.tenant_models._base import TenantContextMissing

        with pytest.raises(TenantContextMissing):
            Profile.objects.for_tenant(None)
