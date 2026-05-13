"""Cached information_schema-backed column allow-list — Phase 8.A5.

Why this exists
---------------

``api/BL/computed_fields.py`` was flagged CRITICAL in the security
audit for f-string SQL interpolation of table/column identifiers
gated behind a character-class whitelist (``[A-Za-z0-9_+\\-*/%(),.\\s]+``)
that permits parentheses, commas, and arithmetic operators. The audit
notes this is "sufficient to inject subqueries" via payloads like
``id) UNION SELECT password FROM users --``.

The fix is two-layered:

  1. Replace f-string identifier interpolation with
     :class:`psycopg2.sql.Identifier`. (Done in the calling module —
     see ``_matching_parents_via_formula_inline``.)
  2. Validate identifiers against the **authoritative** column list
     pulled from Postgres ``information_schema.columns`` — not against
     a self-defined whitelist that could disagree with reality.

This module owns step 2. The cache uses an in-process dict keyed on
``(schema, table)`` plus a TTL; DDL paths (object/field create/drop)
should call :func:`invalidate` to keep the cache fresh.

Performance
-----------

The lookup is O(N) on the number of columns in the table, which is
small (<100 for any normal CRM object). One round-trip on first
access; subsequent calls are dict lookups. Memory cost is negligible.

The TTL fallback (default 300s) is belt-and-suspenders for the
case where a caller forgets to invalidate after DDL. In practice
DDL paths should call :func:`invalidate` so the cache is always
authoritative.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

from django.db import connection

logger = logging.getLogger(__name__)


# Cache: { (schema, table): (columns_set, fetched_at_unix_ts) }
_cache: dict[tuple[str, str], tuple[frozenset[str], float]] = {}
_cache_lock = threading.RLock()


# Default TTL — 5 minutes. DDL invalidation is the primary
# freshness mechanism; this just bounds staleness if invalidate()
# is forgotten.
DEFAULT_TTL_SECONDS = 300


class InvalidIdentifierError(ValueError):
    """Raised when a column / table identifier fails the allow-list check."""


def get_allowed_columns(schema: str, table: str, *, ttl: int = DEFAULT_TTL_SECONDS) -> frozenset[str]:
    """Return the canonical column set for ``schema.table``.

    The set is authoritative: it's pulled from
    ``information_schema.columns``. An identifier the caller wants
    to interpolate must be a member of this set; otherwise the
    caller raises :class:`InvalidIdentifierError`.

    Raises
    ------
    InvalidIdentifierError
        If ``schema`` or ``table`` themselves don't pass the
        identifier check (alnum + underscore, ≤63 chars per Postgres'
        `NAMEDATALEN`).
    """
    _assert_identifier(schema, "schema")
    _assert_identifier(table, "table")

    key = (schema, table)
    now = time.time()

    with _cache_lock:
        entry = _cache.get(key)
        if entry is not None:
            columns, fetched_at = entry
            if now - fetched_at < ttl:
                return columns

    # Cache miss / expired — round-trip to information_schema.
    try:
        with connection.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = %s AND table_name = %s",
                [schema, table],
            )
            rows = cur.fetchall()
    except Exception:
        # Log + return empty set so callers reject every identifier.
        # Better to fail-closed than to fall back to a stale or
        # permissive list.
        logger.exception(
            "get_allowed_columns: information_schema query failed",
            extra={"schema": schema, "table": table},
        )
        return frozenset()

    columns = frozenset(row[0] for row in rows)
    with _cache_lock:
        _cache[key] = (columns, now)
    return columns


def invalidate(schema: str, table: Optional[str] = None) -> None:
    """Invalidate the cache for ``(schema, table)`` or for an entire schema.

    Call from every DDL path:
      * After ``CREATE TABLE`` / ``DROP TABLE``
      * After ``ALTER TABLE ADD COLUMN`` / ``DROP COLUMN``
      * From ``ObjectManager.create_object`` / ``add_field`` / ``drop_field``
      * From migrations that alter per-tenant schemas

    Passing ``table=None`` invalidates every entry under the schema —
    useful after a schema-wide rebuild.
    """
    with _cache_lock:
        if table is None:
            stale = [k for k in _cache if k[0] == schema]
            for k in stale:
                del _cache[k]
        else:
            _cache.pop((schema, table), None)


def invalidate_all() -> None:
    """Clear the entire cache. Useful in tests and after global ops."""
    with _cache_lock:
        _cache.clear()


def assert_column(schema: str, table: str, column: str) -> str:
    """Raise :class:`InvalidIdentifierError` if ``column`` isn't on the table.

    Returns the column name unchanged when valid. Use in callers
    that want to build a :class:`psycopg2.sql.Identifier(column)`
    after confirming the column actually exists.
    """
    _assert_identifier(column, "column")
    allowed = get_allowed_columns(schema, table)
    if not allowed:
        raise InvalidIdentifierError(
            f"No column metadata found for {schema}.{table}; refusing "
            f"to validate {column!r}."
        )
    if column not in allowed:
        raise InvalidIdentifierError(
            f"Column {column!r} not found on {schema}.{table}."
        )
    return column


# ---------------------------------------------------------------------
# Operator whitelist
# ---------------------------------------------------------------------
#
# Used by computed_fields.py wherever an operator string is
# interpolated into SQL. The dict keys are the comparison operators
# we accept; the values are the SQL fragments they map to.
# Operators that take no right-hand side ("IS NULL" / "IS NOT NULL")
# are flagged so callers know not to bind a parameter.

ALLOWED_COMPARISON_OPERATORS: dict[str, dict] = {
    "=":         {"sql": "=",            "binds_rhs": True},
    "!=":        {"sql": "!=",           "binds_rhs": True},
    "<>":        {"sql": "<>",           "binds_rhs": True},
    "<":         {"sql": "<",            "binds_rhs": True},
    ">":         {"sql": ">",            "binds_rhs": True},
    "<=":        {"sql": "<=",           "binds_rhs": True},
    ">=":        {"sql": ">=",           "binds_rhs": True},
    "IS NULL":   {"sql": "IS NULL",      "binds_rhs": False},
    "IS NOT NULL": {"sql": "IS NOT NULL", "binds_rhs": False},
}


class InvalidOperatorError(ValueError):
    """Raised when an operator string isn't on the allow-list."""


def assert_operator(op: str) -> dict:
    """Validate that ``op`` is on the comparison-operator allow-list.

    Returns the matching dict (with ``sql`` and ``binds_rhs`` keys).
    Use the returned ``sql`` value to interpolate into the query
    (it's a fixed string, not user-controlled, so it's safe to
    pass to ``psycopg2.sql.SQL``).
    """
    if op not in ALLOWED_COMPARISON_OPERATORS:
        raise InvalidOperatorError(
            f"Operator {op!r} is not on the allow-list "
            f"({sorted(ALLOWED_COMPARISON_OPERATORS)})."
        )
    return ALLOWED_COMPARISON_OPERATORS[op]


# Same shape, for aggregate functions (SUM, COUNT, AVG, MIN, MAX).
ALLOWED_AGGREGATES: frozenset[str] = frozenset(
    {"SUM", "COUNT", "AVG", "MIN", "MAX"}
)


class InvalidAggregateError(ValueError):
    """Raised when an aggregate function name isn't on the allow-list."""


def assert_aggregate(agg: str) -> str:
    """Validate that ``agg`` is a known aggregate function."""
    upper = (agg or "").upper()
    if upper not in ALLOWED_AGGREGATES:
        raise InvalidAggregateError(
            f"Aggregate {agg!r} is not on the allow-list ({sorted(ALLOWED_AGGREGATES)})."
        )
    return upper


# ---------------------------------------------------------------------
# Identifier shape check
# ---------------------------------------------------------------------

import re as _re

# Postgres identifiers: start with letter/underscore, then alnum/underscore,
# up to 63 chars (NAMEDATALEN-1 by default). We disallow quoted identifiers
# entirely — every column we deal with from the metadata layer is unquoted.
_IDENT_RE = _re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")


def _assert_identifier(ident: str, kind: str) -> None:
    """Raise if ``ident`` doesn't look like a safe Postgres identifier.

    Catches injection attempts that include semicolons, quotes,
    whitespace, comments, or anything else that would let the
    attacker break out of the identifier slot in a query.
    """
    if not isinstance(ident, str) or not ident:
        raise InvalidIdentifierError(f"Empty {kind} identifier.")
    if not _IDENT_RE.match(ident):
        raise InvalidIdentifierError(
            f"Invalid {kind} identifier: {ident!r}. Must be "
            f"[A-Za-z_][A-Za-z0-9_]{{0,62}}."
        )
