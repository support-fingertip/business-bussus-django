"""
Utility functions for processing formula and rollup_summary fields
in list views, reports, and preview pages.
"""
import re
from django.db import connection, transaction
from psycopg2 import sql

# Phase 8.A5 — information_schema-backed identifier allow-list +
# explicit operator whitelist. The audit flagged f-string SQL in this
# module as CRITICAL; the helpers below replace ad-hoc validation with
# authoritative checks against Postgres metadata.
from api.BL.computed_fields_columns import (
    InvalidIdentifierError,
    InvalidOperatorError,
    assert_column,
    assert_operator,
    get_allowed_columns,
)


_column_exists_cache: dict = {}


def _resolve_join_table(relationship, schema):
    """Resolve a dotted-filter `relationship` prefix to the actual parent
    table name. Tries the schema's `object` registry (handles plural vs
    singular), falls back to the prefix itself."""
    if not relationship or not schema:
        return relationship
    try:
        with connection.cursor() as cur:
            cur.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
            )
            cur.execute(
                "SELECT name FROM object WHERE name = %s OR name = %s LIMIT 1",
                [relationship, relationship + "s"],
            )
            row = cur.fetchone()
            if row:
                return row[0]
    except Exception:
        pass
    return relationship


def _build_simple_where(filters, base_alias, schema):
    """Translate a flat filters list into (where_parts, params, joins).
    `joins` is a list of (relationship, parent_table) pairs to LEFT JOIN
    onto the base alias via `{base_alias}.{relationship}_id`. Returns
    (None, None, None) when filters can't be safely translated (nested
    AND/OR, unknown ops, etc.) — caller should fall back."""
    where_parts = []
    params: list = []
    joins: dict = {}  # relationship -> parent_table
    EQ = {"=", "==", "equals"}
    NE = {"!=", "<>", "not_equals"}
    GT = {">", "greater_than"}
    LT = {"<", "less_than"}
    GE = {">=", "greater_than_or_equal"}
    LE = {"<=", "less_than_or_equal"}
    NULL_OPS = {"is_null", "is null", "is_blank", "is blank"}
    NOT_NULL_OPS = {"is_not_null", "is not null", "is_not_blank", "is not blank"}

    NUMERIC_OPS = GT | LT | GE | LE
    for f in filters:
        if not isinstance(f, dict):
            return None, None, None
        if "and" in f or "or" in f:
            return None, None, None
        field = f.get("field")
        op = (f.get("operator") or "=").lower()
        val = f.get("value")
        if not field:
            return None, None, None
        # Numeric ops on a numeric column choke when value arrives as a
        # JSON string (e.g. "30") — Postgres throws "operator does not
        # exist: integer < text". Coerce here so direct_report_count and
        # direct_group_count don't silently fall back to the summary
        # row-count fallback (which is bounded by the visible page size
        # and reports the wrong total to the UI).
        if op in NUMERIC_OPS and isinstance(val, str):
            try:
                val = float(val)
                if val.is_integer():
                    val = int(val)
            except (TypeError, ValueError):
                pass
        # Dotted: JOIN to the parent table and qualify the column with the
        # parent alias. Empty IN with a dotted filter still short-circuits
        # to 0 — no rows can match.
        if "." in str(field):
            relationship, base_col = str(field).split(".", 1)
            if not relationship or not base_col:
                return None, None, None
            if relationship not in joins:
                joins[relationship] = _resolve_join_table(relationship, schema)
            col = sql.SQL("{}.{}").format(
                sql.Identifier(relationship), sql.Identifier(base_col)
            )
        else:
            col = sql.SQL("{}.{}").format(
                sql.Identifier(base_alias), sql.Identifier(field)
            )
        if op in EQ:
            where_parts.append(sql.SQL("{} = %s").format(col)); params.append(val)
        elif op in NE:
            where_parts.append(sql.SQL("{} <> %s").format(col)); params.append(val)
        elif op in GT:
            where_parts.append(sql.SQL("{} > %s").format(col)); params.append(val)
        elif op in LT:
            where_parts.append(sql.SQL("{} < %s").format(col)); params.append(val)
        elif op in GE:
            where_parts.append(sql.SQL("{} >= %s").format(col)); params.append(val)
        elif op in LE:
            where_parts.append(sql.SQL("{} <= %s").format(col)); params.append(val)
        elif op == "in":
            if not isinstance(val, (list, tuple)):
                val = [val]
            if not val:
                return [sql.SQL("FALSE")], [], joins
            where_parts.append(sql.SQL("{} = ANY(%s)").format(col)); params.append(list(val))
        elif op in ("contains", "ilike"):
            where_parts.append(sql.SQL("{} ILIKE %s").format(col)); params.append(f"%{val}%")
        elif op in NULL_OPS:
            where_parts.append(sql.SQL("{} IS NULL").format(col))
        elif op in NOT_NULL_OPS:
            where_parts.append(sql.SQL("{} IS NOT NULL").format(col))
        else:
            return None, None, None
    return where_parts, params, joins


def _format_joins(base_alias, joins):
    """Build LEFT JOIN clauses for each (relationship, parent_table) pair
    against `{base_alias}.{relationship}_id`. Skips self-join when the
    parent table is the base table itself."""
    parts = []
    for rel, parent_table in joins.items():
        parts.append(
            sql.SQL("LEFT JOIN {pt} AS {alias} ON {alias}.id = {base}.{fk}").format(
                pt=sql.Identifier(parent_table),
                alias=sql.Identifier(rel),
                base=sql.Identifier(base_alias),
                fk=sql.Identifier(f"{rel}_id"),
            )
        )
    return parts


def direct_report_count(table_name, filters, schema):
    """Run a direct `SELECT COUNT(*)` against `schema.table_name` using a
    best-effort WHERE built from the flat filters list. Returns int on
    success, None when the filters can't be safely translated (nested
    AND/OR trees, unknown operators) — caller should fall back to the
    regular path.

    Dotted-field filters (e.g. `invoice.grand_total < 100000` on
    `invoice_item`) are handled by emitting a LEFT JOIN to the resolved
    parent table — so the count reflects ALL matching rows in the table,
    not just the fetched batch.

    Bypasses get_permissions/build_query so that report previews can still
    populate `total_count` even when the report-mode count call fails
    (e.g. on huge IN lists produced by the rollup-aggregation push, or
    when get_permissions returns an unexpected shape under report=True).
    """
    if not table_name or not schema or filters is None:
        return None
    if not isinstance(filters, list):
        return None

    where_parts, params, joins = _build_simple_where(filters, table_name, schema)
    if where_parts is None:
        return None

    join_clauses = _format_joins(table_name, joins)

    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
                )
                base = sql.SQL("SELECT COUNT(*) FROM {tbl}").format(
                    tbl=sql.Identifier(table_name)
                )
                if join_clauses:
                    base = sql.SQL("{} {}").format(base, sql.SQL(" ").join(join_clauses))
                if where_parts:
                    query = sql.SQL("{} WHERE {}").format(
                        base, sql.SQL(" AND ").join(where_parts)
                    )
                else:
                    query = base
                cur.execute(query, params)
                row = cur.fetchone()
                if row and row[0] is not None:
                    return int(row[0])
    except Exception as exc:
        print(f"[direct_report_count] failed: {exc!r}")
        return None
    return None


def direct_group_count(table_name, filters, group_field, schema):
    """Run `SELECT COUNT(DISTINCT group_field) FROM schema.table WHERE ...`
    so the summary-view pagination can show the number of distinct groups
    (parent values) rather than the underlying detail-row count.

    Mirrors `direct_report_count` for the simple-filter cases — including
    JOIN-emission for dotted-field filters. Returns int on success, None
    when filters can't be safely translated.
    """
    if not table_name or not schema or not group_field:
        return None
    if filters is None or not isinstance(filters, list):
        return None
    if "." in str(group_field):
        # Group field with relation: caller is expected to pass the FK
        # column on the base table instead.
        return None

    where_parts, params, joins = _build_simple_where(filters, table_name, schema)
    if where_parts is None:
        return None

    join_clauses = _format_joins(table_name, joins)

    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
                )
                gcol = sql.SQL("{}.{}").format(
                    sql.Identifier(table_name), sql.Identifier(group_field)
                )
                base = sql.SQL("SELECT COUNT(DISTINCT {gc}) FROM {tbl}").format(
                    gc=gcol, tbl=sql.Identifier(table_name)
                )
                if join_clauses:
                    base = sql.SQL("{} {}").format(base, sql.SQL(" ").join(join_clauses))
                if where_parts:
                    query = sql.SQL("{} WHERE {}").format(
                        base, sql.SQL(" AND ").join(where_parts)
                    )
                else:
                    query = base
                cur.execute(query, params)
                row = cur.fetchone()
                if row and row[0] is not None:
                    return int(row[0])
    except Exception as exc:
        print(f"[direct_group_count] failed: {exc!r}")
        return None
    return None


def _matching_parents_via_formula_inline(formula_field, parent_table, op_sql, value, schema):
    """Push a non-materialised formula filter down to SQL by inlining the
    field's `formula_expression` into a `SELECT id FROM parent WHERE
    (<expr>) op X` query. Returns matching parent IDs, or None when the
    expression isn't safe to inline (uses formula functions, string ops,
    or references columns the parent table doesn't have) so the caller
    can fall back to the Python evaluator.

    Safety: the expression is whitelisted to letters/digits/underscores,
    arithmetic operators (+ - * / %), parens, decimal points, and
    whitespace. Any other character — including quotes, semicolons, or
    function call syntax — disqualifies the formula. The whitelisted
    output is wrapped in parens and validated against the parent's
    column list, so the only way SQL sees the string is as an arithmetic
    expression over real columns.
    """
    if not formula_field or not parent_table or not schema:
        return None
    # Fetch the formula expression for this field on the parent object.
    try:
        with connection.cursor() as _cur:
            _cur.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
            )
            _cur.execute(
                """
                SELECT formula_expression FROM fields
                WHERE name = %s AND datatype = 'formula'
                  AND object_name IN (%s, %s, %s)
                LIMIT 1
                """,
                [formula_field, parent_table, parent_table.rstrip("s"), parent_table + "s"],
            )
            row_ = _cur.fetchone()
    except Exception:
        return None
    if not row_ or not row_[0]:
        return None
    expr = row_[0].strip()
    # Whitelist: arithmetic on column identifiers + literals, plus a
    # comma to allow function args like `ROUND(x, 2)`.
    import re as _re
    if not _re.fullmatch(r"[A-Za-z0-9_+\-*/%(),.\s]+", expr):
        return None
    # SQL function names that may appear in the expression but aren't
    # columns. Without this carve-out the column-existence check below
    # rejects ANY formula that uses a function (`ROUND`, `COALESCE`,
    # `ABS`, etc.) and the filter never gets pushed to SQL — the user's
    # `Less Than 10000` filter on `invoice.grand_total` silently became
    # a no-op because the saved formula starts with `ROUND(`.
    _FUNCTION_TOKENS = {
        "ROUND", "ABS", "CEIL", "FLOOR", "COALESCE", "GREATEST", "LEAST",
        "CASE", "WHEN", "THEN", "ELSE", "END", "IF", "AND", "OR", "NOT",
        "TRUE", "FALSE", "NULL", "IS", "IN", "BETWEEN", "LIKE", "ILIKE",
        "TO_CHAR", "EXTRACT", "DATE", "TIMESTAMP", "NULLIF",
    }
    # Pull out identifiers and confirm each non-function-name one exists
    # as a real column on the parent table — otherwise SQL will raise
    # mid-query and we'd lose the surrounding transaction.
    identifiers = set(_re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr))
    for ident in identifiers:
        if ident.upper() in _FUNCTION_TOKENS:
            continue
        if not _column_exists(parent_table, ident, schema):
            return None

    # Phase 8.A5 — defence-in-depth on top of the regex + column-existence
    # whitelist already done above. Two extra invariants enforced here:
    #
    #   (1) op_sql MUST be on the explicit ALLOWED_COMPARISON_OPERATORS
    #       whitelist. The caller already pulls it from SQL_PUSHABLE_OPS,
    #       which is a hardcoded dict — but a future refactor that
    #       widens that dict could break this assumption. assert_operator
    #       raises if op_sql ever drifts.
    #
    #   (2) parent_table + every identifier MUST appear in the
    #       information_schema.columns row set for (schema, parent_table).
    #       The old _column_exists used a less-vetted lookup path; the new
    #       assert_column uses information_schema directly, which is the
    #       source of truth no formula-string can fool.
    #
    # Both checks raise BEFORE any SQL leaves the app (the audit's specific
    # ask). The caller's outer try/except None-catches them, falling back
    # to the Python evaluator — same behaviour as a regex-rejection today.
    try:
        op_spec = assert_operator(op_sql)
    except InvalidOperatorError:
        return None
    op_sql_fragment = op_spec["sql"]  # already validated; safe to inline

    # The columns we're going to interpolate must each be a real column.
    # The earlier _column_exists check has already happened, but it doesn't
    # use information_schema; do an authoritative pass here so a single
    # source of truth gates the SQL build.
    try:
        for ident in identifiers:
            if ident.upper() in _FUNCTION_TOKENS:
                continue
            assert_column(schema, parent_table, ident)
    except InvalidIdentifierError:
        return None

    if op_sql == "IS NULL" or op_sql == "IS NOT NULL":
        # IS NULL / IS NOT NULL on a formula: rewrite as "every referenced
        # column IS [NOT] NULL". Approximate but covers the common case.
        params: list = []
        # The connector is fixed-shape SQL (AND/OR) — not user input.
        connector_sql = sql.SQL(" AND ") if op_sql == "IS NULL" else sql.SQL(" OR ")
        clause_pieces = [
            sql.SQL("{} ").format(sql.Identifier(ident))
            + sql.SQL(op_sql_fragment)
            for ident in identifiers
            if ident.upper() not in _FUNCTION_TOKENS
        ]
        if clause_pieces:
            having_clause = connector_sql.join(clause_pieces)
        else:
            having_clause = sql.SQL("1=1")
        full_sql = sql.SQL("SELECT id FROM {tbl} WHERE {clause}").format(
            tbl=sql.Identifier(parent_table),
            clause=having_clause,
        )
    else:
        params = [value]
        # `expr` is the user's formula string — it's already passed the
        # character whitelist (line ~291) AND every identifier in it is
        # verified above. The remaining risk surface is the operator and
        # the table name; both are now passed through psycopg2.sql so
        # they can't break out of their slot.
        #
        # We pass the validated expr inside `sql.SQL(...)` rather than
        # via sql.Identifier (it isn't a single identifier — it's an
        # arithmetic expression over columns). The whitelist + identifier
        # check is what makes that safe.
        full_sql = sql.SQL(
            "SELECT id FROM {tbl} WHERE ({expr}) "
        ).format(
            tbl=sql.Identifier(parent_table),
            expr=sql.SQL(expr),
        ) + sql.SQL(op_sql_fragment) + sql.SQL(" %s")

    try:
        with transaction.atomic():
            with connection.cursor() as _cur:
                _cur.execute(
                    sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
                )
                _cur.execute(full_sql, params)
                return [r[0] for r in _cur.fetchall()]
    except Exception:
        return None


_AGG_OPS_NUMERIC = {">", "<", ">=", "<=", "=", "!=", "<>", "==",
                    "greater_than", "less_than",
                    "greater_than_or_equal", "less_than_or_equal",
                    "equals", "not_equals"}


def _safe_inline_formula_expression(field_name, table_name, schema):
    """Look up `field_name`'s formula_expression on `table_name` and return
    a `psycopg2.sql.SQL` fragment that inlines it as a column expression
    (e.g. `("quantity" * "unit_price")`). Returns None when the field
    isn't a formula, the expression uses unsafe characters, or any of
    the referenced identifiers aren't real columns on `table_name`.

    The whitelist is the same as `_matching_parents_via_formula_inline`:
    letters/digits/underscore, arithmetic ops, parens, decimal points,
    and whitespace. No quotes, no semicolons, no function calls.
    """
    if not field_name or not table_name or not schema:
        return None
    try:
        with connection.cursor() as _cur:
            _cur.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
            )
            _cur.execute(
                """
                SELECT formula_expression FROM fields
                WHERE name = %s AND datatype = 'formula'
                  AND object_name IN (%s, %s, %s)
                LIMIT 1
                """,
                [field_name, table_name, table_name.rstrip('s'), table_name + 's'],
            )
            row_ = _cur.fetchone()
    except Exception:
        return None
    if not row_ or not row_[0]:
        return None
    expr = row_[0]
    import re as _re
    # Whitelist: arithmetic + identifiers + parens + `,` for
    # multi-arg functions like `ROUND(x, 2)`. Without the comma the
    # whole formula was rejected the moment a saved formula used any
    # multi-arg function.
    if not _re.fullmatch(r"[A-Za-z0-9_+\-*/%(),.\s]+", expr):
        return None
    # SQL function names that appear in the expression but aren't
    # columns. Without this carve-out, formulas like
    # `ROUND(quantity * unit_price, 2)` failed the column-existence
    # check on `ROUND` and the rollup filter never got pushed to SQL.
    _FUNCTION_TOKENS = {
        "ROUND", "ABS", "CEIL", "FLOOR", "COALESCE", "GREATEST", "LEAST",
        "CASE", "WHEN", "THEN", "ELSE", "END", "IF", "AND", "OR", "NOT",
        "TRUE", "FALSE", "NULL", "IS", "IN", "BETWEEN", "LIKE", "ILIKE",
        "TO_CHAR", "EXTRACT", "DATE", "TIMESTAMP", "NULLIF",
    }
    identifiers = set(_re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr))
    for ident in identifiers:
        if ident.upper() in _FUNCTION_TOKENS:
            continue
        if not _column_exists(table_name, ident, schema):
            return None
    # Wrap in parens so SUM/AVG/MIN/MAX gets a single expression.
    return sql.SQL("(" + expr + ")")


def _matching_parents_via_aggregation(rollup_field, parent_table, op_sql, value, schema):
    """When a rollup_summary column isn't materialised, derive the matching
    parent IDs by running the equivalent aggregate predicate directly
    against the rollup's `summarized_object`:

        SELECT {parent_fk} FROM {summarized_object}
        GROUP BY {parent_fk}
        HAVING {rollup_type}({field_to_aggregate}) {op} %s

    Returns a list of parent IDs, or None when the fallback can't be
    constructed (missing metadata, unsupported op, missing physical
    column on the source table, etc.) so the caller can fall back further.
    """
    if not rollup_field or not parent_table or not schema:
        return None
    try:
        with connection.cursor() as _cur:
            _cur.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
            )
            _cur.execute(
                """
                SELECT summarized_object, rollup_type, field_to_aggregate
                FROM fields
                WHERE name = %s
                  AND datatype = 'rollup_summary'
                  AND object_name IN (%s, %s, %s)
                LIMIT 1
                """,
                [
                    rollup_field,
                    parent_table,
                    parent_table.rstrip('s'),
                    parent_table + 's',
                ],
            )
            row_ = _cur.fetchone()
        if not row_:
            return None
        summarized_object, rollup_type, field_to_aggregate = row_
        rollup_type = (rollup_type or "").upper()
        if rollup_type not in ("SUM", "COUNT", "MIN", "MAX", "AVG"):
            return None
        if rollup_type != "COUNT" and not field_to_aggregate:
            return None
        # If the source field isn't a real column, try inlining its
        # formula expression so SUM/MIN/MAX/AVG can still aggregate it.
        # That covers the common "rollup of a formula" shape (e.g.
        # invoice.grand_total = SUM(invoice_item.line_total) where
        # line_total = quantity * unit_price). Without this the export
        # silently returned 0 rows because the materialised parent
        # column was unset.
        agg_inner_sql = None
        if rollup_type != "COUNT":
            if _column_exists(summarized_object, field_to_aggregate, schema):
                agg_inner_sql = sql.SQL("{}").format(sql.Identifier(field_to_aggregate))
            else:
                expr_inner = _safe_inline_formula_expression(
                    field_to_aggregate, summarized_object, schema,
                )
                if expr_inner is None:
                    return None
                agg_inner_sql = expr_inner

        parent_fk = f"{parent_table}_id"
        if not _column_exists(summarized_object, parent_fk, schema):
            # Fallback FK naming variants; some schemas drop the trailing s.
            for candidate in (
                f"{parent_table.rstrip('s')}_id",
                f"{parent_table}s_id",
            ):
                if _column_exists(summarized_object, candidate, schema):
                    parent_fk = candidate
                    break
            else:
                return None

        if rollup_type == "COUNT":
            agg_sql = sql.SQL("COUNT(*)")
        else:
            agg_sql = sql.SQL("{}({})").format(
                sql.SQL(rollup_type), agg_inner_sql,
            )

        params = [value]
        if op_sql in ("IS NULL", "IS NOT NULL"):
            having_sql = sql.SQL("{} {}").format(agg_sql, sql.SQL(op_sql))
            params = []
        else:
            having_sql = sql.SQL("{} " + op_sql + " %s").format(agg_sql)

        query = sql.SQL(
            "SELECT {fk} FROM {tbl} "
            "WHERE {fk} IS NOT NULL "
            "GROUP BY {fk} HAVING {having}"
        ).format(
            fk=sql.Identifier(parent_fk),
            tbl=sql.Identifier(summarized_object),
            having=having_sql,
        )
        with transaction.atomic():
            with connection.cursor() as _cur:
                _cur.execute(
                    sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
                )
                _cur.execute(query, params)
                return [r[0] for r in _cur.fetchall()]
    except Exception:
        return None


def _column_exists(table_name, column_name, schema):
    """Return True iff `schema.table_name` has a physical column called
    `column_name`. Cached per-process so repeated rollup filters don't
    re-query information_schema. Used to gate SQL push-downs of computed
    filters: rollup_summary values are sometimes materialised into a
    column and sometimes not — pushing the predicate down on a missing
    column raises 'column does not exist' AND poisons the surrounding
    transaction."""
    if not table_name or not column_name or not schema:
        return False
    key = (schema, table_name, column_name)
    if key in _column_exists_cache:
        return _column_exists_cache[key]
    try:
        with connection.cursor() as _cur:
            _cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s AND column_name = %s
                LIMIT 1
                """,
                [schema, table_name, column_name],
            )
            exists = _cur.fetchone() is not None
    except Exception:
        exists = False
    _column_exists_cache[key] = exists
    return exists


def process_computed_fields_for_report(fields, table_name, schema):
    """
    Separate formula/rollup fields from physical fields for queries.
    Returns (physical_fields, computed_fields_metadata, extra_dependency_fields).
    """
    from api.formulas.functions_metadata import function_metadata as fm

    # Fetch ALL computed fields with full metadata across all objects (single query)
    all_computed = {}  # key: (object_name, field_name) -> meta
    computed_meta = {}  # current table's computed fields
    all_computed_names = set()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO %s", [schema])
            cursor.execute("""
                SELECT f.name, f.datatype, f.formula_expression, f.formula_return_type,
                       f.summarized_object, f.rollup_type, f.field_to_aggregate, f.filter_criteria,
                       f.object_name
                FROM fields f
                WHERE f.datatype IN ('formula', 'rollup_summary')
            """)
            for row in cursor.fetchall():
                all_computed_names.add(row[0])
                meta = {
                    "name": row[0], "datatype": row[1],
                    "formula_expression": row[2], "formula_return_type": row[3],
                    "summarized_object": row[4], "rollup_type": row[5],
                    "field_to_aggregate": row[6], "filter_criteria": row[7],
                    "object_name": row[8],
                }
                all_computed[(row[8], row[0])] = meta
                if row[8] == table_name:
                    computed_meta[row[0]] = meta
    except Exception as e:
        print(f"[DEBUG] Error fetching computed fields metadata: {e}")
        return fields, {}, []

    # Current table's computed field names
    current_table_computed = set(computed_meta.keys())

    physical_fields = []
    computed_fields = {}
    for f in fields:
        fname = f.get("name") if isinstance(f, dict) else f
        is_dot = '.' in fname
        base_field = fname.split('.')[-1] if is_dot else fname

        is_computed = False
        meta = None

        if not is_dot and base_field in current_table_computed:
            # Direct field on current table
            is_computed = True
            meta = dict(computed_meta[base_field])
        elif is_dot and base_field in all_computed_names:
            # Dot-notation: check related object
            relationship = fname.split('.')[0]
            for (obj_name, fld_name), obj_meta in all_computed.items():
                if fld_name == base_field and (
                    obj_name == relationship or
                    obj_name.rstrip('s') == relationship or
                    relationship.rstrip('s') == obj_name
                ):
                    is_computed = True
                    meta = dict(obj_meta)
                    meta["name"] = fname
                    break

        if is_computed and meta:
            if isinstance(f, dict):
                if f.get("aggregate"):
                    meta["aggregate"] = f["aggregate"]
                if f.get("alias"):
                    meta["alias"] = f["alias"]
            key = f.get("alias", fname) if isinstance(f, dict) and f.get("alias") else fname
            computed_fields[key] = meta
        else:
            physical_fields.append(f)

    # Build maps of formula and rollup fields on the current table
    table_formula_exprs = {}
    table_rollup_names = set()
    for (obj_name, fld_name), obj_meta in all_computed.items():
        if obj_name != table_name:
            continue
        if obj_meta.get("datatype") == "formula" and obj_meta.get("formula_expression"):
            table_formula_exprs[fld_name] = obj_meta["formula_expression"]
        elif obj_meta.get("datatype") == "rollup_summary":
            table_rollup_names.add(fld_name)

    def _extract_deps(expression, visited=None):
        """Recursively extract physical field dependencies from a formula expression."""
        if visited is None:
            visited = set()
        deps = set()
        tokens = re.findall(r'\b([a-zA-Z_]\w*)\b', expression)
        for token in tokens:
            if token in fm or token.replace('.', '').isdigit() or token in visited:
                continue
            visited.add(token)
            if token in table_formula_exprs:
                # Recursively expand formula dependency
                deps |= _extract_deps(table_formula_exprs[token], visited)
            elif token in table_rollup_names:
                # Rollup needs id to query child table — add it
                deps.add("id")
            else:
                deps.add(token)
        return deps

    extra_deps = set()
    for meta in computed_fields.values():
        field_name = meta.get("name", "")
        if meta["datatype"] == "formula" and meta.get("formula_expression"):
            extra_deps |= _extract_deps(meta["formula_expression"])
        # For related computed fields, ensure the foreign key is fetched
        if '.' in field_name:
            relationship = field_name.split('.')[0]
            extra_deps.add(f"{relationship}_id")

    existing = set()
    for f in physical_fields:
        existing.add(f.get("name") if isinstance(f, dict) else f)
    extra_deps -= existing
    extra_deps -= set(computed_fields.keys())
    # Also exclude any computed field names from extra_deps (they have no physical column)
    extra_deps -= all_computed_names

    return physical_fields, computed_fields, list(extra_deps)


# Per-process caches for computed-field name lookups. The `fields` table
# changes rarely (only when an object's schema is edited), and the report
# pipeline re-queries it on every filter and field classification — once
# at separate_computed_filters, again at process_computed_fields_for_report,
# again per filter inside convert_rollup_filters_to_physical, etc. On a
# 1L-row report request that's a dozen+ identical small queries adding
# round-trip latency to every preview load.
_ALL_COMPUTED_NAMES_CACHE: dict = {}
_FORMULA_ONLY_NAMES_CACHE: dict = {}
_TABLE_COMPUTED_NAMES_CACHE: dict = {}
_TABLE_FORMULA_ONLY_NAMES_CACHE: dict = {}


def invalidate_computed_field_caches():
    """Drop the per-process caches. Call after a field is added/removed
    or after a tenant's schema metadata changes."""
    _ALL_COMPUTED_NAMES_CACHE.clear()
    _FORMULA_ONLY_NAMES_CACHE.clear()
    _TABLE_COMPUTED_NAMES_CACHE.clear()
    _TABLE_FORMULA_ONLY_NAMES_CACHE.clear()


def _get_all_computed_field_names(schema=None):
    """Fetch all computed field names across all objects."""
    if schema in _ALL_COMPUTED_NAMES_CACHE:
        return _ALL_COMPUTED_NAMES_CACHE[schema]
    try:
        with connection.cursor() as cursor:
            if schema:
                cursor.execute("SET search_path TO %s", [schema])
            cursor.execute("""
                SELECT DISTINCT f.name FROM fields f
                WHERE f.datatype IN ('formula', 'rollup_summary')
            """)
            result = {row[0] for row in cursor.fetchall()}
    except Exception:
        result = set()
    _ALL_COMPUTED_NAMES_CACHE[schema] = result
    return result


def _get_formula_only_field_names(schema=None):
    """Fetch field names that are TRULY runtime-computed (formula only).
    Rollup_summary values are materialised into the column on write, so
    SQL can filter on them directly — they should NOT be classified as
    'computed' for filter-routing purposes."""
    if schema in _FORMULA_ONLY_NAMES_CACHE:
        return _FORMULA_ONLY_NAMES_CACHE[schema]
    try:
        with connection.cursor() as cursor:
            if schema:
                cursor.execute("SET search_path TO %s", [schema])
            cursor.execute("""
                SELECT DISTINCT f.name FROM fields f
                WHERE f.datatype = 'formula'
            """)
            result = {row[0] for row in cursor.fetchall()}
    except Exception:
        result = set()
    _FORMULA_ONLY_NAMES_CACHE[schema] = result
    return result


def _get_table_computed_field_names(table_name, schema=None):
    """Fetch computed field names for a specific table."""
    key = (schema, table_name)
    if key in _TABLE_COMPUTED_NAMES_CACHE:
        return _TABLE_COMPUTED_NAMES_CACHE[key]
    try:
        with connection.cursor() as cursor:
            if schema:
                cursor.execute("SET search_path TO %s", [schema])
            cursor.execute("""
                SELECT DISTINCT f.name FROM fields f
                WHERE f.object_name = %s AND f.datatype IN ('formula', 'rollup_summary')
            """, [table_name])
            result = {row[0] for row in cursor.fetchall()}
    except Exception:
        result = set()
    _TABLE_COMPUTED_NAMES_CACHE[key] = result
    return result


def _get_table_formula_only_field_names(table_name, schema=None):
    """Like _get_table_computed_field_names but limited to formulas."""
    key = (schema, table_name)
    if key in _TABLE_FORMULA_ONLY_NAMES_CACHE:
        return _TABLE_FORMULA_ONLY_NAMES_CACHE[key]
    try:
        with connection.cursor() as cursor:
            if schema:
                cursor.execute("SET search_path TO %s", [schema])
            cursor.execute("""
                SELECT DISTINCT f.name FROM fields f
                WHERE f.object_name = %s AND f.datatype = 'formula'
            """, [table_name])
            result = {row[0] for row in cursor.fetchall()}
    except Exception:
        result = set()
    _TABLE_FORMULA_ONLY_NAMES_CACHE[key] = result
    return result


def separate_computed_filters(filters, computed_field_names, schema=None, table_name=None):
    """
    Separate filters on computed fields from filters on physical fields.
    Handles nested AND/OR filter structures and dot-notation fields.
    Returns (physical_filters, computed_filters_list).
    """
    if not filters:
        return filters, []

    # Current table's computed field names — fetch from DB if table_name given
    current_computed = set(computed_field_names or set())
    if table_name:
        current_computed |= _get_table_computed_field_names(table_name, schema)

    # All computed field names (for dot-notation checks)
    try:
        all_computed = _get_all_computed_field_names(schema)
    except Exception:
        all_computed = set()

    if not current_computed and not all_computed:
        return filters, []

    computed_filters = []

    def _is_computed(field_name):
        if '.' in field_name:
            # Dot-notation: check last part against all computed fields
            base = field_name.split('.')[-1]
            return base in all_computed
        else:
            # Bare name: route to Python whenever the name matches ANY
            # known computed field (not just the current table's). The
            # field picker may emit a bare name for a rollup that lives on
            # a related table, or `object_name` in `fields` may not match
            # the report's `table_name` exactly (e.g. plural vs singular).
            # Letting it fall through as physical produces "column does
            # not exist" SQL errors — apply_computed_filters has lazy DB
            # lookup that handles bare names safely.
            return field_name in current_computed or field_name in all_computed

    def _process(tree):
        if isinstance(tree, dict):
            if 'and' in tree:
                physical = []
                for item in tree['and']:
                    result = _process(item)
                    if result is not None:
                        physical.append(result)
                if not physical:
                    return None
                return {'and': physical} if len(physical) > 1 else physical[0]
            elif 'or' in tree:
                physical = []
                for item in tree['or']:
                    result = _process(item)
                    if result is not None:
                        physical.append(result)
                if not physical:
                    return None
                return {'or': physical} if len(physical) > 1 else physical[0]
            elif 'field' in tree:
                if _is_computed(tree['field']):
                    computed_filters.append(tree)
                    return None
                return tree
            return tree
        elif isinstance(tree, list):
            physical = []
            for item in tree:
                result = _process(item)
                if result is not None:
                    physical.append(result)
            return physical if physical else []
        return tree

    physical = _process(filters)
    if physical is None:
        physical = []
    return physical, computed_filters


def convert_rollup_filters_to_physical(computed_filters, table_name, schema):
    """
    Eagerly resolve rollup_summary computed filters to physical FK-IN filters.

    For each filter like `invoice.grand_total > 100000` where `grand_total`
    is a rollup_summary on the parent table, this runs ONE
    `SELECT id FROM invoice WHERE grand_total > 100000` and returns a new
    filter `{field: invoice_id, operator: in, value: [...matching ids]}`
    that the main SQL builder can apply natively. The detail fetch then
    pulls only the rows we actually need — no need to over-fetch 5000+ rows
    just to throw most of them away in Python.

    Returns (extra_physical_filters, leftover_computed_filters).
    Filters not handled here (formulas, unsupported ops) stay in computed.
    """
    if not computed_filters or not table_name or not schema:
        return [], computed_filters

    SQL_PUSHABLE_OPS = {
        "=":  "=", "==": "=", "equals": "=",
        "!=": "!=", "<>": "!=", "not_equals": "!=",
        ">":  ">", "greater_than": ">",
        "<":  "<", "less_than": "<",
        ">=": ">=", "greater_than_or_equal": ">=",
        "<=": "<=", "less_than_or_equal": "<=",
        "is_null": "IS NULL", "is null": "IS NULL",
        "is_not_null": "IS NOT NULL", "is not null": "IS NOT NULL",
        "is_blank": "IS NULL", "is blank": "IS NULL",
        "is_not_blank": "IS NOT NULL", "is not blank": "IS NOT NULL",
    }

    extra_physical = []
    leftover = []

    # Resolve actual parent table name for a relationship once and cache.
    _parent_table_cache: dict[str, str] = {}

    def _resolve_parent_table(rel):
        if rel in _parent_table_cache:
            return _parent_table_cache[rel]
        parent = rel
        try:
            with connection.cursor() as _cur:
                _cur.execute(
                    sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
                )
                _cur.execute(
                    "SELECT name FROM object WHERE name = %s OR name = %s LIMIT 1",
                    [rel, rel + "s"],
                )
                row_ = _cur.fetchone()
                if row_:
                    parent = row_[0]
        except Exception:
            pass
        _parent_table_cache[rel] = parent
        return parent

    for f in computed_filters:
        fname = f.get("field") or ""
        op_raw = (f.get("operator") or "=").lower()
        if op_raw not in SQL_PUSHABLE_OPS:
            leftover.append(f)
            continue
        # Bare filter (e.g. just "grand_total"): the report's table IS the
        # parent that owns the rollup. Push the predicate down so SQL
        # handles the lakh-scale filter natively. If the column is
        # materialised on the report's own table, just emit the predicate
        # as-is (no FK rewrite needed) — that's what makes filters on
        # materialised formula columns avoid the 5000-row over-fetch +
        # Python pass.
        if "." not in fname:
            op_sql_bare = SQL_PUSHABLE_OPS[op_raw]
            value_bare = f.get("value")
            if op_raw in (">", "<", ">=", "<=", "greater_than", "less_than",
                          "greater_than_or_equal", "less_than_or_equal") and \
                    isinstance(value_bare, str):
                try:
                    value_bare = float(value_bare)
                except (TypeError, ValueError):
                    pass
            if _column_exists(table_name, fname, schema):
                # Native predicate on the materialised column.
                extra_physical.append({
                    "field": fname,
                    "operator": f.get("operator"),
                    "value": value_bare,
                })
                continue
            agg_ids = _matching_parents_via_aggregation(
                fname, table_name, op_sql_bare, value_bare, schema,
            )
            if agg_ids is None:
                # Aggregation refused — try inlining the formula
                # expression instead. This handles bare-name filters
                # on a *formula* field defined on the base table
                # (e.g. `grand_total` on invoice_item where the
                # formula is arithmetic on real columns). Without
                # this fallback the filter ends up in `leftover` and
                # the SUMMARY GROUP BY runs UNFILTERED — every
                # "Less Than 10000" filter silently became a no-op.
                formula_ids = _matching_parents_via_formula_inline(
                    fname, table_name, op_sql_bare, value_bare, schema,
                )
                if formula_ids is None:
                    leftover.append(f)
                    continue
                if not formula_ids:
                    extra_physical.append({"field": "id", "operator": "is_null", "value": None})
                    extra_physical.append({"field": "id", "operator": "is_not_null", "value": None})
                else:
                    extra_physical.append({"field": "id", "operator": "in", "value": formula_ids})
                continue
            if not agg_ids:
                extra_physical.append({"field": "id", "operator": "is_null", "value": None})
                extra_physical.append({"field": "id", "operator": "is_not_null", "value": None})
            else:
                extra_physical.append({"field": "id", "operator": "in", "value": agg_ids})
            continue
        # Confirm this is a rollup_summary on the related object.
        base = fname.split(".")[-1]
        rel = fname.split(".")[0]
        try:
            with connection.cursor() as _cur:
                _cur.execute(
                    sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
                )
                # Match plural/singular variants of `object_name` — the
                # `fields` table may store it as "invoices" while `rel`
                # comes from the FK relationship as "invoice".
                _cur.execute(
                    """
                    SELECT datatype FROM fields
                    WHERE name = %s AND datatype IN ('formula', 'rollup_summary')
                      AND object_name IN (%s, %s, %s)
                    LIMIT 1
                    """,
                    [base, rel, rel.rstrip("s"), rel + "s"],
                )
                row_ = _cur.fetchone()
        except Exception:
            row_ = None
        if not row_:
            leftover.append(f)
            continue
        field_datatype = row_[0]

        parent_table = _resolve_parent_table(rel)
        op_sql = SQL_PUSHABLE_OPS[op_raw]
        value = f.get("value")
        # Numeric ops on a numeric column choke when value arrives as the
        # JSON string "100000". Coerce to float when the op only makes sense
        # numerically and the string parses cleanly.
        if op_raw in (">", "<", ">=", "<=", "greater_than", "less_than",
                      "greater_than_or_equal", "less_than_or_equal") and \
                isinstance(value, str):
            try:
                value = float(value)
            except (TypeError, ValueError):
                pass
        # Resolve matching parent IDs, preferring source-of-truth paths
        # over the materialised rollup column (which can be stale or all
        # NULL when nothing has triggered the write-through yet — that's
        # the bug where every export came back with 0 rows).
        #   • rollup_summary → aggregate from the source table. Always
        #     reflects current data.
        #   • formula        → inline the expression. Falls through to
        #     `_column_exists` materialised path if the inline isn't safe.
        matching_ids = None
        column_materialised = _column_exists(parent_table, base, schema)
        if field_datatype == "rollup_summary":
            agg_ids = _matching_parents_via_aggregation(
                base, parent_table, op_sql, value, schema
            )
            if agg_ids is not None:
                matching_ids = agg_ids
        elif field_datatype == "formula":
            # Always try the inline path first — even when the column
            # is materialised on the parent. Materialised values are
            # often stale or all-NULL when the write-through hasn't
            # fired yet, so the materialised SQL would silently return
            # empty matching_ids and the filter would defer to leftover
            # (i.e. never apply). Inlining the formula expression
            # against current row data gives the correct match set
            # regardless of whether the parent column has been backfilled.
            formula_ids = _matching_parents_via_formula_inline(
                base, parent_table, op_sql, value, schema,
            )
            if formula_ids is not None:
                matching_ids = formula_ids
        if matching_ids is None and column_materialised:
            try:
                with transaction.atomic():
                    with connection.cursor() as _cur:
                        _cur.execute(
                            sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
                        )
                        if op_sql in ("IS NULL", "IS NOT NULL"):
                            _cur.execute(
                                sql.SQL(
                                    "SELECT id FROM {tbl} WHERE {col} " + op_sql
                                ).format(
                                    tbl=sql.Identifier(parent_table),
                                    col=sql.Identifier(base),
                                )
                            )
                        else:
                            _cur.execute(
                                sql.SQL(
                                    "SELECT id FROM {tbl} WHERE {col} " + op_sql + " %s"
                                ).format(
                                    tbl=sql.Identifier(parent_table),
                                    col=sql.Identifier(base),
                                ),
                                [value],
                            )
                        matching_ids = [r[0] for r in _cur.fetchall()]
            except Exception:
                matching_ids = None

        # Last-resort fallback: when every SQL-push path failed (rollup
        # source is a non-inlineable formula, materialised column is
        # missing/stale, etc.), compute the rollup in Python via
        # `evaluate_rollup_batch` and filter parent IDs that way. Only
        # fires when the parent set is small enough to evaluate without
        # blowing the request budget — otherwise we defer to Python
        # `apply_computed_filters` (which works on the already-fetched
        # detail rows, not the entire parent universe).
        FALLBACK_PARENT_CAP = 5000
        if (matching_ids is None or not matching_ids) and field_datatype == "rollup_summary":
            try:
                with connection.cursor() as _cur:
                    _cur.execute(
                        sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
                    )
                    _cur.execute(
                        """
                        SELECT summarized_object, rollup_type,
                               field_to_aggregate, filter_criteria
                        FROM fields
                        WHERE name = %s AND datatype = 'rollup_summary'
                          AND object_name IN (%s, %s, %s)
                        LIMIT 1
                        """,
                        [base, parent_table, parent_table.rstrip('s'), parent_table + 's'],
                    )
                    rmeta = _cur.fetchone()
                    # Fast count first — bail out before we materialise a
                    # 1L-row id list when the parent table is large.
                    _cur.execute(
                        sql.SQL("SELECT COUNT(*) FROM {tbl}").format(
                            tbl=sql.Identifier(parent_table)
                        )
                    )
                    parent_count = _cur.fetchone()[0]
                    if parent_count > FALLBACK_PARENT_CAP:
                        all_parent_ids = []
                    else:
                        _cur.execute(
                            sql.SQL("SELECT id FROM {tbl}").format(
                                tbl=sql.Identifier(parent_table)
                            )
                        )
                        all_parent_ids = [r[0] for r in _cur.fetchall()]
                if rmeta and all_parent_ids:
                    summarized_object, rollup_type, field_to_aggregate, filter_criteria = rmeta
                    from api.formulas.evaluate_rollup import evaluate_rollup_batch
                    values_by_parent = evaluate_rollup_batch(
                        record_ids=all_parent_ids,
                        summarized_object=summarized_object,
                        rollup_type=rollup_type,
                        field_to_aggregate=field_to_aggregate,
                        filter_criteria=filter_criteria,
                        parent_field=f"{parent_table}_id",
                        schema=schema,
                    )
                    cmp_ops = {
                        ">": lambda a, b: a is not None and a > b,
                        "<": lambda a, b: a is not None and a < b,
                        ">=": lambda a, b: a is not None and a >= b,
                        "<=": lambda a, b: a is not None and a <= b,
                        "=": lambda a, b: a == b,
                        "!=": lambda a, b: a != b,
                        "IS NULL": lambda a, b: a is None,
                        "IS NOT NULL": lambda a, b: a is not None,
                    }
                    cmp = cmp_ops.get(op_sql)
                    if cmp:
                        try:
                            cmp_value = float(value) if not isinstance(value, (int, float)) and value is not None else value
                        except (TypeError, ValueError):
                            cmp_value = value
                        matched = []
                        for pid in all_parent_ids:
                            v = values_by_parent.get(pid)
                            try:
                                v_num = float(v) if v is not None else None
                            except (TypeError, ValueError):
                                v_num = v
                            if cmp(v_num, cmp_value):
                                matched.append(pid)
                        matching_ids = matched
            except Exception:
                pass

        # When matching_ids is empty list (formula/aggregation ran but
        # no parent satisfies the predicate), emit a contradictory
        # filter so the main SELECT returns zero rows. Pushing this to
        # `leftover` (Python) doesn't help when DR is off / details are
        # skipped — the SUMMARY GROUP BY would run unfiltered and the
        # user sees every record despite their filter restricting to
        # "no matches" (the bug just flagged where 119k rows showed
        # up under a filter that should match 0).
        fk_col = f"{rel}_id"
        if matching_ids is None:
            leftover.append(f)
            continue
        if not matching_ids:
            extra_physical.append({"field": fk_col, "operator": "is_null", "value": None})
            extra_physical.append({"field": fk_col, "operator": "is_not_null", "value": None})
            continue

        extra_physical.append({
            "field": fk_col,
            "operator": "in",
            "value": matching_ids,
        })

    return extra_physical, leftover


def apply_computed_filters(records, computed_filters, computed_fields=None, table_name=None, schema=None):
    """
    Apply computed field filters in Python after values have been computed.

    `computed_fields` (optional) is the metadata map produced by
    `process_computed_fields_for_report`. When supplied, this function will
    LAZILY evaluate a filter's target field on the record if it isn't already
    present. That covers the case where the upstream
    `apply_computed_fields_to_records` step didn't produce the value (e.g.
    the FK column wasn't selected, or the field is on a related table that
    wasn't part of the detail SELECT) — without this fallback every record
    sees `None` for the filtered field and the whole result gets dropped.
    """
    if not computed_filters or not records:
        return records

    # Build a lookup so we can find the meta for a filter field by any of
    # the shapes it may appear under (alias key, dotted name, bare base).
    meta_by_alias = {}
    for alias, meta in (computed_fields or {}).items():
        meta_by_alias[alias] = meta
        if meta.get("name"):
            meta_by_alias[meta["name"]] = meta
            base = meta["name"].split(".")[-1]
            meta_by_alias.setdefault(base, meta)

    def _fetch_meta_from_db(field_name):
        """Last-resort: look up the field's metadata directly from `fields`
        when the caller didn't supply a `computed_fields` map (or supplied
        an empty one). Without this the lazy-eval below short-circuits and
        every row sees None for the filtered field."""
        if not schema:
            return None
        base = field_name.split(".")[-1] if "." in field_name else field_name
        relationship = field_name.split(".")[0] if "." in field_name else None
        try:
            with connection.cursor() as _cur:
                _cur.execute(
                    sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
                )
                # Try the related-object table first when the filter is
                # dotted; fall back to current table for direct fields.
                if relationship:
                    # Match plural/singular variants of `object_name`. The
                    # `fields` table sometimes stores it as the plural form
                    # ("invoices") while the filter uses the singular FK
                    # relationship ("invoice"); without the +'s' variant
                    # this lookup misses and the bulk SQL push downstream
                    # falls back to per-row evaluate_rollup (N+1).
                    _cur.execute(
                        """
                        SELECT name, datatype, formula_expression,
                               summarized_object, rollup_type, field_to_aggregate,
                               filter_criteria, object_name
                        FROM fields
                        WHERE name = %s AND datatype IN ('formula', 'rollup_summary')
                          AND object_name IN (%s, %s, %s)
                        LIMIT 1
                        """,
                        [base, relationship, relationship.rstrip('s'), relationship + 's'],
                    )
                else:
                    # Try the current table first, then plural/singular
                    # variants, and finally any object — `fields.object_name`
                    # is sometimes recorded as a plural (e.g. "invoices")
                    # while the report uses the singular form. Without this
                    # fallback a bare-name filter on a computed field whose
                    # `object_name` doesn't match the report's `table_name`
                    # can't be evaluated in Python and silently drops every
                    # row.
                    _cur.execute(
                        """
                        SELECT name, datatype, formula_expression,
                               summarized_object, rollup_type, field_to_aggregate,
                               filter_criteria, object_name
                        FROM fields
                        WHERE name = %s AND datatype IN ('formula', 'rollup_summary')
                          AND object_name IN (%s, %s, %s)
                        LIMIT 1
                        """,
                        [base, table_name, table_name.rstrip('s'), table_name + 's'],
                    )
                row_ = _cur.fetchone()
                if not row_ and not relationship:
                    _cur.execute(
                        """
                        SELECT name, datatype, formula_expression,
                               summarized_object, rollup_type, field_to_aggregate,
                               filter_criteria, object_name
                        FROM fields
                        WHERE name = %s AND datatype IN ('formula', 'rollup_summary')
                        LIMIT 1
                        """,
                        [base],
                    )
                    row_ = _cur.fetchone()
                if not row_:
                    return None
                return {
                    "name": field_name,
                    "datatype": row_[1],
                    "formula_expression": row_[2],
                    "summarized_object": row_[3],
                    "rollup_type": row_[4],
                    "field_to_aggregate": row_[5],
                    "filter_criteria": row_[6],
                    "object_name": row_[7],
                }
        except Exception:
            return None

    def _ensure_value(record, field_name):
        """Compute and store the field on the record if it isn't already."""
        if not field_name:
            return
        # Already populated under one of the recognised key shapes?
        candidate_keys = {field_name}
        if "." in field_name:
            candidate_keys.add(field_name.replace(".", "_"))
            candidate_keys.add(field_name.split(".")[-1])
        for k in candidate_keys:
            if record.get(k) is not None:
                return

        meta = meta_by_alias.get(field_name)
        if not meta:
            # Caller didn't pass a computed_fields map, or it didn't have
            # this field. Pull the metadata directly from the schema and
            # cache it so subsequent rows skip the round-trip.
            meta = _fetch_meta_from_db(field_name)
            if meta:
                meta_by_alias[field_name] = meta
                if meta.get("name"):
                    meta_by_alias[meta["name"]] = meta
                    meta_by_alias.setdefault(meta["name"].split(".")[-1], meta)
        if not meta:
            return
        # Lazy import to avoid circulars + only pay the import cost when
        # we actually need to evaluate.
        from api.formulas.evaluate_formula import process_formula
        from api.formulas.evaluate_rollup import evaluate_rollup
        try:
            mname = meta.get("name") or field_name
            if "." in mname:
                # Related-object computed field: resolve via FK.
                relationship = mname.split(".")[0]
                related_field = mname.split(".")[-1]
                parent_id = (
                    record.get(f"{relationship}_id")
                    or record.get(f"{relationship}s_id")
                )
                if not parent_id and isinstance(record.get(relationship), dict):
                    parent_id = record[relationship].get("id")
                # FK isn't on the row — fall back to a single-row SELECT on
                # the main table to fetch it. We need this because the
                # earlier extra_deps machinery sometimes folds the FK into a
                # JOIN alias and doesn't actually emit it as a column on the
                # result row, leaving downstream filters with no parent_id.
                if not parent_id and table_name and record.get("id"):
                    fk_col = f"{relationship}_id"
                    try:
                        with connection.cursor() as _cur:
                            if schema:
                                _cur.execute(
                                    sql.SQL("SET search_path TO {}").format(
                                        sql.Identifier(schema)
                                    )
                                )
                            _cur.execute(
                                sql.SQL("SELECT {fk} FROM {tbl} WHERE id = %s").format(
                                    fk=sql.Identifier(fk_col),
                                    tbl=sql.Identifier(table_name),
                                ),
                                [record["id"]],
                            )
                            row_ = _cur.fetchone()
                            if row_ and row_[0]:
                                parent_id = row_[0]
                                # Cache the FK back onto the record so the
                                # next filter on the same record skips this.
                                record[fk_col] = parent_id
                    except Exception:
                        pass
                if not parent_id:
                    return
                if meta.get("datatype") == "rollup_summary":
                    val = evaluate_rollup(
                        record_id=parent_id,
                        summarized_object=meta.get("summarized_object"),
                        rollup_type=meta.get("rollup_type"),
                        field_to_aggregate=meta.get("field_to_aggregate"),
                        filter_criteria=meta.get("filter_criteria"),
                        parent_object=relationship,
                        parent_field=f"{relationship}_id",
                        schema=schema,
                    )
                elif meta.get("datatype") == "formula" and meta.get("formula_expression"):
                    # For formulas we'd need the parent record; pulling it
                    # row-by-row is expensive. Skip — caller can opt into
                    # the full apply_computed_fields_to_records pass instead.
                    return
                else:
                    return
            else:
                # Direct computed field on the current table.
                if meta.get("datatype") == "rollup_summary" and record.get("id"):
                    val = evaluate_rollup(
                        record_id=record["id"],
                        summarized_object=meta.get("summarized_object"),
                        rollup_type=meta.get("rollup_type"),
                        field_to_aggregate=meta.get("field_to_aggregate"),
                        filter_criteria=meta.get("filter_criteria"),
                        parent_object=table_name,
                        parent_field=f"{table_name}_id",
                        schema=schema,
                    )
                elif meta.get("datatype") == "formula" and meta.get("formula_expression"):
                    val = process_formula(meta["formula_expression"], mname, record)
                else:
                    return
            if val is not None:
                # Write under every key shape so subsequent matchers + later
                # render code can read whichever they expect.
                for k in candidate_keys:
                    record[k] = val
        except Exception:
            # Lazy eval is best-effort. If it fails, the matcher below will
            # treat the field as None and that filter will exclude the row.
            pass

    def _matches(record, f):
        field = f.get('field')
        op = f.get('operator', '=')
        value = f.get('value')
        _ensure_value(record, field)
        # Try several key shapes — computed values land on the record under
        # the alias the SELECT used (e.g. dotted "invoice.grand_total" stored
        # as "invoice_grand_total"), or under just the bare field name when
        # no JOIN was needed. Without these fallbacks every comparison sees
        # None and the row gets filtered out.
        record_val = record.get(field)
        if record_val is None and field:
            alt_keys = []
            if "." in field:
                alt_keys.append(field.replace(".", "_"))
                alt_keys.append(field.split(".")[-1])
            for k in alt_keys:
                if k in record and record[k] is not None:
                    record_val = record[k]
                    break

        if op in ('is_null', 'is null'):
            return record_val is None
        if op in ('is_not_null', 'is not null'):
            return record_val is not None
        if op in ('is_blank', 'is blank'):
            return record_val is None or record_val == ''
        if op in ('is_not_blank', 'is not blank'):
            return record_val is not None and record_val != ''

        # Convert for comparison
        try:
            if isinstance(record_val, (int, float)) and value is not None:
                value = float(value)
        except (ValueError, TypeError):
            pass

        if op in ('=', '==', 'equals'):
            return record_val == value
        if op in ('!=', '<>', 'not_equals'):
            return record_val != value
        if op in ('>', 'greater_than'):
            return record_val is not None and record_val > value
        if op in ('<', 'less_than'):
            return record_val is not None and record_val < value
        if op in ('>=', 'greater_than_or_equal'):
            return record_val is not None and record_val >= value
        if op in ('<=', 'less_than_or_equal'):
            return record_val is not None and record_val <= value
        if op in ('contains', 'ilike'):
            return record_val is not None and str(value).lower() in str(record_val).lower()
        if op in ('not_contains', 'not_ilike'):
            return record_val is None or str(value).lower() not in str(record_val).lower()
        if op == 'in':
            return record_val in (value if isinstance(value, list) else [value])
        return True

    # ── Set-based bulk filter ──────────────────────────────────────────────
    # Push each rollup_summary computed filter into a SINGLE SQL query that
    # returns the parent IDs whose stored column satisfies the predicate.
    # Then keep records whose FK lands in that set. No per-row evaluate_rollup
    # call, no per-row record value lookup, no per-row DB round-trip — for a
    # 5k preview the whole filter resolves in 2 queries (FK batch + parent-id
    # batch) regardless of row count.
    SQL_PUSHABLE_OPS = {
        "=":  "=",
        "==": "=",
        "equals": "=",
        "!=": "!=",
        "<>": "!=",
        "not_equals": "!=",
        ">":  ">",
        "greater_than": ">",
        "<":  "<",
        "less_than": "<",
        ">=": ">=",
        "greater_than_or_equal": ">=",
        "<=": "<=",
        "less_than_or_equal": "<=",
        "is_null":      "IS NULL",
        "is null":      "IS NULL",
        "is_not_null":  "IS NOT NULL",
        "is not null":  "IS NOT NULL",
        "is_blank":     "IS NULL",
        "is blank":     "IS NULL",
        "is_not_blank": "IS NOT NULL",
        "is not blank": "IS NOT NULL",
    }

    sql_handled_filters = []        # list of computed_filter dicts handled by SQL
    fk_membership = []              # list of (fk_col, set_of_matching_parent_ids)
    if records and table_name and schema:
        # Resolve FK columns up-front for all rollup filters so a single
        # batch SELECT covers every record × every relationship the filters
        # mention, instead of one round-trip per (record, filter).
        rollup_specs = []  # (filter, fname, meta, fk_col, parent_table, parent_col)
        for f in computed_filters:
            fname = f.get("field") or ""
            op = (f.get("operator") or "=").lower()
            if "." not in fname or op not in SQL_PUSHABLE_OPS:
                continue
            meta = meta_by_alias.get(fname) or _fetch_meta_from_db(fname)
            # Accept both rollup_summary and formula here. The actual SQL
            # push at the bottom of this block bails when the column isn't
            # materialised on the parent table, so a non-materialised
            # formula correctly falls through to the Python fallback —
            # while a formula stored as a real column (computed at write
            # time) gets the same single-query treatment as a rollup.
            if not meta or meta.get("datatype") not in ("rollup_summary", "formula"):
                continue
            relationship = fname.split(".")[0]
            parent_col = fname.split(".")[-1]
            parent_table = relationship
            try:
                with connection.cursor() as _cur:
                    _cur.execute(
                        sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
                    )
                    _cur.execute(
                        "SELECT name FROM object WHERE name = %s OR name = %s LIMIT 1",
                        [relationship, relationship + "s"],
                    )
                    obj_row = _cur.fetchone()
                    if obj_row:
                        parent_table = obj_row[0]
            except Exception:
                pass
            fk_col = f"{relationship}_id"
            rollup_specs.append((f, fname, meta, fk_col, parent_table, parent_col))

        if rollup_specs:
            # ONE query: gather every missing FK across every record at once.
            fks_needed = {}  # fk_col -> set of record ids missing it
            for record in records:
                rid = record.get("id")
                if not rid:
                    continue
                for _, _, _, fk_col, _, _ in rollup_specs:
                    if not record.get(fk_col):
                        fks_needed.setdefault(fk_col, set()).add(rid)
            for fk_col, ids in fks_needed.items():
                if not ids:
                    continue
                try:
                    with connection.cursor() as _cur:
                        _cur.execute(
                            sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
                        )
                        _cur.execute(
                            sql.SQL(
                                "SELECT id, {fk} FROM {tbl} WHERE id = ANY(%s)"
                            ).format(
                                fk=sql.Identifier(fk_col),
                                tbl=sql.Identifier(table_name),
                            ),
                            [list(ids)],
                        )
                        fk_map = dict(_cur.fetchall())
                    for record in records:
                        rid = record.get("id")
                        if rid and not record.get(fk_col) and rid in fk_map:
                            record[fk_col] = fk_map[rid]
                except Exception:
                    pass

            # ONE query per filter: the predicate is evaluated server-side.
            # Returns only the parent IDs that match — no value list, no
            # Python comparison, no per-row work. We later keep records
            # whose FK is in the returned set.
            for f, fname, meta, fk_col, parent_table, parent_col in rollup_specs:
                op_raw = (f.get("operator") or "=").lower()
                op_sql = SQL_PUSHABLE_OPS[op_raw]
                value = f.get("value")
                # Coerce JSON-string numerics so Postgres doesn't compare
                # text against numeric (returns 0 rows or errors).
                if op_raw in (">", "<", ">=", "<=") and isinstance(value, str):
                    try:
                        value = float(value)
                    except (TypeError, ValueError):
                        pass
                # Restrict the SQL to parent IDs we actually have on records.
                parent_ids = {
                    record.get(fk_col)
                    for record in records
                    if record.get(fk_col)
                }
                if not parent_ids:
                    fk_membership.append((fk_col, set()))
                    sql_handled_filters.append(f)
                    continue

                # Prefer aggregation over the materialised column for
                # rollup_summary fields — the stored column may be stale
                # or all NULL when the write-through hasn't fired, which
                # silently dropped every export to 0 rows.
                matching_ids = None
                if (
                    meta.get("datatype") == "rollup_summary"
                    and op_sql not in ("IS NULL", "IS NOT NULL")
                ):
                    agg_ids = _matching_parents_via_aggregation(
                        parent_col, parent_table, op_sql, value, schema,
                    )
                    if agg_ids is not None:
                        matching_ids = {pid for pid in agg_ids if pid in parent_ids}

                if matching_ids is None:
                    if not _column_exists(parent_table, parent_col, schema):
                        # No materialised column to fall back on — defer
                        # to the per-record Python evaluator below.
                        continue
                    try:
                        with transaction.atomic():
                            with connection.cursor() as _cur:
                                _cur.execute(
                                    sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
                                )
                                if op_sql in ("IS NULL", "IS NOT NULL"):
                                    _cur.execute(
                                        sql.SQL(
                                            "SELECT id FROM {tbl} "
                                            "WHERE id = ANY(%s) AND {col} " + op_sql
                                        ).format(
                                            tbl=sql.Identifier(parent_table),
                                            col=sql.Identifier(parent_col),
                                        ),
                                        [list(parent_ids)],
                                    )
                                else:
                                    _cur.execute(
                                        sql.SQL(
                                            "SELECT id FROM {tbl} "
                                            "WHERE id = ANY(%s) AND {col} " + op_sql + " %s"
                                        ).format(
                                            tbl=sql.Identifier(parent_table),
                                            col=sql.Identifier(parent_col),
                                        ),
                                        [list(parent_ids), value],
                                    )
                                matching_ids = {row[0] for row in _cur.fetchall()}
                    except Exception:
                        continue

                fk_membership.append((fk_col, matching_ids))
                sql_handled_filters.append(f)

    # Drop SQL-handled filters from the Python pass; they're already done.
    remaining_filters = [f for f in computed_filters if f not in sql_handled_filters]

    # ── Batch prefill for the Python fallback ─────────────────────────────
    # When the SQL push above couldn't handle a filter (column not
    # materialised, op not pushable, exception), `_matches → _ensure_value`
    # would otherwise call `evaluate_rollup` once per record — N+1 in SQL.
    # Resolve each filter's target field across ALL records in a single
    # `evaluate_rollup_batch` call up front so the per-record `_ensure_value`
    # below becomes a no-op dict read.
    if remaining_filters and records and schema:
        from api.formulas.evaluate_rollup import evaluate_rollup_batch
        for f in remaining_filters:
            fname = f.get("field") or ""
            if not fname:
                continue
            meta = meta_by_alias.get(fname) or _fetch_meta_from_db(fname)
            if not meta or meta.get("datatype") != "rollup_summary":
                continue
            mname = meta.get("name") or fname
            if "." in mname:
                relationship = mname.split(".")[0]
                fk_a, fk_b = f"{relationship}_id", f"{relationship}s_id"
                # Backfill missing FKs in one SELECT (mirrors the SQL-push
                # block above) so we have parent ids to batch on.
                if table_name:
                    missing_fk_ids = {
                        r.get("id") for r in records
                        if r.get("id") and not (r.get(fk_a) or r.get(fk_b))
                        and not isinstance(r.get(relationship), dict)
                    }
                    if missing_fk_ids:
                        try:
                            with connection.cursor() as _cur:
                                _cur.execute(
                                    sql.SQL("SET search_path TO {}").format(sql.Identifier(schema))
                                )
                                _cur.execute(
                                    sql.SQL(
                                        "SELECT id, {fk} FROM {tbl} WHERE id = ANY(%s)"
                                    ).format(
                                        fk=sql.Identifier(fk_a),
                                        tbl=sql.Identifier(table_name),
                                    ),
                                    [list(missing_fk_ids)],
                                )
                                fk_map = dict(_cur.fetchall())
                            for r in records:
                                rid = r.get("id")
                                if rid in fk_map and not (r.get(fk_a) or r.get(fk_b)):
                                    r[fk_a] = fk_map[rid]
                        except Exception:
                            pass
                parent_ids = set()
                for r in records:
                    pid = r.get(fk_a) or r.get(fk_b)
                    if not pid and isinstance(r.get(relationship), dict):
                        pid = r[relationship].get("id")
                    if pid:
                        parent_ids.add(pid)
                if not parent_ids:
                    continue
                try:
                    values_by_parent = evaluate_rollup_batch(
                        record_ids=list(parent_ids),
                        summarized_object=meta.get("summarized_object"),
                        rollup_type=meta.get("rollup_type"),
                        field_to_aggregate=meta.get("field_to_aggregate"),
                        filter_criteria=meta.get("filter_criteria"),
                        parent_field=f"{relationship}_id",
                        schema=schema,
                    )
                except Exception:
                    values_by_parent = {}
                # Write under every key shape `_ensure_value` checks first.
                base = mname.split(".")[-1]
                key_shapes = {fname, mname, mname.replace(".", "_"), base}
                for r in records:
                    if any(r.get(k) is not None for k in key_shapes):
                        continue
                    pid = r.get(fk_a) or r.get(fk_b)
                    if not pid and isinstance(r.get(relationship), dict):
                        pid = r[relationship].get("id")
                    if pid is not None and pid in values_by_parent:
                        v = values_by_parent[pid]
                        for k in key_shapes:
                            r[k] = v
            else:
                # Bare rollup on the current table: batch over record ids.
                if not table_name:
                    continue
                rec_ids = [r.get("id") for r in records if r.get("id")]
                if not rec_ids:
                    continue
                try:
                    values_by_id = evaluate_rollup_batch(
                        record_ids=rec_ids,
                        summarized_object=meta.get("summarized_object"),
                        rollup_type=meta.get("rollup_type"),
                        field_to_aggregate=meta.get("field_to_aggregate"),
                        filter_criteria=meta.get("filter_criteria"),
                        parent_field=f"{table_name}_id",
                        schema=schema,
                    )
                except Exception:
                    values_by_id = {}
                for r in records:
                    if r.get(fname) is not None:
                        continue
                    rid = r.get("id")
                    if rid in values_by_id:
                        r[fname] = values_by_id[rid]

    # Apply the SQL-derived membership sets in one vectorised sweep — single
    # `all(...)` per record, no DB calls in the loop.
    filtered = []
    for record in records:
        # Each rollup-pushed filter must hit (FK in matching_ids).
        passed_sql = all(
            record.get(fk_col) in matching_ids
            for fk_col, matching_ids in fk_membership
        )
        if not passed_sql:
            continue
        if remaining_filters and not all(_matches(record, f) for f in remaining_filters):
            continue
        filtered.append(record)
    return filtered


def apply_computed_fields_to_records(records, computed_fields, table_name, schema):
    """
    Evaluate formula and rollup_summary fields on each record in the result set.
    """
    from api.formulas.evaluate_formula import process_formula
    from api.formulas.evaluate_rollup import evaluate_rollup, evaluate_rollup_batch

    # Fetch ALL formula AND rollup_summary fields on the current table.
    # This ensures formulas referencing other computed fields (e.g.
    # IF(total_amount > 100, ...) where total_amount is itself a formula
    # or rollup) resolve correctly.
    table_computed = {}  # name -> meta dict
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO %s", [schema])
            cursor.execute("""
                SELECT f.name, f.datatype, f.formula_expression,
                       f.summarized_object, f.rollup_type, f.field_to_aggregate, f.filter_criteria
                FROM fields f
                WHERE f.object_name = %s AND f.datatype IN ('formula', 'rollup_summary')
            """, [table_name])
            for row in cursor.fetchall():
                table_computed[row[0]] = {
                    "datatype": row[1],
                    "formula_expression": row[2],
                    "summarized_object": row[3],
                    "rollup_type": row[4],
                    "field_to_aggregate": row[5],
                    "filter_criteria": row[6],
                }
    except Exception as e:
        print(f"[DEBUG] Error fetching table computed fields: {e}")

    def _resolve_formula_deps(record):
        """Pre-compute all formula and rollup fields on the table."""
        for iteration in range(5):
            changed = False
            for fld, fmeta in table_computed.items():
                if fld in record and record[fld] is not None:
                    continue
                try:
                    if fmeta["datatype"] == "formula" and fmeta.get("formula_expression"):
                        val = process_formula(fmeta["formula_expression"], fld, record)
                    elif fmeta["datatype"] == "rollup_summary" and record.get("id"):
                        val = evaluate_rollup(
                            record_id=record["id"],
                            summarized_object=fmeta.get("summarized_object"),
                            rollup_type=fmeta.get("rollup_type"),
                            field_to_aggregate=fmeta.get("field_to_aggregate"),
                            filter_criteria=fmeta.get("filter_criteria"),
                            parent_object=table_name,
                            parent_field=f"{table_name}_id",
                            schema=schema,
                        )
                    else:
                        val = None
                    if val is not None:
                        record[fld] = val
                        changed = True
                except Exception:
                    pass
            if not changed:
                break

    # Separate plain computed fields from aggregated computed fields
    plain_fields = {k: v for k, v in computed_fields.items() if not v.get("aggregate")}
    agg_fields = {k: v for k, v in computed_fields.items() if v.get("aggregate")}

    # Batch-prefill rollups for the current table so we don't run one SQL per
    # record (N+1). Covers both the current-table rollups selected into
    # `plain_fields` AND any table-level rollups pulled in through
    # `_resolve_formula_deps` below.
    record_ids_all = [r.get("id") for r in records if r.get("id")]
    rollup_cache: dict = {}  # field_name -> {record_id: value}
    # Dot-notation rollups (e.g. "invoice.grand_total" on invoice_item):
    # field_name -> { relationship: str, parent_field_value_key: str,
    #   values: { parent_id: rollup_value } }
    related_rollup_cache: dict = {}
    if record_ids_all:
        rollup_specs = {}
        for fname, meta in plain_fields.items():
            if (
                meta.get("datatype") == "rollup_summary"
                and "." not in meta.get("name", fname)
            ):
                rollup_specs[fname] = meta
        for fld, fmeta in table_computed.items():
            if fmeta.get("datatype") == "rollup_summary" and fld not in rollup_specs:
                rollup_specs[fld] = fmeta
        for fname, meta in rollup_specs.items():
            try:
                rollup_cache[fname] = evaluate_rollup_batch(
                    record_ids=record_ids_all,
                    summarized_object=meta.get("summarized_object"),
                    rollup_type=meta.get("rollup_type"),
                    field_to_aggregate=meta.get("field_to_aggregate"),
                    filter_criteria=meta.get("filter_criteria"),
                    parent_field=f"{table_name}_id",
                    schema=schema,
                )
            except Exception as e:
                print(f"[DEBUG] batch rollup error for {fname}: {e}")
                rollup_cache[fname] = {}

        # Batch dot-notation rollups too. Without this, `invoice.grand_total`
        # on invoice_item rows triggers per-record SELECTs against the parent
        # object lookup AND a per-record evaluate_rollup call — N+1 in Python
        # AND in SQL. Group by (relationship, rollup spec), collect distinct
        # parent ids from the records once, batch-eval once.
        related_specs = {}  # field_name -> meta with relationship inferred
        for fname, meta in plain_fields.items():
            if meta.get("datatype") != "rollup_summary":
                continue
            mname = meta.get("name", fname)
            if "." not in mname:
                continue
            related_specs[fname] = meta

        for fname, meta in related_specs.items():
            mname = meta.get("name", fname)
            relationship = mname.split(".")[0]
            fk_keys = (f"{relationship}_id", f"{relationship}s_id")
            parent_ids = set()
            for rec in records:
                pid = rec.get(fk_keys[0]) or rec.get(fk_keys[1])
                if not pid and isinstance(rec.get(relationship), dict):
                    pid = rec[relationship].get("id")
                if pid:
                    parent_ids.add(pid)
            if not parent_ids:
                continue

            # Resolve the actual parent table name once.
            parent_table = relationship
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET search_path TO %s", [schema])
                    cursor.execute(
                        "SELECT name FROM object WHERE name = %s OR name = %s",
                        [relationship, relationship + "s"],
                    )
                    obj_row = cursor.fetchone()
                    if obj_row:
                        parent_table = obj_row[0]
            except Exception:
                pass

            try:
                values_by_parent = evaluate_rollup_batch(
                    record_ids=list(parent_ids),
                    summarized_object=meta.get("summarized_object"),
                    rollup_type=meta.get("rollup_type"),
                    field_to_aggregate=meta.get("field_to_aggregate"),
                    filter_criteria=meta.get("filter_criteria"),
                    parent_field=f"{parent_table}_id",
                    schema=schema,
                )
            except Exception as e:
                print(f"[DEBUG] batch related rollup error for {fname}: {e}")
                values_by_parent = {}

            related_rollup_cache[fname] = {
                "fk_keys": fk_keys,
                "relationship": relationship,
                "values": values_by_parent,
            }

    # Prefill each record's rollup values from the batch results so the
    # per-record fallbacks below become no-ops.
    if rollup_cache or related_rollup_cache:
        for record in records:
            rid = record.get("id")
            if rid:
                for fname, values in rollup_cache.items():
                    if fname in record and record[fname] is not None:
                        continue
                    if rid in values:
                        record[fname] = values[rid]
            for fname, spec in related_rollup_cache.items():
                if fname in record and record[fname] is not None:
                    continue
                fk_a, fk_b = spec["fk_keys"]
                pid = record.get(fk_a) or record.get(fk_b)
                if not pid and isinstance(record.get(spec["relationship"]), dict):
                    pid = record[spec["relationship"]].get("id")
                if pid is not None and pid in spec["values"]:
                    record[fname] = spec["values"][pid]

    for record in records:
        # Pre-compute all formula fields on the table so cross-references work
        _resolve_formula_deps(record)

        for fname, meta in plain_fields.items():
            field_name = meta.get("name", fname)

            # Handle dot-notation fields (e.g. "invoice.total_amount")
            # These are computed fields on a related/parent object
            is_related = '.' in field_name
            if is_related:
                # Skip if the batched dot-notation rollup pass already filled
                # this field — the fallback below otherwise re-issues a
                # parent-table SELECT + per-record evaluate_rollup, which is
                # the N+1 the batch was meant to eliminate.
                if record.get(fname) is not None:
                    continue
                parts = field_name.split('.')
                relationship = parts[0]  # e.g. "invoice"
                related_field = parts[-1]  # e.g. "total_amount"
                # Find parent record id via foreign key (e.g. invoice_id)
                parent_id = record.get(f"{relationship}_id") or record.get(f"{relationship}s_id")
                if not parent_id and isinstance(record.get(relationship), dict):
                    parent_id = record[relationship].get("id")
                if parent_id:
                    # print(f"[DEBUG] Computing related field '{fname}': relationship='{relationship}', related_field='{related_field}', parent_id='{parent_id}', datatype='{meta.get('datatype')}', summarized_object='{meta.get('summarized_object')}', rollup_type='{meta.get('rollup_type')}', field_to_aggregate='{meta.get('field_to_aggregate')}'")
                    try:
                        parent_data = {}
                        with connection.cursor() as cursor:
                            cursor.execute("SET search_path TO %s", [schema])
                            # Try to find the parent table name
                            cursor.execute("SELECT name FROM object WHERE name = %s OR name = %s", [relationship, relationship + 's'])
                            obj_row = cursor.fetchone()
                            parent_table = obj_row[0] if obj_row else relationship

                            cursor.execute(
                                sql.SQL("SELECT * FROM {} WHERE id = %s").format(sql.Identifier(parent_table)),
                                [parent_id]
                            )
                            row = cursor.fetchone()
                            if row:
                                cols = [desc[0] for desc in cursor.description]
                                parent_data = dict(zip(cols, row))

                        if meta["datatype"] == "formula" and meta.get("formula_expression"):
                            record[fname] = process_formula(
                                meta["formula_expression"], related_field, parent_data
                            )
                        elif meta["datatype"] == "rollup_summary" and parent_id:
                            record[fname] = evaluate_rollup(
                                record_id=parent_id,
                                summarized_object=meta.get("summarized_object"),
                                rollup_type=meta.get("rollup_type"),
                                field_to_aggregate=meta.get("field_to_aggregate"),
                                filter_criteria=meta.get("filter_criteria"),
                                parent_object=parent_table,
                                parent_field=f"{parent_table}_id",
                                schema=schema,
                            )
                    except Exception as e:
                        print(f"[DEBUG] Related computed field error for '{fname}': {e}")
                        record[fname] = None
                else:
                    print(f"[DEBUG] No parent_id found for '{fname}', relationship='{relationship}', record keys={list(record.keys())}")
                    record[fname] = None
                continue

            if meta["datatype"] == "formula" and meta.get("formula_expression"):
                try:
                    record[fname] = process_formula(
                        meta["formula_expression"], field_name, record
                    )
                except Exception:
                    record[fname] = None
            elif meta["datatype"] == "rollup_summary" and record.get("id"):
                if record.get(fname) is not None:
                    continue
                try:
                    record[fname] = evaluate_rollup(
                        record_id=record["id"],
                        summarized_object=meta.get("summarized_object"),
                        rollup_type=meta.get("rollup_type"),
                        field_to_aggregate=meta.get("field_to_aggregate"),
                        filter_criteria=meta.get("filter_criteria"),
                        parent_object=table_name,
                        parent_field=f"{table_name}_id",
                        schema=schema,
                    )
                except Exception as e:
                    print(f"[DEBUG] rollup error for {fname}: {e}")
                    record[fname] = None

    # Handle aggregated computed fields (e.g. SUM of a formula field)
    if agg_fields and records:
        # Compute the base value for each record first
        for record in records:
            for fname, meta in agg_fields.items():
                field_name = meta.get("name", fname)
                if meta["datatype"] == "formula" and meta.get("formula_expression"):
                    try:
                        record[f"_raw_{field_name}"] = process_formula(
                            meta["formula_expression"], field_name, record
                        )
                    except Exception:
                        record[f"_raw_{field_name}"] = 0
                elif meta["datatype"] == "rollup_summary" and record.get("id"):
                    try:
                        record[f"_raw_{field_name}"] = evaluate_rollup(
                            record_id=record["id"],
                            summarized_object=meta.get("summarized_object"),
                            rollup_type=meta.get("rollup_type"),
                            field_to_aggregate=meta.get("field_to_aggregate"),
                            filter_criteria=meta.get("filter_criteria"),
                            parent_object=table_name,
                            parent_field=f"{table_name}_id",
                            schema=schema,
                        )
                    except Exception:
                        record[f"_raw_{field_name}"] = 0

        # Compute aggregates across all records
        for fname, meta in agg_fields.items():
            field_name = meta.get("name", fname)
            alias = meta.get("alias", fname)
            aggregate = meta["aggregate"].lower()
            raw_key = f"_raw_{field_name}"
            values = [float(r.get(raw_key, 0) or 0) for r in records]

            if aggregate == "sum":
                agg_value = round(sum(values), 2)
            elif aggregate == "min":
                agg_value = round(min(values), 2) if values else 0
            elif aggregate == "max":
                agg_value = round(max(values), 2) if values else 0
            elif aggregate == "count":
                agg_value = len(values)
            elif aggregate == "avg":
                agg_value = round(sum(values) / len(values), 2) if values else 0
            else:
                agg_value = round(sum(values), 2)

            # Set aggregate value on all records (for summary rows)
            for record in records:
                record[alias] = agg_value

        # Clean up raw keys
        for record in records:
            for key in list(record.keys()):
                if key.startswith("_raw_"):
                    del record[key]

    return records
