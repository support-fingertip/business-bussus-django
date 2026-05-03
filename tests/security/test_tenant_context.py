"""Unit tests for ``api.security.tenant_context``.

Covers the three contracts background-task callers rely on:
  - ``with_tenant_schema`` issues the right SET search_path and resets
    on exit (and on exception).
  - Re-entrant nesting restores the parent schema, not ``public``.
  - ``tenant_schema_required`` extracts the schema from kwarg /
    positional arg / Celery `self`-bound first arg.
  - The decorator raises a clear error if the schema is missing.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.unit


# --- Helpers --------------------------------------------------------------

def _patch_connection(monkeypatch):
    """Replace ``api.security.tenant_context.connection`` with a mock cursor."""
    from api.security import tenant_context as tc

    executed: list[tuple[str, list]] = []

    class FakeCursor:
        def execute(self, sql, params=None):
            executed.append((sql, params))
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return None

    fake_conn = MagicMock()
    fake_conn.cursor.return_value = FakeCursor()
    monkeypatch.setattr(tc, "connection", fake_conn)
    return executed


# --- with_tenant_schema ---------------------------------------------------

class TestWithTenantSchema:
    def test_sets_and_resets_search_path(self, monkeypatch):
        from api.security.tenant_context import with_tenant_schema

        executed = _patch_connection(monkeypatch)
        with with_tenant_schema("tenant_alpha"):
            pass

        assert executed == [
            ("SET search_path TO %s, public", ["tenant_alpha"]),
            ("SET search_path TO public", None),
        ]

    def test_resets_on_exception(self, monkeypatch):
        from api.security.tenant_context import with_tenant_schema

        executed = _patch_connection(monkeypatch)
        with pytest.raises(RuntimeError, match="boom"):
            with with_tenant_schema("tenant_alpha"):
                raise RuntimeError("boom")

        # Reset still happened.
        assert executed[-1] == ("SET search_path TO public", None)

    def test_nested_restores_parent_not_public(self, monkeypatch):
        from api.security.tenant_context import with_tenant_schema, get_current_schema

        executed = _patch_connection(monkeypatch)
        with with_tenant_schema("tenant_alpha"):
            assert get_current_schema() == "tenant_alpha"
            with with_tenant_schema("tenant_beta"):
                assert get_current_schema() == "tenant_beta"
            # Inner exited — should restore alpha, not public
            assert get_current_schema() == "tenant_alpha"

        # Trace: enter alpha, enter beta, exit beta -> back to alpha,
        # exit alpha -> back to public.
        sqls = [s for s, _ in executed]
        assert "SET search_path TO public" in sqls
        # Last operation should be the reset to public.
        assert executed[-1] == ("SET search_path TO public", None)
        # Second-to-last (after exiting beta) should restore alpha.
        assert ("SET search_path TO %s, public", ["tenant_alpha"]) in executed

    def test_rejects_invalid_schema_identifier(self, monkeypatch):
        from api.security.tenant_context import with_tenant_schema

        _patch_connection(monkeypatch)
        with pytest.raises(ValueError):
            with with_tenant_schema("evil; DROP TABLE users"):
                pass

    def test_user_id_set_on_correlation(self, monkeypatch):
        from api.security.tenant_context import with_tenant_schema
        from api.security.correlation import get_user_id, get_tenant_id

        _patch_connection(monkeypatch)
        with with_tenant_schema("tenant_alpha", user_id="usr_001"):
            assert get_tenant_id() == "tenant_alpha"
            assert get_user_id() == "usr_001"


# --- tenant_schema_required decorator -------------------------------------

class TestTenantSchemaRequired:
    def test_extracts_from_named_kwarg(self, monkeypatch):
        from api.security.tenant_context import tenant_schema_required

        executed = _patch_connection(monkeypatch)

        @tenant_schema_required()
        def task(tenant_schema, payload):
            return payload

        assert task(tenant_schema="tenant_alpha", payload={"x": 1}) == {"x": 1}
        assert any(
            sql == "SET search_path TO %s, public" and params == ["tenant_alpha"]
            for sql, params in executed
        )

    def test_extracts_from_positional_arg(self, monkeypatch):
        from api.security.tenant_context import tenant_schema_required

        executed = _patch_connection(monkeypatch)

        @tenant_schema_required()
        def task(tenant_schema, payload):
            return payload

        assert task("tenant_alpha", {"x": 1}) == {"x": 1}
        assert any(
            params == ["tenant_alpha"]
            for sql, params in executed
            if sql == "SET search_path TO %s, public"
        )

    def test_celery_bound_self_handled(self, monkeypatch):
        from api.security.tenant_context import tenant_schema_required

        _patch_connection(monkeypatch)

        @tenant_schema_required()
        def bound_task(self, tenant_schema, payload):
            return (self.name, tenant_schema, payload)

        # Simulate a Celery task self.
        class FakeTask:
            request = object()
            name = "fake.task"

        result = bound_task(FakeTask(), "tenant_alpha", {"x": 1})
        assert result == ("fake.task", "tenant_alpha", {"x": 1})

    def test_raises_when_schema_missing(self):
        from api.security.tenant_context import tenant_schema_required

        @tenant_schema_required()
        def task(tenant_schema, payload):
            return payload

        with pytest.raises(ValueError, match="requires a tenant schema"):
            task(tenant_schema=None, payload={"x": 1})

    def test_bare_decorator_no_parens_works(self, monkeypatch):
        from api.security.tenant_context import tenant_schema_required

        _patch_connection(monkeypatch)

        @tenant_schema_required
        def task(tenant_schema, payload):
            return payload

        assert task("tenant_alpha", {"x": 1}) == {"x": 1}
