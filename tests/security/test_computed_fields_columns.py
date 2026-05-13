"""Tests for api.BL.computed_fields_columns — Phase 8.A5.

Pure unit tests with mocked information_schema lookups. The module's
own logic (identifier shape check, cache, TTL, operator whitelist) is
exercised here; the SQL injection regression test lives in
``test_computed_fields_injection.py``.
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
    fake = MagicMock()
    fake.fetchall.return_value = [(r,) for r in rows]
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=fake)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


@pytest.fixture(autouse=True)
def _isolate_cache():
    """Each test gets a clean cache."""
    _ensure_django()
    from api.BL.computed_fields_columns import invalidate_all
    invalidate_all()
    yield
    invalidate_all()


class TestIdentifierShape:
    """_assert_identifier rejects every plausible injection attempt."""

    @pytest.mark.parametrize("bad", [
        "",
        "1abc",                  # starts with digit
        "a; DROP TABLE users",   # semicolon
        "a' OR '1'='1",          # quote
        'a" OR "1"="1',          # double quote
        "a/*comment*/",          # comment markers
        "a--comment",            # SQL line comment
        "a b",                   # whitespace
        "a\nb",                  # newline
        "a)",                    # paren
        "a(b)",                  # function-call shape
        "A" * 64,                # too long (NAMEDATALEN-1 is 63)
        "  ",                    # whitespace only
        ".",
        "..",
    ])
    def test_bad_shapes_rejected(self, bad):
        from api.BL.computed_fields_columns import (
            InvalidIdentifierError,
            _assert_identifier,
        )
        with pytest.raises(InvalidIdentifierError):
            _assert_identifier(bad, "test")

    @pytest.mark.parametrize("good", [
        "id",
        "user_id",
        "_id",
        "Account",
        "ABC_123",
        "x",
        "A" * 63,                # exactly NAMEDATALEN-1
    ])
    def test_good_shapes_accepted(self, good):
        from api.BL.computed_fields_columns import _assert_identifier
        # Should not raise
        _assert_identifier(good, "test")


class TestOperatorWhitelist:
    def test_known_operators_accepted(self):
        from api.BL.computed_fields_columns import assert_operator
        for op in ("=", "!=", "<", ">", "<=", ">=", "IS NULL", "IS NOT NULL"):
            spec = assert_operator(op)
            assert "sql" in spec and "binds_rhs" in spec

    @pytest.mark.parametrize("bad", [
        "UNION SELECT",
        "; DROP TABLE",
        "OR 1=1",
        "= OR 1=1",
        "==",                    # equality variant — caller maps to "=" before reaching us
        "  =  ",                 # whitespace-padded
        "",
        "REGEXP",                # known SQL operator, but not on the allow-list
        "LIKE",                  # ditto — we don't push LIKE today
    ])
    def test_unknown_operator_rejected(self, bad):
        from api.BL.computed_fields_columns import (
            InvalidOperatorError,
            assert_operator,
        )
        with pytest.raises(InvalidOperatorError):
            assert_operator(bad)

    def test_is_null_doesnt_bind_rhs(self):
        from api.BL.computed_fields_columns import assert_operator
        assert assert_operator("IS NULL")["binds_rhs"] is False
        assert assert_operator("IS NOT NULL")["binds_rhs"] is False

    def test_equality_binds_rhs(self):
        from api.BL.computed_fields_columns import assert_operator
        assert assert_operator("=")["binds_rhs"] is True


class TestColumnAllowList:
    def test_assert_column_passes_for_known(self):
        from api.BL.computed_fields_columns import assert_column

        with patch("api.BL.computed_fields_columns.connection") as fake_conn:
            fake_conn.cursor.return_value = _fake_cursor(["id", "name", "email"])
            assert assert_column("tenant_alpha", "users", "email") == "email"

    def test_assert_column_rejects_unknown(self):
        from api.BL.computed_fields_columns import (
            InvalidIdentifierError,
            assert_column,
        )
        with patch("api.BL.computed_fields_columns.connection") as fake_conn:
            fake_conn.cursor.return_value = _fake_cursor(["id", "name"])
            with pytest.raises(InvalidIdentifierError):
                assert_column("tenant_alpha", "users", "password")

    def test_assert_column_rejects_bad_shape_before_query(self):
        """Identifier shape check runs BEFORE the DB lookup, so a malicious
        column name like ``id) UNION SELECT…`` is rejected without
        information_schema being consulted at all."""
        from api.BL.computed_fields_columns import (
            InvalidIdentifierError,
            assert_column,
        )
        with patch("api.BL.computed_fields_columns.connection") as fake_conn:
            with pytest.raises(InvalidIdentifierError):
                assert_column(
                    "tenant_alpha",
                    "users",
                    "id) UNION SELECT password FROM users --",
                )
            fake_conn.cursor.assert_not_called()

    def test_assert_column_rejects_when_table_unknown(self):
        from api.BL.computed_fields_columns import (
            InvalidIdentifierError,
            assert_column,
        )
        # Empty result → assert_column refuses every column
        with patch("api.BL.computed_fields_columns.connection") as fake_conn:
            fake_conn.cursor.return_value = _fake_cursor([])
            with pytest.raises(InvalidIdentifierError):
                assert_column("tenant_alpha", "nonexistent", "id")


class TestCache:
    def test_repeat_lookups_hit_cache(self):
        from api.BL.computed_fields_columns import get_allowed_columns

        with patch("api.BL.computed_fields_columns.connection") as fake_conn:
            fake_conn.cursor.return_value = _fake_cursor(["id", "name"])
            first = get_allowed_columns("tenant_alpha", "users")
            second = get_allowed_columns("tenant_alpha", "users")
            assert first == second == frozenset(["id", "name"])
            # The DB was hit only once across the two calls.
            assert fake_conn.cursor.call_count == 1

    def test_invalidate_forces_refresh(self):
        from api.BL.computed_fields_columns import (
            get_allowed_columns,
            invalidate,
        )

        with patch("api.BL.computed_fields_columns.connection") as fake_conn:
            fake_conn.cursor.return_value = _fake_cursor(["id"])
            get_allowed_columns("tenant_alpha", "users")
            invalidate("tenant_alpha", "users")
            get_allowed_columns("tenant_alpha", "users")
            assert fake_conn.cursor.call_count == 2

    def test_invalidate_all_clears_every_entry(self):
        from api.BL.computed_fields_columns import (
            get_allowed_columns,
            invalidate_all,
        )
        with patch("api.BL.computed_fields_columns.connection") as fake_conn:
            fake_conn.cursor.return_value = _fake_cursor(["id"])
            get_allowed_columns("tenant_a", "users")
            get_allowed_columns("tenant_b", "leads")
            invalidate_all()
            get_allowed_columns("tenant_a", "users")
            get_allowed_columns("tenant_b", "leads")
            # 4 calls — 2 initial + 2 after invalidation
            assert fake_conn.cursor.call_count == 4

    def test_query_failure_fails_closed(self):
        """If information_schema is unreachable, we return an empty set
        so callers reject every identifier. Fail-closed is the right
        default for a security check."""
        from api.BL.computed_fields_columns import get_allowed_columns

        with patch("api.BL.computed_fields_columns.connection") as fake_conn:
            fake_conn.cursor.side_effect = RuntimeError("DB blip")
            result = get_allowed_columns("tenant_alpha", "users")
            assert result == frozenset()
