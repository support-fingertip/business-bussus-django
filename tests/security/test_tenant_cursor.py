"""Tests for api.db.tenant_cursor — Phase 5 raw-SQL guardrail.

The tenant_cursor helper is the only sanctioned way to execute raw
SQL in tenant-scoped code paths. These tests verify the three
failure modes:

  1. Missing TenantContext → TenantContextMissing
  2. Search-path doesn't include the tenant schema → TenantContextMismatch
  3. Happy path → yields a cursor

Tests use ``pytest.importorskip`` for django so they skip cleanly in
stripped environments.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
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


@pytest.fixture
def fake_ctx():
    """A minimal TenantContext stub — no DB roundtrips."""
    _ensure_django()
    from api.security.schema_authority import TenantContext
    return TenantContext(
        org_id="org_test",
        schema="tenant_test",
        profile_id="profile_test",
    )


class TestTenantContextMissing:
    """The helper refuses to yield a cursor without a TenantContext."""

    def test_none_ctx_raises(self):
        _ensure_django()
        from api.db.tenant_cursor import tenant_cursor, TenantContextMissing
        with pytest.raises(TenantContextMissing) as exc:
            with tenant_cursor(None):
                pass
        assert "TenantContext" in str(exc.value)

    def test_ctx_with_empty_schema_raises(self):
        _ensure_django()
        from api.db.tenant_cursor import tenant_cursor, TenantContextMissing
        # Use a SimpleNamespace because TenantContext is frozen and
        # may not allow empty schema; this simulates a misuse case.
        ctx = SimpleNamespace(schema=None, org_id="org_x", profile_id=None)
        with pytest.raises(TenantContextMissing):
            with tenant_cursor(ctx):
                pass


class TestTenantContextMismatch:
    """If the connection's search_path doesn't include ctx.schema, raise."""

    def test_search_path_mismatch_raises(self, fake_ctx):
        _ensure_django()
        from api.db.tenant_cursor import tenant_cursor, TenantContextMismatch

        fake_cursor = MagicMock()
        fake_cursor.fetchone.return_value = ('"$user", public',)  # no tenant
        fake_cm = MagicMock()
        fake_cm.__enter__ = MagicMock(return_value=fake_cursor)
        fake_cm.__exit__ = MagicMock(return_value=False)

        with patch("api.db.tenant_cursor.connection") as fake_conn:
            fake_conn.cursor.return_value = fake_cm
            with pytest.raises(TenantContextMismatch):
                with tenant_cursor(fake_ctx) as cur:
                    cur.execute("SELECT 1")

    def test_search_path_contains_schema_yields(self, fake_ctx):
        _ensure_django()
        from api.db.tenant_cursor import tenant_cursor

        fake_cursor = MagicMock()
        # search_path includes the tenant schema → mismatch check passes
        fake_cursor.fetchone.return_value = (f'"{fake_ctx.schema}", public',)
        fake_cm = MagicMock()
        fake_cm.__enter__ = MagicMock(return_value=fake_cursor)
        fake_cm.__exit__ = MagicMock(return_value=False)

        with patch("api.db.tenant_cursor.connection") as fake_conn:
            fake_conn.cursor.return_value = fake_cm
            with tenant_cursor(fake_ctx) as cur:
                cur.execute("SELECT 1")

            # Verify the SHOW search_path probe ran first, then the
            # caller's query. (Two execute() calls total.)
            assert fake_cursor.execute.call_count >= 2
            first_call = fake_cursor.execute.call_args_list[0][0][0]
            assert "search_path" in first_call.lower()
