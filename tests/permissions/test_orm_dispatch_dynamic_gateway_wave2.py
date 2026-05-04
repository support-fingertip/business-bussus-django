"""Phase 4.B wave 2 — UPDATE cutover via the dynamic-object gateway.

Wave 2 adds:

  * ``api.ORM.dynamic.dynamic_table.update_unchecked`` — UPDATE with
    identifier validation but WITHOUT metadata-registry membership
    enforcement. Used when callers stamp system columns
    (``last_modified_by_id`` etc.) that aren't always in the field
    registry.
  * ``api.ORM.sqlFunctions.updateSQLFunction._execute_update`` — the
    new dispatch chokepoint at the UPDATE SQL site in
    ``updateRawSQL``. Routes between a raw-cursor path (byte-identical
    to pre-wave-2) and a gateway-backed path behind
    ``USE_DYNAMIC_GATEWAY``.

These tests cover the dispatch wiring and the new gateway primitive.
Behavioural parity (both paths producing identical effects against a
real schema) belongs in the staging soak — see
``docs/PHASE4_B_WAVE2_OPERATOR_NOTES.md``.
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
# update_unchecked — input validation
# ---------------------------------------------------------------------------


class TestUpdateUncheckedValidation:
    """update_unchecked still validates identifiers; only the metadata-
    registry membership check is skipped."""

    def test_rejects_empty_patch(self):
        _ensure_django()
        from api.ORM.dynamic import dynamic_table
        with pytest.raises(ValueError, match="non-empty patch"):
            dynamic_table.update_unchecked(
                "tenant_alpha", "leads", record_id="lead_1", patch={},
            )

    def test_rejects_empty_record_id(self):
        _ensure_django()
        from api.ORM.dynamic import dynamic_table
        with pytest.raises(ValueError, match="record_id"):
            dynamic_table.update_unchecked(
                "tenant_alpha", "leads", record_id="", patch={"name": "x"},
            )

    def test_rejects_unsafe_object_name(self):
        _ensure_django()
        from api.ORM.dynamic import dynamic_table
        from api.ORM.dynamic.identifier_validator import InvalidIdentifierError
        with pytest.raises((InvalidIdentifierError, ValueError)):
            dynamic_table.update_unchecked(
                "tenant_alpha",
                "leads; DROP TABLE users",
                record_id="lead_1",
                patch={"name": "x"},
            )

    def test_rejects_unsafe_field_name(self):
        _ensure_django()
        from api.ORM.dynamic import dynamic_table
        from api.ORM.dynamic.identifier_validator import InvalidIdentifierError
        with pytest.raises((InvalidIdentifierError, ValueError)):
            dynamic_table.update_unchecked(
                "tenant_alpha",
                "leads",
                record_id="lead_1",
                patch={"name; DROP TABLE x": "evil"},
            )

    def test_rejects_empty_schema(self):
        _ensure_django()
        from api.ORM.dynamic import dynamic_table
        with pytest.raises(PermissionError, match="empty schema"):
            dynamic_table.update_unchecked(
                "", "leads", record_id="lead_1", patch={"name": "x"},
            )


# ---------------------------------------------------------------------------
# _execute_update — dispatch wiring
# ---------------------------------------------------------------------------


class TestExecuteUpdateDispatch:
    def test_raw_path_when_flag_off(self, monkeypatch):
        _ensure_django()
        from api.ORM.sqlFunctions import updateSQLFunction as mod

        captured = {}

        def fake_raw(cursor, table_name, record_id, update_fields):
            captured["impl"] = "raw"
            captured["table"] = table_name
            captured["record_id"] = record_id
            captured["fields"] = dict(update_fields)
            return 1

        def fake_orm(schema, table_name, record_id, update_fields):
            captured["impl"] = "orm"
            return 99

        monkeypatch.setattr(mod, "_execute_update_raw", fake_raw)
        monkeypatch.setattr(mod, "_execute_update_orm", fake_orm)
        monkeypatch.delenv("USE_DYNAMIC_GATEWAY", raising=False)

        result = mod._execute_update(
            cursor=MagicMock(),
            schema="tenant_alpha",
            table_name="leads",
            record_id="lead_1",
            update_fields={"name": "Acme", "phone": "555-0100"},
        )
        assert captured["impl"] == "raw"
        assert captured["table"] == "leads"
        assert captured["record_id"] == "lead_1"
        assert captured["fields"] == {"name": "Acme", "phone": "555-0100"}
        assert result == 1

    def test_orm_path_when_flag_on(self, monkeypatch):
        _ensure_django()
        from api.ORM.sqlFunctions import updateSQLFunction as mod

        captured = {}

        def fake_raw(*args, **kwargs):
            captured["impl"] = "raw"
            return -1

        def fake_orm(schema, table_name, record_id, update_fields):
            captured["impl"] = "orm"
            captured["schema"] = schema
            captured["table"] = table_name
            captured["record_id"] = record_id
            captured["fields"] = dict(update_fields)
            return 1

        monkeypatch.setattr(mod, "_execute_update_raw", fake_raw)
        monkeypatch.setattr(mod, "_execute_update_orm", fake_orm)
        monkeypatch.setenv("USE_DYNAMIC_GATEWAY", "1")

        result = mod._execute_update(
            cursor=MagicMock(),
            schema="tenant_alpha",
            table_name="leads",
            record_id="lead_1",
            update_fields={"name": "Acme"},
        )
        assert captured["impl"] == "orm"
        assert captured["schema"] == "tenant_alpha"
        assert captured["table"] == "leads"
        assert captured["record_id"] == "lead_1"
        assert captured["fields"] == {"name": "Acme"}
        assert result == 1


class TestExecuteUpdateRaw:
    """The raw helper composes safe SQL via sql.Identifier and forwards
    it on the caller's cursor — no new transaction is opened."""

    def test_emits_safe_sql_via_identifier(self):
        _ensure_django()
        from psycopg2 import sql as _sql
        from api.ORM.sqlFunctions.updateSQLFunction import _execute_update_raw

        cursor = MagicMock()
        cursor.rowcount = 1

        rc = _execute_update_raw(
            cursor=cursor,
            table_name="leads",
            record_id="lead_1",
            update_fields={"name": "Acme", "phone": "555-0100"},
        )
        assert rc == 1
        cursor.execute.assert_called_once()
        composed_query, params = cursor.execute.call_args.args
        # Must be a psycopg2.sql composable, never a plain string.
        assert isinstance(composed_query, _sql.Composed)
        assert params == ["Acme", "555-0100", "lead_1"]


class TestExecuteUpdateOrmRoutesToGateway:
    """The ORM helper delegates to dynamic_table.update_unchecked."""

    def test_calls_update_unchecked_with_args(self, monkeypatch):
        _ensure_django()
        from api.ORM.sqlFunctions import updateSQLFunction as mod
        from api.ORM.dynamic import dynamic_table

        captured = {}

        def fake_unchecked(schema, table_name, *, record_id, patch):
            captured["schema"] = schema
            captured["table"] = table_name
            captured["record_id"] = record_id
            captured["patch"] = dict(patch)
            return 1

        monkeypatch.setattr(dynamic_table, "update_unchecked", fake_unchecked)

        rc = mod._execute_update_orm(
            schema="tenant_alpha",
            table_name="leads",
            record_id="lead_1",
            update_fields={"name": "Acme"},
        )

        assert rc == 1
        assert captured == {
            "schema": "tenant_alpha",
            "table": "leads",
            "record_id": "lead_1",
            "patch": {"name": "Acme"},
        }
