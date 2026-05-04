"""Dynamic-table CRUD gateway — the single chokepoint for raw SQL on
custom-business-object tables.

All four primitives below take a Django ``request`` (so they can read
``request.tenant_schema`` set by ``schema_authority``) OR a schema
string (for non-HTTP callers like the SQL function modules), an
``object_name`` (validated against the metadata registry), and a
narrowly-typed payload. They build SQL exclusively via ``psycopg2.sql``
composables, never f-strings or ``.format()`` on plain strings.

Phase 1 (scaffold): built but not wired. Caller-side feature flag
guarded by the legacy path raising ``DynamicGatewayDisabled``.

Phase 4.B wave 1: routing happens via ``api.permissions._orm_dispatch``
with the ``USE_DYNAMIC_GATEWAY`` flag. The legacy DELETE path
(``api/ORM/sqlFunctions/deleteSQLFunction.py``) now dispatches between
its raw cursor implementation and a thin wrapper that calls
``dynamic_table.delete()`` here. Future waves wire UPDATE / INSERT /
SELECT the same way.

Authorization is OUT of scope here — the gateway trusts that the caller
has already gone through the permissions layer. The gateway's job is
SQL safety, schema authority, and metadata enforcement.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional, Sequence

from django.db import connection, transaction
from psycopg2 import sql

from api.ORM.dynamic.identifier_validator import (
    InvalidIdentifierError,
    validate_field_name,
    validate_object_name,
)
from api.ORM.dynamic.metadata_loader import ObjectMeta, load_object

logger = logging.getLogger(__name__)


# Phase 4.B wave 1: removed _enforce_off_by_default + DynamicGatewayDisabled.
# The off-by-default contract now lives in the dispatch helper
# (api.permissions._orm_dispatch with flag="USE_DYNAMIC_GATEWAY"), not
# here. The gateway is a library — callers that reach it are expected
# to have already gone through dispatch, which means the env flag is
# already on. Direct imports are still allowed for tests + tooling.


class UnknownObject(LookupError):
    pass


class UnknownField(LookupError):
    pass


def _resolve_schema(request_or_schema) -> str:
    """Accept either a Django request (with ``tenant_schema`` pinned)
    or a schema string. Non-HTTP callers (e.g. the SQL function
    modules) pass schema directly because they don't have a request
    object to thread through."""
    if isinstance(request_or_schema, str):
        if not request_or_schema:
            raise PermissionError(
                "dynamic_table called with empty schema string."
            )
        return request_or_schema
    schema = getattr(request_or_schema, "tenant_schema", None)
    if not schema:
        raise PermissionError(
            "dynamic_table called without a pinned tenant schema. "
            "Run pin_request_tenant on the request first."
        )
    return schema


def _require_meta(schema: str, object_name: str) -> ObjectMeta:
    validate_object_name(object_name)
    meta = load_object(schema, object_name)
    if meta is None:
        raise UnknownObject(
            f"Object {object_name!r} is not registered in schema {schema!r}."
        )
    if meta.setup:
        # Setup tables (object, fields, profile, …) are migrating to
        # Django ORM in Phase 2/3/4; the dynamic gateway is for business
        # objects only.
        raise UnknownObject(
            f"Object {object_name!r} is a setup table; use the Django ORM."
        )
    return meta


def _validate_payload_keys(meta: ObjectMeta, payload: dict) -> None:
    valid = set(meta.field_names())
    # Allow id even if the metadata loader didn't include it explicitly
    # (every dynamic table is required to have one).
    valid.add("id")
    for key in payload.keys():
        validate_field_name(key)
        if key not in valid:
            raise UnknownField(
                f"Field {key!r} is not registered on object {meta.name!r}."
            )


def _set_search_path(cur, schema: str) -> None:
    cur.execute("SET search_path TO %s", [schema])


# ---------------------------------------------------------------------------
# CRUD primitives
# ---------------------------------------------------------------------------

def select(
    request,
    object_name: str,
    *,
    fields: Sequence[str],
    where: Optional[Iterable[tuple[str, str, Any]]] = None,
    order_by: Optional[Sequence[str]] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> list[dict]:
    """Read rows from a dynamic-object table.

    ``fields`` are validated against the metadata registry so a caller
    can't ask for ``password`` or other unregistered columns.
    ``where`` is an iterable of ``(field, op, value)`` tuples; only a
    small whitelist of operators is accepted.
    """
    schema = _resolve_schema(request)
    meta = _require_meta(schema, object_name)

    valid_fields = set(meta.field_names()) | {"id"}
    for f in fields:
        validate_field_name(f)
        if f not in valid_fields:
            raise UnknownField(f"{f!r} not on {meta.name!r}")

    select_cols = sql.SQL(", ").join(sql.Identifier(f) for f in fields)
    parts = [
        sql.SQL("SELECT "), select_cols,
        sql.SQL(" FROM "), sql.Identifier(meta.name),
    ]
    params: list[Any] = []
    if where:
        clauses = []
        for field, op, value in where:
            validate_field_name(field)
            if field not in valid_fields:
                raise UnknownField(f"{field!r} not on {meta.name!r}")
            op_norm = (op or "").lower()
            if op_norm not in {"=", "!=", "<", "<=", ">", ">=", "in", "is null", "is not null"}:
                raise ValueError(f"Operator {op!r} is not allowed.")
            if op_norm == "in":
                if not isinstance(value, (list, tuple)) or not value:
                    raise ValueError("'in' requires a non-empty sequence.")
                placeholders = sql.SQL(", ").join([sql.Placeholder()] * len(value))
                clauses.append(
                    sql.SQL("{} IN ({})").format(sql.Identifier(field), placeholders)
                )
                params.extend(value)
            elif op_norm in {"is null", "is not null"}:
                clauses.append(
                    sql.SQL("{} {}").format(
                        sql.Identifier(field),
                        sql.SQL(op_norm.upper()),
                    )
                )
            else:
                clauses.append(
                    sql.SQL("{} {} %s").format(
                        sql.Identifier(field),
                        sql.SQL(op_norm),
                    )
                )
                params.append(value)
        parts.append(sql.SQL(" WHERE "))
        parts.append(sql.SQL(" AND ").join(clauses))

    if order_by:
        order_clauses = []
        for ob in order_by:
            direction = "ASC"
            field = ob
            if ob.lower().endswith(" desc"):
                direction = "DESC"
                field = ob[:-5].strip()
            elif ob.lower().endswith(" asc"):
                field = ob[:-4].strip()
            validate_field_name(field)
            if field not in valid_fields:
                raise UnknownField(f"{field!r} not on {meta.name!r}")
            order_clauses.append(
                sql.SQL("{} {}").format(sql.Identifier(field), sql.SQL(direction))
            )
        parts.append(sql.SQL(" ORDER BY "))
        parts.append(sql.SQL(", ").join(order_clauses))

    if limit is not None:
        parts.append(sql.SQL(" LIMIT %s"))
        params.append(int(limit))
    if offset is not None:
        parts.append(sql.SQL(" OFFSET %s"))
        params.append(int(offset))

    query = sql.Composed(parts)
    with connection.cursor() as cur:
        _set_search_path(cur, schema)
        cur.execute(query, params)
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def insert(request, object_name: str, payload: dict) -> dict:
    """Insert one row, return the row with its server-generated columns."""
    if not payload:
        raise ValueError("insert requires a non-empty payload.")

    schema = _resolve_schema(request)
    meta = _require_meta(schema, object_name)
    _validate_payload_keys(meta, payload)

    columns = list(payload.keys())
    values = [payload[c] for c in columns]
    query = sql.SQL(
        "INSERT INTO {} ({cols}) VALUES ({placeholders}) RETURNING *"
    ).format(
        sql.Identifier(meta.name),
        cols=sql.SQL(", ").join(sql.Identifier(c) for c in columns),
        placeholders=sql.SQL(", ").join([sql.Placeholder()] * len(columns)),
    )
    with transaction.atomic(), connection.cursor() as cur:
        _set_search_path(cur, schema)
        cur.execute(query, values)
        cols = [c[0] for c in cur.description]
        row = cur.fetchone()
    return dict(zip(cols, row))


def update(request, object_name: str, *, record_id: str, patch: dict) -> int:
    """Update one row by primary key. Returns the number of rows affected."""
    if not patch:
        raise ValueError("update requires a non-empty patch.")
    if not record_id:
        raise ValueError("update requires a record_id.")

    schema = _resolve_schema(request)
    meta = _require_meta(schema, object_name)
    _validate_payload_keys(meta, patch)

    columns = list(patch.keys())
    set_clause = sql.SQL(", ").join(
        sql.SQL("{} = %s").format(sql.Identifier(c)) for c in columns
    )
    query = sql.SQL("UPDATE {} SET {} WHERE id = %s").format(
        sql.Identifier(meta.name), set_clause
    )
    params = [patch[c] for c in columns] + [record_id]
    with transaction.atomic(), connection.cursor() as cur:
        _set_search_path(cur, schema)
        cur.execute(query, params)
        return cur.rowcount


def update_unchecked(
    request_or_schema,
    object_name: str,
    *,
    record_id: str,
    patch: dict,
) -> int:
    """Phase 4.B wave 2 — UPDATE with no metadata-registry validation.

    The standard ``update()`` primitive validates every key in
    ``patch`` against the field registry; that's the gateway's
    metadata-enforcement contract. ``update_unchecked()`` skips that
    check.

    Use this for system-stamped writes that mix user fields with
    columns the application controls (``last_modified_by_id``,
    ``last_modified_date``, ``deleted_*``, etc.) — those audit
    columns are physical but may not be in the field registry, and
    the registry-enforcing path would reject them.

    Identifier-level safety is preserved (``object_name`` and every
    column name still go through ``validate_*``-style checks before
    reaching ``sql.Identifier``). The unchecked-ness is specifically
    "skip the metadata-registry membership check" — every other
    safety layer is intact.
    """
    if not patch:
        raise ValueError("update_unchecked requires a non-empty patch.")
    if not record_id:
        raise ValueError("update_unchecked requires a record_id.")

    schema = _resolve_schema(request_or_schema)
    validate_object_name(object_name)

    columns = list(patch.keys())
    for col in columns:
        validate_field_name(col)

    set_clause = sql.SQL(", ").join(
        sql.SQL("{} = %s").format(sql.Identifier(c)) for c in columns
    )
    query = sql.SQL("UPDATE {} SET {} WHERE id = %s").format(
        sql.Identifier(object_name), set_clause
    )
    params = [patch[c] for c in columns] + [record_id]
    with transaction.atomic(), connection.cursor() as cur:
        _set_search_path(cur, schema)
        cur.execute(query, params)
        return cur.rowcount


def delete(request, object_name: str, *, record_ids: Sequence[str]) -> int:
    """Hard-delete rows by primary key. Returns affected row count."""
    if not record_ids:
        return 0

    schema = _resolve_schema(request)
    meta = _require_meta(schema, object_name)

    placeholders = sql.SQL(", ").join([sql.Placeholder()] * len(record_ids))
    query = sql.SQL("DELETE FROM {} WHERE id IN ({})").format(
        sql.Identifier(meta.name), placeholders
    )
    with transaction.atomic(), connection.cursor() as cur:
        _set_search_path(cur, schema)
        cur.execute(query, list(record_ids))
        return cur.rowcount
