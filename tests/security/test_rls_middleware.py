"""Tests for the RLS wiring in TenantSchemaMiddleware — Phase 4 part 2.

Phase 4 part 2 adds two things to the middleware:

  1. ``SET LOCAL app.current_org_id = <org>`` per request — this is
     the predicate the RLS policies read on every query.
  2. ``RESET app.current_org_id`` on the way out so a pooled
     connection doesn't carry the value into the next request.

These tests verify both. No live DB needed; we mock the cursor and
check the statements that get executed.

A separate integration test (``test_rls_policies_integration.py``)
runs against a real Postgres database when one is available.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

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


def _fake_request(schema="tenant_alpha", org_id="org_alpha"):
    req = MagicMock()
    req.tenant_schema = schema
    req.tenant_org_id = org_id
    req.path = "/test"
    return req


def _fake_cursor():
    cur = MagicMock()
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cur)
    cm.__exit__ = MagicMock(return_value=False)
    return cur, cm


class TestSetCurrentOrgId:
    def test_pinned_org_id_set_on_process_view(self):
        _ensure_django()
        from api.security.tenant_schema_middleware import TenantSchemaMiddleware

        mw = TenantSchemaMiddleware(get_response=lambda r: r)
        req = _fake_request(schema="tenant_alpha", org_id="org_alpha")
        cur, cm = _fake_cursor()

        with patch("api.security.tenant_schema_middleware.connection") as fake_conn:
            fake_conn.cursor.return_value = cm
            mw.process_view(req, view_func=lambda: None, view_args=(), view_kwargs={})

        statements = [str(c.args[0]) for c in cur.execute.call_args_list]
        params = [c.args[1] if len(c.args) > 1 else None for c in cur.execute.call_args_list]

        # Find the SET LOCAL app.current_org_id call
        org_id_calls = [
            (s, p) for s, p in zip(statements, params)
            if "app.current_org_id" in s.lower()
        ]
        assert org_id_calls, f"Expected SET LOCAL app.current_org_id; got {statements}"
        # Parameter must be the pinned org_id, NOT the schema name.
        assert org_id_calls[0][1] == ["org_alpha"]
        assert getattr(req, "_tenant_org_id_set", False) is True

    def test_falls_back_to_schema_when_org_id_missing(self):
        """If schema_authority forgot to set tenant_org_id (legacy code
        path), the middleware falls back to the schema name. RLS then
        returns 0 rows (schema name doesn't match any organization_id
        column) — fail-closed."""
        _ensure_django()
        from api.security.tenant_schema_middleware import TenantSchemaMiddleware

        mw = TenantSchemaMiddleware(get_response=lambda r: r)
        req = MagicMock()
        req.tenant_schema = "tenant_legacy"
        # Note: NO tenant_org_id attribute
        del req.tenant_org_id  # ensure getattr returns the default
        req.path = "/test"
        cur, cm = _fake_cursor()

        with patch("api.security.tenant_schema_middleware.connection") as fake_conn:
            fake_conn.cursor.return_value = cm
            mw.process_view(req, view_func=lambda: None, view_args=(), view_kwargs={})

        # The org_id passed to SET LOCAL must NOT be None — even the
        # fallback gives a value (the schema name) so RLS has something
        # to compare against.
        org_calls = [
            c for c in cur.execute.call_args_list
            if "app.current_org_id" in str(c.args[0]).lower()
        ]
        assert org_calls
        # Should have fallen back to the schema name
        assert org_calls[0].args[1] == ["tenant_legacy"]


class TestResetOnResponse:
    def test_resets_current_org_id_too(self):
        _ensure_django()
        from api.security.tenant_schema_middleware import TenantSchemaMiddleware

        mw = TenantSchemaMiddleware(get_response=lambda r: r)
        req = _fake_request()
        req._tenant_org_id_set = True
        req._tenant_search_path_set = True
        cur, cm = _fake_cursor()

        with patch("api.security.tenant_schema_middleware.connection") as fake_conn:
            fake_conn.cursor.return_value = cm
            mw.process_response(req, MagicMock())

        statements = [str(c.args[0]).lower() for c in cur.execute.call_args_list]
        assert any("reset app.current_org_id" in s for s in statements), \
            f"Expected RESET app.current_org_id; got {statements}"

    def test_no_reset_when_marker_absent(self):
        """If nothing was set on the request, don't issue any RESETs.
        Saves a connection round-trip for unauthenticated paths."""
        _ensure_django()
        from api.security.tenant_schema_middleware import TenantSchemaMiddleware

        mw = TenantSchemaMiddleware(get_response=lambda r: r)
        req = MagicMock()
        # No _tenant_* markers
        for attr in ("_tenant_org_id_set", "_tenant_role_set",
                     "_tenant_search_path_set"):
            if hasattr(req, attr):
                delattr(req, attr)

        with patch("api.security.tenant_schema_middleware.connection") as fake_conn:
            mw.process_response(req, MagicMock())
            fake_conn.cursor.assert_not_called()
