"""Phase 4.B wave 3 — INSERT cutover via the dynamic-object gateway.

Wave 3 adds:

  * ``api.ORM.dynamic.dynamic_table.insert_unchecked`` — INSERT with
    identifier validation but WITHOUT metadata-registry membership
    enforcement. Used when callers stamp system columns
    (``created_by_id``, ``created_date``, etc.) that aren't always
    in the field registry. Mirrors the wave-2
    ``update_unchecked`` primitive.
  * ``api.ORM.sqlFunctions.createSQLFunction._execute_insert`` — the
    new dispatch chokepoint at the main INSERT SQL site in
    ``post_data_sql`` (~line 1100, the ``INSERT ... RETURNING *``
    path). Routes between a raw-cursor path (byte-identical to
    pre-wave-3) and a gateway-backed path behind
    ``USE_DYNAMIC_GATEWAY``.

These tests cover the dispatch wiring and the new gateway primitive.
Behavioural parity (both paths producing identical inserted-row
shapes against a real schema) belongs in the staging soak — see
``docs/PHASE4_B_WAVE3_OPERATOR_NOTES.md``.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

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


# ---------------------------------------------------------------------------
# insert_unchecked — input validation
# ---------------------------------------------------------------------------


class TestInsertUncheckedValidation:
    """insert_unchecked still validates identifiers; only the
    metadata-registry membership check is skipped."""

    def test_rejects_empty_payload(self):
        _ensure_django()
        from api.ORM.dynamic import dynamic_table
        with pytest.raises(ValueError, match="non-empty payload"):
            dynamic_table.insert_unchecked("tenant_alpha", "leads", {})

    def test_rejects_unsafe_object_name(self):
        _ensure_django()
        from api.ORM.dynamic import dynamic_table
        from api.ORM.dynamic.identifier_validator import InvalidIdentifierError
        with pytest.raises((InvalidIdentifierError, ValueError)):
            dynamic_table.insert_unchecked(
                "tenant_alpha",
                "leads; DROP TABLE users",
                {"name": "Acme"},
            )

    def test_rejects_unsafe_field_name(self):
        _ensure_django()
        from api.ORM.dynamic import dynamic_table
        from api.ORM.dynamic.identifier_validator import InvalidIdentifierError
        with pytest.raises((InvalidIdentifierError, ValueError)):
            dynamic_table.insert_unchecked(
                "tenant_alpha",
                "leads",
                {"name; DROP TABLE x": "evil"},
            )

    def test_rejects_empty_schema(self):
        _ensure_django()
        from api.ORM.dynamic import dynamic_table
        with pytest.raises(PermissionError, match="empty schema"):
            dynamic_table.insert_unchecked("", "leads", {"name": "x"})


# ---------------------------------------------------------------------------
# _execute_insert — dispatch wiring
# ---------------------------------------------------------------------------


class TestExecuteInsertDispatch:
    def test_raw_path_when_flag_off(self, monkeypatch):
        _ensure_django()
        from api.ORM.sqlFunctions import createSQLFunction as mod

        captured = {}

        def fake_raw(cursor, table_name, cleaned_item):
            captured["impl"] = "raw"
            captured["table"] = table_name
            captured["item"] = dict(cleaned_item)
            return {"id": "lead_001", "name": "Acme"}

        def fake_orm(schema, table_name, cleaned_item):
            captured["impl"] = "orm"
            return {"id": "should_not_run"}

        monkeypatch.setattr(mod, "_execute_insert_raw", fake_raw)
        monkeypatch.setattr(mod, "_execute_insert_orm", fake_orm)
        monkeypatch.delenv("USE_DYNAMIC_GATEWAY", raising=False)

        result = mod._execute_insert(
            cursor=MagicMock(),
            schema="tenant_alpha",
            table_name="leads",
            cleaned_item={"name": "Acme", "phone": "555-0100"},
        )
        assert captured["impl"] == "raw"
        assert captured["table"] == "leads"
        assert captured["item"] == {"name": "Acme", "phone": "555-0100"}
        assert result == {"id": "lead_001", "name": "Acme"}

    def test_orm_path_when_flag_on(self, monkeypatch):
        _ensure_django()
        from api.ORM.sqlFunctions import createSQLFunction as mod

        captured = {}

        def fake_raw(*args, **kwargs):
            captured["impl"] = "raw"
            return {"id": "should_not_run"}

        def fake_orm(schema, table_name, cleaned_item):
            captured["impl"] = "orm"
            captured["schema"] = schema
            captured["table"] = table_name
            captured["item"] = dict(cleaned_item)
            return {"id": "lead_002", "name": "Acme"}

        monkeypatch.setattr(mod, "_execute_insert_raw", fake_raw)
        monkeypatch.setattr(mod, "_execute_insert_orm", fake_orm)
        monkeypatch.setenv("USE_DYNAMIC_GATEWAY", "1")

        result = mod._execute_insert(
            cursor=MagicMock(),
            schema="tenant_alpha",
            table_name="leads",
            cleaned_item={"name": "Acme"},
        )
        assert captured["impl"] == "orm"
        assert captured["schema"] == "tenant_alpha"
        assert captured["table"] == "leads"
        assert captured["item"] == {"name": "Acme"}
        assert result == {"id": "lead_002", "name": "Acme"}


class TestExecuteInsertRaw:
    """The raw helper composes safe SQL via sql.Identifier and forwards
    it on the caller's cursor — no new transaction is opened. Returns
    the inserted row as a dict via RETURNING *."""

    def test_emits_safe_sql_via_identifier(self):
        _ensure_django()
        from psycopg2 import sql as _sql
        from api.ORM.sqlFunctions.createSQLFunction import _execute_insert_raw

        cursor = MagicMock()
        cursor.description = [("id",), ("name",), ("phone",)]
        cursor.fetchone.return_value = ("lead_001", "Acme", "555-0100")

        row = _execute_insert_raw(
            cursor=cursor,
            table_name="leads",
            cleaned_item={"name": "Acme", "phone": "555-0100"},
        )
        assert row == {"id": "lead_001", "name": "Acme", "phone": "555-0100"}
        cursor.execute.assert_called_once()
        composed_query, params = cursor.execute.call_args.args
        # Must be a psycopg2.sql composable, never a plain string.
        assert isinstance(composed_query, _sql.Composed)
        assert params == ["Acme", "555-0100"]


class TestExecuteInsertOrmRoutesToGateway:
    """The ORM helper delegates to dynamic_table.insert_unchecked."""

    def test_calls_insert_unchecked_with_args(self, monkeypatch):
        _ensure_django()
        from api.ORM.sqlFunctions import createSQLFunction as mod
        from api.ORM.dynamic import dynamic_table

        captured = {}

        def fake_unchecked(schema, table_name, payload):
            captured["schema"] = schema
            captured["table"] = table_name
            captured["payload"] = dict(payload)
            return {"id": "lead_003", "name": "Acme"}

        monkeypatch.setattr(dynamic_table, "insert_unchecked", fake_unchecked)

        row = mod._execute_insert_orm(
            schema="tenant_alpha",
            table_name="leads",
            cleaned_item={"name": "Acme"},
        )

        assert row == {"id": "lead_003", "name": "Acme"}
        assert captured == {
            "schema": "tenant_alpha",
            "table": "leads",
            "payload": {"name": "Acme"},
        }
