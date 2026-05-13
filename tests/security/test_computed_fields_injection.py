"""SQL-injection regression tests for api.BL.computed_fields — Phase 8.A5.

The audit graded the f-string SQL in this module CRITICAL. The fix
in claude/sec-phase8-sql-injection-fix replaces f-string identifier
interpolation with :func:`psycopg2.sql.Identifier` AND validates every
column / operator against an authoritative allow-list pulled from
``information_schema.columns``.

These tests pin the fix in place. Every payload below is from the
classic SQL-injection corpus (sqlmap / OWASP). All of them MUST be
rejected at parse time, BEFORE any SQL is sent to the database.

The contract under test
-----------------------

A malicious value reaching ``_matching_parents_via_formula_inline``
through any of its arguments (``formula_field``, ``parent_table``,
``op_sql``, identifiers inside ``expr``) must produce ``None`` — the
push-down planner's signal to fall back to the Python evaluator.
Returning ``None`` is the SAFE fallback because:

  * No SQL has been emitted yet (the check runs upstream of cursor.execute)
  * The caller falls back to the Python formula evaluator
  * The query result the user sees is correct even though slower
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


def _fake_cursor(rows):
    """Build a context-manager-shaped mock that yields a cursor whose
    fetchall returns ``rows``."""
    fake = MagicMock()
    fake.fetchall.return_value = rows
    fake.fetchone.return_value = rows[0] if rows else None
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=fake)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


@pytest.fixture(autouse=True)
def _isolate_caches():
    _ensure_django()
    from api.BL.computed_fields_columns import invalidate_all
    invalidate_all()
    yield
    invalidate_all()


# -----------------------------------------------------------------------
# Classic payload corpus
# -----------------------------------------------------------------------
#
# These are pulled from sqlmap's payload database + OWASP's SQLi cheat
# sheet, narrowed to the payloads that target the slots
# `_matching_parents_via_formula_inline` interpolates: parent_table,
# expression, operator, and identifiers within the expression.

# Payloads injected as column / table identifiers.
IDENTIFIER_INJECTIONS = [
    "id) UNION SELECT password FROM users --",
    "id; DROP TABLE users",
    "id'--",
    "id\" OR \"1\"=\"1",
    "id') OR ('1'='1",
    "id/**/UNION/**/SELECT/**/password",
    "id) AND 1=0 UNION SELECT current_database() --",
    "id) AND SLEEP(5) --",
    "id);WAITFOR DELAY '0:0:5'--",
    "id) AND ASCII(SUBSTRING(password,1,1))>64 --",
    "id\x00OR\x001=1",            # null-byte
    "id\nUNION\nSELECT password",  # newline
]

# Payloads injected as operators.
OPERATOR_INJECTIONS = [
    "= OR 1=1",
    "= UNION SELECT password FROM users --",
    "=; DROP TABLE users; --",
    "= OR EXISTS(SELECT * FROM users) --",
    "=' OR '1'='1",
    "REGEXP",        # accepted SQL operator, but not on our allow-list
    "ILIKE",         # same
    "BETWEEN",       # same
    "",
    "  =  ",
]

# Payloads injected as table names.
TABLE_INJECTIONS = [
    "users; DROP TABLE leads; --",
    "users WHERE 1=1 UNION SELECT password",
    "(SELECT password FROM users)",
    "users--",
    "users/*",
    "users.email FROM users JOIN ",
]


class TestIdentifierAllowListBlocksInjection:
    """The information_schema-backed assert_column rejects every payload
    that doesn't shape-match a Postgres identifier OR that isn't on the
    column list for the (schema, table). Neither check requires the
    payload to round-trip the database."""

    @pytest.mark.parametrize("payload", IDENTIFIER_INJECTIONS)
    def test_identifier_payload_rejected(self, payload):
        from api.BL.computed_fields_columns import (
            InvalidIdentifierError,
            assert_column,
        )
        with patch("api.BL.computed_fields_columns.connection") as fake_conn:
            # No matter what the DB would say, the shape check catches
            # every payload above before any query runs.
            with pytest.raises(InvalidIdentifierError):
                assert_column("tenant_alpha", "leads", payload)
            # And the DB was NEVER asked.
            fake_conn.cursor.assert_not_called()


class TestOperatorAllowListBlocksInjection:
    @pytest.mark.parametrize("payload", OPERATOR_INJECTIONS)
    def test_operator_payload_rejected(self, payload):
        from api.BL.computed_fields_columns import (
            InvalidOperatorError,
            assert_operator,
        )
        with pytest.raises(InvalidOperatorError):
            assert_operator(payload)


class TestTableNameAllowList:
    """Table names go through the same _assert_identifier check as column
    names. assert_column's first action is to validate the table shape;
    a malicious table name raises before any query runs."""

    @pytest.mark.parametrize("payload", TABLE_INJECTIONS)
    def test_table_payload_rejected(self, payload):
        from api.BL.computed_fields_columns import (
            InvalidIdentifierError,
            get_allowed_columns,
        )
        with patch("api.BL.computed_fields_columns.connection") as fake_conn:
            with pytest.raises(InvalidIdentifierError):
                get_allowed_columns("tenant_alpha", payload)
            fake_conn.cursor.assert_not_called()


class TestFormulaInlinePushDownRejectsInjection:
    """End-to-end check on the actual push-down planner. For every
    classic injection payload, _matching_parents_via_formula_inline
    must return None (the safe fallback). It MUST NOT execute the
    payload against the database."""

    @pytest.mark.parametrize("payload", [
        "id) UNION SELECT password FROM users --",
        "id;DROP TABLE users",
        "id) OR 1=1 --",
    ])
    def test_malicious_parent_table_returns_none(self, payload):
        from api.BL.computed_fields import _matching_parents_via_formula_inline

        result = _matching_parents_via_formula_inline(
            formula_field="grand_total",
            parent_table=payload,
            op_sql="=",
            value=100,
            schema="tenant_alpha",
        )
        assert result is None

    @pytest.mark.parametrize("payload", [
        "= OR 1=1",
        "; DROP TABLE users; --",
        "REGEXP",
    ])
    def test_malicious_op_sql_returns_none(self, payload):
        from api.BL.computed_fields import _matching_parents_via_formula_inline

        # Even if we mock the schema-lookup to return a "valid" formula,
        # the operator check rejects before any SQL execution.
        with patch("api.BL.computed_fields.connection") as fake_conn:
            fake_conn.cursor.return_value = _fake_cursor([("price * qty",)])
            result = _matching_parents_via_formula_inline(
                formula_field="line_total",
                parent_table="invoice_items",
                op_sql=payload,
                value=0,
                schema="tenant_alpha",
            )
            assert result is None

    def test_malicious_schema_returns_none(self):
        from api.BL.computed_fields import _matching_parents_via_formula_inline

        # Schema name injection — the assert_identifier check in
        # get_allowed_columns raises, which the caller catches and
        # returns None.
        result = _matching_parents_via_formula_inline(
            formula_field="grand_total",
            parent_table="invoices",
            op_sql="=",
            value=100,
            schema="tenant_alpha; DROP DATABASE",
        )
        assert result is None
