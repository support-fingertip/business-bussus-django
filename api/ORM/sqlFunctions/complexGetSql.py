import json
import logging
from django.db import connection
from pypika import Table, Query, Order, functions as fn
from pypika.terms import LiteralValue
from typing import Dict, List, Tuple, Any, Union

# ✅ Import your extracted helpers
from api.ORM.sqlFunctions.utils.helpers import (
    build_json_tree,
    generate_alias,
    ensure_joins,
    get_aggregate_function,
    insert_into_tree,
    resolve_field,
    build_nested_criteria,
    flatten_conditions,
)

_log = logging.getLogger(__name__)

# Aggregates that only make sense on numeric columns. If the user requests
# one against a non-numeric field we drop it rather than letting Postgres
# blow up with "function sum(character varying) does not exist".
_NUMERIC_AGGS = {"sum", "avg"}
_NUMERIC_DATATYPES = {
    "number", "numeric", "int", "int2", "int4", "int8",
    "integer", "bigint", "smallint", "decimal", "double precision",
    "real", "float", "float4", "float8", "currency", "percent",
}

_field_type_cache: Dict[Tuple[str, str, str], str] = {}


def _get_column_datatype(schema: str, table_name: str, column_name: str) -> str:
    """Return the information_schema data_type for a column, cached per process."""
    key = (schema or "public", table_name, column_name)
    if key in _field_type_cache:
        return _field_type_cache[key]
    try:
        with connection.cursor() as cur:
            cur.execute(
                """
                SELECT data_type
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s AND column_name = %s
                LIMIT 1
                """,
                [key[0], table_name, column_name],
            )
            row = cur.fetchone()
        dtype = (row[0] or "").lower() if row else ""
    except Exception:
        dtype = ""
    _field_type_cache[key] = dtype
    return dtype


def _is_numeric_agg_valid(field_name: str, base_table_name: str, schema: str) -> bool:
    """Resolve a (possibly dotted) field path to its table+column and check
    whether the underlying datatype supports SUM/AVG."""
    parts = field_name.split(".")
    # For dotted paths the last-but-one segment is the related object name
    # (relationship/table). For a single-segment field the base table owns it.
    table = parts[-2] if len(parts) > 1 else base_table_name
    column = parts[-1]
    dtype = _get_column_datatype(schema, table, column)
    if not dtype:
        # Unknown — be permissive so we don't silently drop valid aggregates.
        return True
    for hint in _NUMERIC_DATATYPES:
        if hint in dtype:
            return True
    return False

def build_complex_query(**kwargs) -> Tuple[str, List[Any], Dict]:
    input_data = kwargs   
    schema = input_data.get("schema")  
    if not schema:
        raise ValueError("Invalid user request: 'schema' is required in kwargs")

    base_table_name = input_data["tableName"]
    fields = input_data.get("fields", [])
    where_clauses = input_data.get("where", [])
    having_clauses = input_data.get("having", [])
    group_by = input_data.get("group_by", [])
    order_by = input_data.get("order_by", [])
    limit = input_data.get("limit")
    offset = input_data.get("offset")
    distinct = input_data.get("distinct", False)
    relationships = input_data.get("relationships", {})
    relationship_output = input_data.get("relationship_output", "None")
    alias_mode = input_data.get("aliasing", "auto")
    # print(relationship_output, relationships)

    base = Table(base_table_name)
    query = Query.from_(base).distinct() if distinct else Query.from_(base)
    tables = {base_table_name: base}
    joins = {}
    json_tree = {}
    params = []
    alias_map = {}
    alias_counter = 0
    json_aliases = {}
    mapped_aliases = {}

    select_fields = []
    all_fields = []
    for f in fields:
        if isinstance(f, str):
            all_fields.append(f)
        elif isinstance(f, dict) and "name" in f:
            # `expression: True` fields carry a raw SQL fragment as
            # their "name" (e.g. `ROUND((COALESCE("invoice_item"."quantity", 0) * …))`).
            # The dots inside that fragment look like relationship paths
            # to the JOIN-resolution loop below, which then emitted
            # bogus `LEFT JOIN "ROUND((COALESCE..."` clauses and crashed
            # SQL with a zero-length-identifier error. Skip these
            # entries entirely — they're already self-contained SQL.
            if f.get("expression", False):
                continue
            all_fields.append(f["name"])

    all_fields += flatten_conditions(where_clauses) + flatten_conditions(having_clauses)
    GROUPING_FORMAT_MAP = {
        "year": "TO_CHAR({col}, 'YYYY')",
        # Include the year on quarter/month so buckets across years stay
        # distinct (otherwise Jan-2024 and Jan-2025 collapse into one
        # "Jan" row and the user can't tell them apart).
        "quarter": "TO_CHAR({col}, '\"Q\"Q-YYYY')",
        "month": "TO_CHAR({col}, 'Mon-YYYY')",
        "week": "TO_CHAR(DATE_TRUNC('week', {col}), 'FMMM/DD/YYYY') || ' - ' || TO_CHAR(DATE_TRUNC('week', {col}) + INTERVAL '6 days', 'FMMM/DD/YYYY')",
        "day": "TO_CHAR({col}, 'DD-MM-YYYY')",
        "date": "TO_CHAR({col}, 'DD-MM-YYYY')",
        "hour": "TO_CHAR({col}, 'DD-MM-YYYY HH24')",
        "minute": "TO_CHAR({col}, 'DD-MM-YYYY HH24:MI')",
    }
    GROUPING_ORDER_MAP = {
        "year": "MIN({col})",
        "quarter": "MIN({col})",
        "month": "MIN({col})",
        "week": "MIN({col})",
        "day": "MIN({col})",
        "date": "MIN({col})",
        "hour": "MIN({col})",
        "minute": "MIN({col})",
    }
    grouping_map = {}
    grouping_unit_map = {}

    def _qualified_col_sql(field_name, base_tbl, resolved_col):
        """Return a fully-qualified SQL expression for a column so it won't
        collide with same-named columns on joined tables. For single-segment
        base-table fields, explicitly prefix with the base table name."""
        if "." in field_name:
            return str(resolved_col)
        return f'"{base_tbl}"."{field_name}"'

    if isinstance(group_by, dict):
        group_items = group_by.get('rows', []) + group_by.get('columns', [])
    elif isinstance(group_by, list):
        group_items = group_by
    else:
        group_items = []

    for item in group_items:
        if isinstance(item, dict):
            fname = item.get("field") or item.get("name", "")
            all_fields.append(fname)
            raw_unit = item.get("grouping") or item.get("grouping_unit")
            # Caller may resolve a formula's `formula_expression` and
            # forward it on the group_by dict so the SQL builder can
            # inline it into both SELECT and GROUP BY. This is what
            # lets users pivot by a formula/rollup field — without it
            # the report controller strips the field as "computed" and
            # the pivot ends up with no column-axis buckets.
            raw_expr = item.get("expression") or item.get("expression_sql")
            if raw_unit:
                # Frontend sends Title-cased ("Month", "Year"); the format
                # map is keyed by lowercase ("month", "year"). Without the
                # normalisation, `GROUPING_FORMAT_MAP.get("Month", default)`
                # returns the daily default and the report renders raw
                # dates instead of month/year buckets.
                unit_key = str(raw_unit).strip().lower()
                grouping_map[fname] = GROUPING_FORMAT_MAP.get(unit_key, "TO_CHAR({col}, 'YYYY-MM-DD')")
                grouping_unit_map[fname] = unit_key
            elif raw_expr:
                # The expression is already a SQL fragment with column
                # refs (table-qualified by the caller). Wrap in parens
                # so it composes safely with downstream operators.
                grouping_map[fname] = f"({raw_expr})"
        elif isinstance(item, str):
            all_fields.append(item)

    for field in all_fields:
        if not isinstance(field, str):
            continue
        parts = field.split(".")
        if len(parts) > 1:
            query = ensure_joins(query, tables, joins, parts[:-1], relationships, base, base_table_name)

    for f in fields:
        if isinstance(f, str):
            name = f
            alias = name.split(".")[-1] if alias_mode == "none" else generate_alias(alias_counter)
            alias_counter += 1
            col, query = resolve_field(name, base, base_table_name, tables, relationships, joins, query)
            if relationship_output == "json" and ("." not in name):
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

        elif isinstance(f, dict):
            name = f["name"]
            alias = f.get("alias")
            agg = f.get("aggregate")

            if f.get("expression", False):
                # `name` here is a raw SQL fragment like
                # "SUM(ROUND((quantity * unit_price - discount_amount) + …))"
                # built by the export pipeline so the database evaluates
                # the formula in-place. Wrapping it in `fn.Function("", name)`
                # makes pypika quote it as a literal string ('SUM(...)') —
                # which is why the export's "Sum of Grand Total" cells
                # rendered the formula expression as text instead of a
                # number. `LiteralValue` injects the fragment verbatim.
                alias = alias or generate_alias(alias_counter)
                alias_counter += 1
                select_fields.append(LiteralValue(f'{name} "{alias}"'))
                alias_map[alias] = name
                continue

            if agg:
                # Guard against numeric aggregates on text columns. Postgres
                # raises "function sum(character varying) does not exist" and
                # kills the whole report — if the column isn't numeric, skip
                # this aggregate entry instead of emitting invalid SQL.
                if (
                    agg.lower() in _NUMERIC_AGGS
                    and not _is_numeric_agg_valid(name, base_table_name, schema)
                ):
                    _log.warning(
                        "Dropping %s aggregate on non-numeric field %s.%s",
                        agg, base_table_name, name,
                    )
                    continue
                alias = alias or generate_alias(alias_counter)
                alias_counter += 1
                col, query = resolve_field(name, base, base_table_name, tables, relationships, joins, query)
                col = get_aggregate_function(agg, col)
                select_fields.append(col.as_(alias))
                alias_map[alias] = name
            elif relationship_output == "json" and name.endswith("__r"):
                parts = name.split(".")
                alias = alias or generate_alias(alias_counter)
                alias_counter += 1
                insert_into_tree(json_tree, parts, alias=alias)
                json_aliases[parts[0]] = parts[0]
            else:
                alias = alias or generate_alias(alias_counter)
                alias_counter += 1
                # When the field is a pre-resolved formula expression
                # (no `{col}` placeholder in the template), skip
                # `resolve_field` — the field name is the formula's
                # logical name (e.g. "tax_amount") which doesn't exist
                # as a physical column on the base table and would
                # raise "column does not exist".
                gm_entry = grouping_map.get(name)
                is_inline_expr = (
                    gm_entry is not None and "{col}" not in gm_entry
                )
                if is_inline_expr:
                    select_fields.append(LiteralValue(f"{gm_entry} \"{alias}\""))
                    alias_map[alias] = name
                    continue
                col, query = resolve_field(name, base, base_table_name, tables, relationships, joins, query)
                if name in grouping_map:
                    # Always fully-qualify the column so TO_CHAR(...) doesn't
                    # collide with a same-named column on a joined relation
                    # (e.g. base.created_date vs product.created_date ->
                    # "column reference is ambiguous" from PostgreSQL).
                    col_sql = _qualified_col_sql(name, base_table_name, col)
                    fmt_expr = grouping_map[name].format(col=col_sql)
                    select_fields.append(LiteralValue(f"{fmt_expr} \"{alias}\""))
                    grouping_map[name] = fmt_expr
                else:
                    select_fields.append(col.as_(alias))
                alias_map[alias] = name
    
    for alias, root_key in json_aliases.items(): 
        if root_key in json_tree:
            select_fields.append(build_json_tree(json_tree[root_key], tables, get_aggregate_function).as_(root_key))

    query = query.select(*select_fields)

    if where_clauses:
        query = query.where(build_nested_criteria(where_clauses, "where", base, base_table_name, tables, relationships, joins, query, params))

    if isinstance(group_by, dict):
        # Pivot reports configure two grouping axes — `rows` AND `columns`.
        # Pulling only `rows` into the SQL GROUP BY collapses every column
        # bucket into one row, which is why the user's Tax Amount / Total
        # Amount group-columns weren't reflected in the preview matrix.
        # Both axes need to be in GROUP BY so each (row × column) cell
        # gets its own aggregate.
        raw_group = list(group_by.get('rows', [])) + list(group_by.get('columns', []))
    else:
        raw_group = group_by

    for gb in raw_group:
        if isinstance(gb, dict):
            gb_field = gb.get("field") or gb.get("name", "")
        else:
            gb_field = gb
        if gb_field in grouping_map:
            # If the SELECT loop didn't process this field (e.g. the
            # group-by column wasn't in the SELECT list because the user
            # only kept aggregate fields), the grouping_map entry is
            # still the raw template `TO_CHAR({col}, 'Mon')`. Resolve
            # the column NOW and substitute, otherwise we'd emit
            # `GROUP BY TO_CHAR({col}, 'Mon')` literally and Postgres
            # would either error or fall back to grouping by the raw
            # date.
            gb_expr = grouping_map[gb_field]
            if "{col}" in gb_expr:
                col, query = resolve_field(gb_field, base, base_table_name, tables, relationships, joins, query)
                col_sql = _qualified_col_sql(gb_field, base_table_name, col)
                gb_expr = gb_expr.format(col=col_sql)
                grouping_map[gb_field] = gb_expr
            query = query.groupby(LiteralValue(gb_expr))
        else:
            col, query = resolve_field(gb_field, base, base_table_name, tables, relationships, joins, query)
            if "." not in gb_field and joins:
                query = query.groupby(LiteralValue(
                    _qualified_col_sql(gb_field, base_table_name, col)
                ))
            else:
                query = query.groupby(col)

    if having_clauses:
        query = query.having(build_nested_criteria(having_clauses, "having", base, base_table_name, tables, relationships, joins, query, params))

    for ob in order_by:
        key = ob["field"]
        resolved = alias_map.get(key, key)
        direction = ob["direction"].upper()
        order = Order.desc if direction == "DESC" else Order.asc
        if resolved in grouping_unit_map:
            col, query = resolve_field(resolved, base, base_table_name, tables, relationships, joins, query)
            col_sql = _qualified_col_sql(resolved, base_table_name, col)
            order_expr = GROUPING_ORDER_MAP[grouping_unit_map[resolved]].format(col=col_sql)
            query = query.orderby(LiteralValue(order_expr), order=order)
        else:
            field, query = resolve_field(resolved, base, base_table_name, tables, relationships, joins, query)
            query = query.orderby(field, order=order)

    # Auto-add calendar order for grouped date fields when no explicit order_by is set for them
    if group_items and not any(
        alias_map.get(ob["field"], ob["field"]) in grouping_unit_map for ob in order_by
    ):
        for gb in raw_group:
            gb_field = gb.get("field") or gb.get("name", "") if isinstance(gb, dict) else gb
            if gb_field in grouping_unit_map:
                col, query = resolve_field(gb_field, base, base_table_name, tables, relationships, joins, query)
                col_sql = _qualified_col_sql(gb_field, base_table_name, col)
                order_expr = GROUPING_ORDER_MAP[grouping_unit_map[gb_field]].format(col=col_sql)
                query = query.orderby(LiteralValue(order_expr), order=Order.asc)

    if limit:
        query = query.limit(limit)
    if offset:
        query = query.offset(offset)

    result = fetch_data_raw_sql(str(query), schema=schema)
    return result


def fetch_data_raw_sql(sql, schema='public'):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL search_path TO %s", [schema])
            cursor.execute(sql)
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
                    else:
                        row_data[col_name] = value
                results.append(row_data)
            return results
    except Exception as e:
        print(sql,"This is the SQL that caused error")
        print("SQL Execution Error:", e)
        raise Exception("Something went wrong while fetching the data.",str(e)) from e

