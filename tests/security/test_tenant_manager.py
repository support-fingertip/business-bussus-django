"""Tests for the TenantManager.for_tenant entrypoint — Phase 5.

The manager:
  1. Refuses to return a queryset without a TenantContext.
  2. Refuses if the connection's search_path doesn't include ctx.schema.
  3. Returns a regular queryset when both checks pass.

These tests use mocks for the DB connection so they're pure unit
tests with no DB dependency.
"""

from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

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


def _ctx(schema="tenant_test"):
    _ensure_django()
    from api.security.schema_authority import TenantContext
    return TenantContext(org_id="org_x", schema=schema, profile_id=None)


def _fake_cursor(search_path_response):
    fake = MagicMock()
    fake.fetchone.return_value = (search_path_response,)
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=fake)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


class TestForTenantRequiresContext:
    def test_none_ctx_raises(self):
        _ensure_django()
        from api.tenant_models._base import TenantManager, TenantContextMissing
        # Use any registered tenant model that exposes TenantManager.
        from api.tenant_models import Profile

        with pytest.raises(TenantContextMissing):
            Profile.objects.for_tenant(None)


class TestForTenantSearchPathCheck:
    def test_mismatched_search_path_raises(self):
        _ensure_django()
        from api.tenant_models._base import TenantContextMismatch
        from api.tenant_models import Profile

        ctx = _ctx(schema="tenant_alpha")

        with patch("api.tenant_models._base.connection") as fake_conn:
            fake_conn.cursor.return_value = _fake_cursor('"$user", public')
            with pytest.raises(TenantContextMismatch):
                Profile.objects.for_tenant(ctx)

    def test_matching_search_path_returns_queryset(self):
        _ensure_django()
        from api.tenant_models import Profile

        ctx = _ctx(schema="tenant_alpha")

        with patch("api.tenant_models._base.connection") as fake_conn:
            fake_conn.cursor.return_value = _fake_cursor('"tenant_alpha", public')
            qs = Profile.objects.for_tenant(ctx)
            # We don't execute it (no test DB), just verify it returns
            # something with a queryset-shaped interface.
            assert hasattr(qs, "filter")
            assert hasattr(qs, "all")
