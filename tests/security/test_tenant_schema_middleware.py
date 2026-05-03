"""Unit tests for ``TenantSchemaMiddleware``.

Verify the per-request search_path is set ONLY when ``request.tenant_schema``
is populated, and is reset on the response.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.unit


def _fake_request(tenant_schema=None, path="/v2/api/leads"):
    req = SimpleNamespace()
    req.tenant_schema = tenant_schema
    req.path = path
    return req


class TestTenantSchemaMiddleware:
    def test_skips_when_no_tenant(self, monkeypatch):
        from api.security.tenant_schema_middleware import TenantSchemaMiddleware
        from api.security import tenant_schema_middleware as tsm

        # Replace `connection` with a mock that fails noisily if used.
        mock_conn = MagicMock()
        monkeypatch.setattr(tsm, "connection", mock_conn)

        mw = TenantSchemaMiddleware(get_response=lambda r: r)
        req = _fake_request(tenant_schema=None)
        result = mw.process_view(req, lambda r: None, [], {})
        assert result is None
        mock_conn.cursor.assert_not_called()

    def test_sets_search_path_when_tenant_pinned(self, monkeypatch):
        from api.security.tenant_schema_middleware import TenantSchemaMiddleware
        from api.security import tenant_schema_middleware as tsm

        executed = []
        mock_cursor = MagicMock()
        mock_cursor.execute = lambda sql, params=None: executed.append((sql, params))
        mock_cursor.__enter__ = lambda self: mock_cursor
        mock_cursor.__exit__ = lambda *a: None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        monkeypatch.setattr(tsm, "connection", mock_conn)

        mw = TenantSchemaMiddleware(get_response=lambda r: r)
        req = _fake_request(tenant_schema="tenant_alpha")
        mw.process_view(req, lambda r: None, [], {})
        assert executed == [
            ("SET search_path TO %s, public", ["tenant_alpha"]),
        ]
        assert req._tenant_search_path_set is True

    def test_rejects_invalid_schema_identifier(self, monkeypatch, caplog):
        from api.security.tenant_schema_middleware import TenantSchemaMiddleware
        from api.security import tenant_schema_middleware as tsm

        mock_conn = MagicMock()
        monkeypatch.setattr(tsm, "connection", mock_conn)

        mw = TenantSchemaMiddleware(get_response=lambda r: r)
        req = _fake_request(tenant_schema="evil; DROP TABLE users")
        with caplog.at_level("ERROR", logger="api.security.tenant_schema_middleware"):
            mw.process_view(req, lambda r: None, [], {})
        assert any("invalid schema name" in r.message.lower() for r in caplog.records)
        mock_conn.cursor.assert_not_called()

    def test_resets_on_response_when_set(self, monkeypatch):
        from api.security.tenant_schema_middleware import TenantSchemaMiddleware
        from api.security import tenant_schema_middleware as tsm

        executed = []
        mock_cursor = MagicMock()
        mock_cursor.execute = lambda sql, params=None: executed.append((sql, params))
        mock_cursor.__enter__ = lambda self: mock_cursor
        mock_cursor.__exit__ = lambda *a: None
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        monkeypatch.setattr(tsm, "connection", mock_conn)

        mw = TenantSchemaMiddleware(get_response=lambda r: r)
        req = _fake_request(tenant_schema="tenant_alpha")
        req._tenant_search_path_set = True
        out = mw.process_response(req, "ok")
        assert out == "ok"
        assert ("SET search_path TO public", None) in executed

    def test_no_reset_when_never_set(self, monkeypatch):
        from api.security.tenant_schema_middleware import TenantSchemaMiddleware
        from api.security import tenant_schema_middleware as tsm

        mock_conn = MagicMock()
        monkeypatch.setattr(tsm, "connection", mock_conn)

        mw = TenantSchemaMiddleware(get_response=lambda r: r)
        req = _fake_request(tenant_schema="tenant_alpha")
        # Never set _tenant_search_path_set.
        out = mw.process_response(req, "ok")
        assert out == "ok"
        mock_conn.cursor.assert_not_called()
