import json
import logging
import re
from copy import deepcopy
from datetime import datetime, timezone as dt_timezone
from typing import Any, Dict, List, Optional, Tuple

from django.db import connection
from pypika import Order, Query, Table

from api.ORM.sqlFunctions.complexGetSql import build_complex_query
from api.ORM.sqlFunctions.relationships import build_relationships_dynamic
from api.ORM.sqlFunctions.utils.query_builder_helpers import (
    build_json_tree,
    build_nested_criteria,
    ensure_joins,
    flatten_conditions,
    generate_alias,
    get_aggregate_function,
    insert_into_tree,
    resolve_field,
)

logger = logging.getLogger(__name__)

SHARED_TABLES = {"organizations", "lead_capture", "user_login_history"}
SCHEMA_REGEX = re.compile(r"^[A-Za-z0-9_]+$")

def _validate_schema(schema: str) -> str:
    if not schema or not SCHEMA_REGEX.match(schema):
        raise ValueError("Invalid schema name")
    return schema


def _validate_pagination(limit: Optional[Any], offset: Optional[Any]) -> Tuple[Optional[int], Optional[int]]:
    def _to_int(value: Any, name: str) -> Optional[int]:
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError(f"{name} must be an integer")
        try:
            iv = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"{name} must be an integer")
        if iv < 0:
            raise ValueError(f"{name} must be non-negative")
        return iv
    return _to_int(limit, "limit"), _to_int(offset, "offset")


def build_query(**kwargs):
    input_data = deepcopy(kwargs)
    base_table_name = input_data["tableName"]
    schema = _validate_schema(input_data.get("schema"))

    # Build relationships first
    input_data = build_relationships_dynamic(input_data, **kwargs)

    # Delegate to report builder if needed
    if input_data.get("report", False):
        return build_complex_query(**input_data)

    # Basic params
    record_id = input_data.get("id")
    fields: List[Any] = deepcopy(input_data.get("fields", []))
    if "id" not in fields:
        fields.insert(0, "id")

    where_clauses = deepcopy(input_data.get("where", []))
    if record_id is not None:
        if isinstance(where_clauses, list):
            where_clauses.append({"field": "id", "value": record_id, "operator": "="})
        elif isinstance(where_clauses, dict):
            where_clauses.setdefault("and", []).append({"field": "id", "value": record_id, "operator": "="})

    # Enforce org scoping for shared tables
    if base_table_name in SHARED_TABLES:
        org_id = kwargs.get("org", {}).get("id")
        if org_id is None:
            raise ValueError("organization_id is required for shared tables")
        where_clauses.append({"field": "organization_id", "value": org_id, "operator": "="})
        schema = "public"

    having_clauses = deepcopy(input_data.get("having", []))
    group_by = deepcopy(input_data.get("group_by", []))
    order_by = deepcopy(input_data.get("order_by") or [{"field": "created_date", "direction": "DESC"}])
    limit, offset = _validate_pagination(input_data.get("limit"), input_data.get("offset"))
    distinct = bool(input_data.get("distinct", False))
    relationships = input_data.get("relationships", {})
    relationship_output = input_data.get("relationship_output", "json")
    alias_mode = input_data.get("aliasing", "none")

    # Setup query state
    base = Table(base_table_name)
    query = Query.from_(base).distinct() if distinct else Query.from_(base)
    tables = {base_table_name: base}
    joins: Dict[str, Any] = {}
    json_tree: Dict[str, Any] = {}
    params: List[Any] = []
    alias_map: Dict[str, str] = {}
    alias_counter = 0
    json_aliases: Dict[str, str] = {}
    mapped_aliases: Dict[str, str] = {}

    def next_alias():
        nonlocal alias_counter
        alias = generate_alias(alias_counter)
        alias_counter += 1
        return alias

    # Collect fields to ensure joins
    select_fields = []
    all_fields: List[str] = []

    for f in fields:
        if isinstance(f, str):
            all_fields.append(f)
        elif isinstance(f, dict) and "name" in f:
            all_fields.append(f["name"])

    all_fields += flatten_conditions(where_clauses) + flatten_conditions(having_clauses) + group_by

    for field in all_fields:
        parts = field.split(".")
        if len(parts) > 1:
            query = ensure_joins(query, tables, joins, parts[:-1], relationships, base, base_table_name)

    # Select fields
    for f in fields:
        if isinstance(f, str):
            name = f
            alias = (
                name.split(".")[-1] if alias_mode == "none"
                else next_alias() if alias_mode == "auto"
                else None
            )
            if alias is None:
                raise ValueError(f"Explicit alias required for field: {name}")

            col, query = resolve_field(name, base, base_table_name, tables, relationships, joins, query)

            if relationship_output == "json" and "." not in name:
                select_fields.append(col)
            elif relationship_output != "json":
                select_fields.append(col)

            alias_map[alias] = name

            if relationship_output == "json":
                parts = name.split(".")
                insert_into_tree(json_tree, parts, alias=alias)
                if alias != parts[0] and mapped_aliases.get(parts[0]) is None:
                    json_aliases[parts[0]] = parts[0]
                    mapped_aliases[parts[0]] = parts[0]

    for alias, root_key in json_aliases.items():
        if root_key in json_tree:
            select_fields.append(build_json_tree(json_tree[root_key], tables, get_aggregate_function).as_(root_key))

    query = query.select(*select_fields)

    # WHERE
    if where_clauses:
        query = query.where(
            build_nested_criteria(
                where_clauses, "where", base, base_table_name, tables, relationships, joins, query, params
            )
        )

    # GROUP BY
    for gb in group_by:
        col, query = resolve_field(gb, base, base_table_name, tables, relationships, joins, query)
        query = query.groupby(col)

    # HAVING
    if having_clauses:
        query = query.having(
            build_nested_criteria(
                having_clauses, "having", base, base_table_name, tables, relationships, joins, query, params
            )
        )

    # ORDER BY
    if order_by and isinstance(order_by, list):
        for ob in order_by:
            key = ob["field"]
            direction = str(ob.get("direction", "ASC")).upper()
            direction = "DESC" if direction == "DESC" else "ASC"
            resolved = alias_map.get(key, key)
            col, query = resolve_field(resolved, base, base_table_name, tables, relationships, joins, query)
            query = query.orderby(col, order=Order.desc if direction == "DESC" else Order.asc)

    # LIMIT & OFFSET
    if limit is not None:
        query = query.limit(limit)
    if offset is not None:
        query = query.offset(offset)

    sql = str(query)
    return fetch_data_raw_sql(sql, params=params, schema=schema)


def fetch_data_raw_sql(sql: str, params: Optional[List[Any]] = None, schema: str = "public"):
    params = params or []
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO %s", [schema])
            cursor.execute(sql, params)
            columns = [col[0] for col in cursor.description]
            results = []
            for row in cursor.fetchall():
                row_data = {}
                for idx, value in enumerate(row):
                    col_name = columns[idx]
                    if isinstance(value, (dict, list)):
                        row_data[col_name] = value
                    elif isinstance(value, str) and value.strip().startswith(('{', '[')):
                        try:
                            row_data[col_name] = json.loads(value)
                        except json.JSONDecodeError:
                            row_data[col_name] = value
                    elif isinstance(value, datetime) and value.tzinfo is None:
                        # TIMESTAMP (without TZ) columns come back as naive datetimes.
                        # The DB session timezone is UTC, so naive values are UTC — attach
                        # UTC tzinfo so DRF serialises them with "+00:00" and the frontend
                        # can correctly convert to local time instead of treating them as
                        # local time directly (which would be 5:30 h off for IST users).
                        row_data[col_name] = value.replace(tzinfo=dt_timezone.utc)
                    else:
                        row_data[col_name] = value
                results.append(row_data)
            return results
    except Exception as e:
        print(sql,"This is the SQL that caused error")
        logger.exception("SQL execution failed")
        raise Exception("Something went wrong while fetching the data.",str(e)) from e