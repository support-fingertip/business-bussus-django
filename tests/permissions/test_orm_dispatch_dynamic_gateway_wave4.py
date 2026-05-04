"""Phase 4.B wave 4 — SELECT cutover via the dynamic-object gateway.

Wave 4 adds:

  * ``api.ORM.dynamic.dynamic_table.select_raw`` — thin SELECT
    executor for pre-composed SQL. Unlike ``select()`` (which
    builds the SQL itself from a fields list + where dict),
    ``select_raw`` accepts a query string + params and just runs
    it. Used when SQL has already been built upstream — the
    canonical case is the ``getQueryBuilder.build_query`` path
    where PyPika has produced the final query string.
  * ``api.ORM.sqlFunctions.getQueryBuilder._execute_select`` — the
    new dispatch chokepoint at the SELECT execution site in
    ``fetch_data_raw_sql``. Routes between a raw-cursor path
    (byte-identical to pre-wave-4) and a gateway-backed path
    behind ``USE_DYNAMIC_GATEWAY``.

These tests cover the dispatch wiring, the new gateway primitive,
and the ``(columns, rows)`` shape contract on both paths so the
caller's column-type post-processing (JSON parsing, datetime tz
attachment) doesn't need to know which path it's on.
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
# select_raw — schema-pin enforcement
# ---------------------------------------------------------------------------


class TestSelectRawValidation:
    """select_raw still enforces schema-pin; SQL composition is the
    caller's responsibility (PyPika upstream)."""

    def test_rejects_empty_schema_string(self):
        _ensure_django()
        from api.ORM.dynamic import dynamic_table
        with pytest.raises(PermissionError, match="empty schema"):
            dynamic_table.select_raw("", "SELECT 1", [])

    def test_rejects_request_with_no_pinned_schema(self):
        _ensure_django()
        from types import SimpleNamespace
        from api.ORM.dynamic import dynamic_table
        with pytest.raises(PermissionError, match="pinned tenant schema"):
            dynamic_table.select_raw(SimpleNamespace(), "SELECT 1", [])

    def test_accepts_schema_string(self):
        """Smoke that the resolver path reads a string without raising —
        we don't actually execute (no DB), just ensure the resolution
        step succeeds before the cursor work would happen."""
        _ensure_django()
        from api.ORM.dynamic.dynamic_table import _resolve_schema
        assert _resolve_schema("tenant_alpha") == "tenant_alpha"


# ---------------------------------------------------------------------------
# _execute_select — dispatch wiring
# ---------------------------------------------------------------------------


class TestExecuteSelectDispatch:
    def test_raw_path_when_flag_off(self, monkeypatch):
        _ensure_django()
        from api.ORM.sqlFunctions import getQueryBuilder as mod

        captured = {}

        def fake_raw(schema, sql, params):
            captured["impl"] = "raw"
            captured["schema"] = schema
            captured["sql"] = sql
            captured["params"] = list(params)
            return (["id", "name"], [("a1", "Alpha")])

        def fake_orm(schema, sql, params):
            captured["impl"] = "orm"
            return ([], [])

        monkeypatch.setattr(mod, "_execute_select_raw", fake_raw)
        monkeypatch.setattr(mod, "_execute_select_orm", fake_orm)
        monkeypatch.delenv("USE_DYNAMIC_GATEWAY", raising=False)

        cols, rows = mod._execute_select("tenant_alpha", "SELECT 1", [42])
        assert captured["impl"] == "raw"
        assert captured["schema"] == "tenant_alpha"
        assert captured["sql"] == "SELECT 1"
        assert captured["params"] == [42]
        assert cols == ["id", "name"]
        assert rows == [("a1", "Alpha")]

    def test_orm_path_when_flag_on(self, monkeypatch):
        _ensure_django()
        from api.ORM.sqlFunctions import getQueryBuilder as mod

        captured = {}

        def fake_raw(*args):
            captured["impl"] = "raw"
            return ([], [])

        def fake_orm(schema, sql, params):
            captured["impl"] = "orm"
            captured["schema"] = schema
            captured["sql"] = sql
            captured["params"] = list(params)
            return (["id", "name"], [("b1", "Beta")])

        monkeypatch.setattr(mod, "_execute_select_raw", fake_raw)
        monkeypatch.setattr(mod, "_execute_select_orm", fake_orm)
        monkeypatch.setenv("USE_DYNAMIC_GATEWAY", "1")

        cols, rows = mod._execute_select("tenant_alpha", "SELECT 1", [])
        assert captured["impl"] == "orm"
        assert captured["schema"] == "tenant_alpha"
        assert captured["sql"] == "SELECT 1"
        assert captured["params"] == []
        assert cols == ["id", "name"]
        assert rows == [("b1", "Beta")]


# ---------------------------------------------------------------------------
# Shape parity: both paths must return (columns, rows) the same way
# ---------------------------------------------------------------------------


class TestExecuteSelectShapeParity:
    """The post-processing in fetch_data_raw_sql iterates ``rows`` by
    integer index against ``columns``. Both paths MUST return the same
    (columns: list[str], rows: list[tuple]) shape so the post-processor
    doesn't need to know which path ran."""

    def test_orm_path_unpacks_dicts_into_tuples(self, monkeypatch):
        _ensure_django()
        from api.ORM.sqlFunctions import getQueryBuilder as mod
        from api.ORM.dynamic import dynamic_table

        # Fake the gateway returning the list-of-dicts shape.
        monkeypatch.setattr(
            dynamic_table, "select_raw",
            lambda schema, sql, params: [
                {"id": "a1", "name": "Alpha", "phone": "555-0100"},
                {"id": "b1", "name": "Beta", "phone": None},
            ],
        )

        cols, rows = mod._execute_select_orm("tenant_alpha", "SELECT * FROM leads", [])
        assert cols == ["id", "name", "phone"]
        assert rows == [
            ("a1", "Alpha", "555-0100"),
            ("b1", "Beta", None),
        ]

    def test_orm_path_handles_empty_resultset(self, monkeypatch):
        _ensure_django()
        from api.ORM.sqlFunctions import getQueryBuilder as mod
        from api.ORM.dynamic import dynamic_table

        monkeypatch.setattr(
            dynamic_table, "select_raw",
            lambda schema, sql, params: [],
        )

        cols, rows = mod._execute_select_orm("tenant_alpha", "SELECT 1 WHERE FALSE", [])
        assert cols == []
        assert rows == []


# ---------------------------------------------------------------------------
# fetch_data_raw_sql post-processing parity (JSON / datetime handling)
# ---------------------------------------------------------------------------


class TestFetchDataRawSqlPostProcessingPath:
    """The JSON parsing + naive-datetime tz attachment in
    fetch_data_raw_sql must work identically regardless of whether
    _execute_select returned raw or ORM rows. We force the dispatcher
    to a known shape and assert the post-processing transforms it the
    same way."""

    def test_json_string_is_parsed_into_dict(self, monkeypatch):
        _ensure_django()
        from api.ORM.sqlFunctions import getQueryBuilder as mod

        monkeypatch.setattr(
            mod, "_execute_select",
            lambda schema, sql, params: (
                ["id", "config"],
                [("a1", '{"k": "v"}'), ("b1", "[1, 2, 3]"), ("c1", "plain")],
            ),
        )
        results = mod.fetch_data_raw_sql("SELECT 1", schema="tenant_alpha")
        assert results == [
            {"id": "a1", "config": {"k": "v"}},
            {"id": "b1", "config": [1, 2, 3]},
            {"id": "c1", "config": "plain"},
        ]

    def test_naive_datetime_gets_utc_tz(self, monkeypatch):
        _ensure_django()
        from datetime import datetime, timezone as dt_timezone
        from api.ORM.sqlFunctions import getQueryBuilder as mod

        naive = datetime(2026, 1, 1, 12, 0, 0)
        monkeypatch.setattr(
            mod, "_execute_select",
            lambda schema, sql, params: (
                ["id", "created_date"],
                [("a1", naive)],
            ),
        )
        results = mod.fetch_data_raw_sql("SELECT 1", schema="tenant_alpha")
        assert results[0]["created_date"].tzinfo == dt_timezone.utc

    def test_already_aware_datetime_passes_through(self, monkeypatch):
        _ensure_django()
        from datetime import datetime, timezone as dt_timezone
        from api.ORM.sqlFunctions import getQueryBuilder as mod

        aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=dt_timezone.utc)
        monkeypatch.setattr(
            mod, "_execute_select",
            lambda schema, sql, params: (
                ["id", "created_date"],
                [("a1", aware)],
            ),
        )
        results = mod.fetch_data_raw_sql("SELECT 1", schema="tenant_alpha")
        assert results[0]["created_date"] is aware
