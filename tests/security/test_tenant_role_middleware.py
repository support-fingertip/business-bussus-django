"""Tests for Phase 4 part 1 — TenantSchemaMiddleware now SET LOCAL ROLE.

Verifies:
  * Happy path: middleware issues both SET LOCAL search_path AND SET LOCAL ROLE.
  * Tolerant mode (default): if SET LOCAL ROLE fails (un-provisioned tenant),
    fall back to search_path-only and log a WARNING.
  * Enforce mode (ENFORCE_TENANT_ROLE=1): if SET LOCAL ROLE fails, refuse with 503.
  * Invalid schema name: middleware refuses to issue either SET LOCAL.
  * process_response resets ROLE + search_path on the way out.
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


def _fake_request(schema="tenant_test"):
    """Build a request-shaped stub with the tenant pinned."""
    req = MagicMock()
    req.tenant_schema = schema
    req.path = "/test"
    return req


def _fake_cursor():
    """Return a context-manager-wrapped MagicMock cursor."""
    cur = MagicMock()
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cur)
    cm.__exit__ = MagicMock(return_value=False)
    return cur, cm


class TestHappyPath:
    def test_sets_search_path_and_role(self):
        _ensure_django()
        from api.security.tenant_schema_middleware import TenantSchemaMiddleware

        mw = TenantSchemaMiddleware(get_response=lambda r: r)
        cur, cm = _fake_cursor()
        req = _fake_request("tenant_alpha")

        with patch("api.security.tenant_schema_middleware.connection") as fake_conn:
            fake_conn.cursor.return_value = cm
            mw.process_view(req, view_func=lambda: None, view_args=(), view_kwargs={})

        # Two statements executed:
        # 1. SET LOCAL search_path TO tenant_alpha, public
        # 2. SET LOCAL ROLE tenant_tenant_alpha_role
        calls = [c.args[0] for c in cur.execute.call_args_list]
        assert any("search_path" in s.lower() for s in calls), \
            f"Expected SET LOCAL search_path; got {calls}"
        assert any("local role" in s.lower() for s in calls), \
            f"Expected SET LOCAL ROLE; got {calls}"

        # Markers set so process_response knows to reset
        assert getattr(req, "_tenant_search_path_set", False) is True
        assert getattr(req, "_tenant_role_set", False) is True


class TestTolerantModeOnRoleFailure:
    """Default rollout mode: missing tenant role logs WARN but request continues."""

    def test_role_failure_falls_back_to_search_path_only(self):
        _ensure_django()
        import api.security.tenant_schema_middleware as m
        from api.security.tenant_schema_middleware import TenantSchemaMiddleware

        # Force tolerant mode
        with patch.object(m, "ENFORCE_TENANT_ROLE", False):
            cur = MagicMock()
            # Make ONLY the SET LOCAL ROLE call fail; search_path succeeds.
            def execute_side(sql_str, *_args, **_kw):
                if "LOCAL ROLE" in str(sql_str).upper():
                    raise RuntimeError("role does not exist")
                return None
            cur.execute.side_effect = execute_side
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cur)
            cm.__exit__ = MagicMock(return_value=False)

            mw = TenantSchemaMiddleware(get_response=lambda r: r)
            req = _fake_request("tenant_unprovisioned")

            with patch("api.security.tenant_schema_middleware.connection") as fake_conn:
                fake_conn.cursor.return_value = cm
                result = mw.process_view(req, view_func=lambda: None, view_args=(), view_kwargs={})

            # Tolerant mode → no early Response; the view continues.
            assert result is None
            assert getattr(req, "_tenant_search_path_set", False) is True
            assert getattr(req, "_tenant_role_set", False) is False


class TestEnforceModeOnRoleFailure:
    """ENFORCE_TENANT_ROLE=1 → role failure is a 503."""

    def test_role_failure_returns_503(self):
        _ensure_django()
        import api.security.tenant_schema_middleware as m
        from api.security.tenant_schema_middleware import TenantSchemaMiddleware

        with patch.object(m, "ENFORCE_TENANT_ROLE", True):
            cur = MagicMock()
            def execute_side(sql_str, *_args, **_kw):
                if "LOCAL ROLE" in str(sql_str).upper():
                    raise RuntimeError("role does not exist")
                return None
            cur.execute.side_effect = execute_side
            cm = MagicMock()
            cm.__enter__ = MagicMock(return_value=cur)
            cm.__exit__ = MagicMock(return_value=False)

            mw = TenantSchemaMiddleware(get_response=lambda r: r)
            req = _fake_request("tenant_unprovisioned")

            with patch("api.security.tenant_schema_middleware.connection") as fake_conn:
                fake_conn.cursor.return_value = cm
                result = mw.process_view(req, view_func=lambda: None, view_args=(), view_kwargs={})

            # Enforce mode → middleware returns a 503 Response.
            assert result is not None
            assert getattr(result, "status_code", None) == 503


class TestSchemaValidation:
    def test_invalid_schema_name_skips_set(self):
        _ensure_django()
        from api.security.tenant_schema_middleware import TenantSchemaMiddleware

        mw = TenantSchemaMiddleware(get_response=lambda r: r)
        cur, cm = _fake_cursor()
        # Identifiers with `;` / spaces / quotes are rejected by validate_identifier.
        req = _fake_request("tenant; DROP TABLE users")

        with patch("api.security.tenant_schema_middleware.connection") as fake_conn:
            fake_conn.cursor.return_value = cm
            mw.process_view(req, view_func=lambda: None, view_args=(), view_kwargs={})

        # No statements executed — connection wasn't even touched.
        fake_conn.cursor.assert_not_called()
        assert getattr(req, "_tenant_search_path_set", False) is False
        assert getattr(req, "_tenant_role_set", False) is False


class TestProcessResponseResets:
    def test_resets_role_and_search_path_when_marker_set(self):
        _ensure_django()
        from api.security.tenant_schema_middleware import TenantSchemaMiddleware

        mw = TenantSchemaMiddleware(get_response=lambda r: r)
        cur, cm = _fake_cursor()
        req = _fake_request()
        req._tenant_role_set = True
        req._tenant_search_path_set = True

        with patch("api.security.tenant_schema_middleware.connection") as fake_conn:
            fake_conn.cursor.return_value = cm
            mw.process_response(req, MagicMock())

        statements = [c.args[0] for c in cur.execute.call_args_list]
        assert any("reset role" in s.lower() for s in statements), \
            f"Expected RESET ROLE in {statements}"
        assert any("search_path to public" in s.lower() for s in statements), \
            f"Expected SET search_path TO public in {statements}"

    def test_no_reset_when_no_marker(self):
        """If process_view never ran (no marker set), process_response
        leaves the connection alone."""
        _ensure_django()
        from api.security.tenant_schema_middleware import TenantSchemaMiddleware

        mw = TenantSchemaMiddleware(get_response=lambda r: r)
        req = _fake_request()
        # Don't set any markers.

        with patch("api.security.tenant_schema_middleware.connection") as fake_conn:
            mw.process_response(req, MagicMock())
            fake_conn.cursor.assert_not_called()
