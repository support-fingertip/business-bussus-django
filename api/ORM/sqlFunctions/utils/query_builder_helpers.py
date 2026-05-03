from datetime import datetime
from typing import Dict, List, Any, Union
from pypika import Table, Query, Order, Criterion, functions as fn
from pypika.terms import LiteralValue, ValueWrapper

FALLBACK_REL_TABLE_MAP = {
    "account": "accounts",
    "owner": "users",
    "created_by": "users",
    "last_modified_by": "users",
    "assigned_to": "users",
}

# ------------------------------
# Helper functions extracted
# ------------------------------

def get_aggregate_function(name: str, column):
    mapping = {
        "sum": fn.Sum,
        "count": fn.Count,
        "avg": fn.Avg,
        "min": fn.Min,
        "max": fn.Max,
        "string_agg": lambda col: fn.Function("STRING_AGG", col, "','"),
        "array_agg": lambda col: fn.Function("ARRAY_AGG", col),
    }
    func = mapping.get(name.lower()) 
    if func:
        return func(column)
    raise ValueError(f"Unsupported aggregation function: {name}")

def build_json_tree(tree: Dict[str, Any], tables, get_aggregate_function) -> fn.Function:
    args = []
    for key, val in tree.items():
        if val is None:
            args.extend([LiteralValue(f"'{key}'"), LiteralValue("null")])
            continue
        if isinstance(val, dict) and "field" in val:
            parts = val["field"].split(".")
            col = tables[parts[-2]][parts[-1]]
            if val["aggregate"]:
                col = get_aggregate_function(val["aggregate"], col)
            # For id fields, make sure to place them in their respective JSON object
            if parts[-1] == "id":
                # Assign a unique alias based on the table and field name to prevent collisions
                alias = f"{parts[-2]}_id"
                args.extend([LiteralValue(f"'{key}'"), col.as_(alias)])
            args.extend([LiteralValue(f"'{key}'"), col])
        else:
            args.extend([LiteralValue(f"'{key}'"), build_json_tree(val, tables, get_aggregate_function)])
    return fn.Function("jsonb_build_object", *args)

def generate_alias(alias_counter: int) -> str:
    """Generate a unique alias name."""
    return f"expr{alias_counter}"

def ensure_joins(query, tables, joins, path: List[str], relationships, base, base_table_name):
    """Ensure the required joins are added to the query."""
    path = list(path)
    if path and path[0] == base_table_name:
        path = path[1:]

    if not path:
        return query

    for i, part in enumerate(path):
        if part not in tables:
            tables[part] = Table(part)
        if i == 0:
            from_table = base
            from_name = base_table_name
        else:
            from_table = tables[path[i - 1]]
            from_name = path[i - 1]

        # Build full path key from base_table_name (matches build_relationship_chain)
        full_key = f"{base_table_name}.{'.'.join(path[:i+1])}"
        # Also try the short key for backwards compatibility (single-hop relationships)
        short_key = f"{from_name}.{part}"
        rel = relationships.get(full_key) or relationships.get(short_key)

        if rel is None:
            fk_col = part if part.endswith("_id") else f"{part}_id"
            to_table_name = FALLBACK_REL_TABLE_MAP.get(part, part)
            join_type = "left"
        elif isinstance(rel, str):
            fk_col = rel
            to_table_name = part
            join_type = "left"
        elif isinstance(rel, dict):
            fk_col = rel["key"]
            to_table_name = rel.get("table", part)
            join_type = rel.get("type", "left")
        else:
            raise ValueError(f"Invalid relationship config for key: {full_key}")

        to_table = Table(to_table_name).as_(part)
        tables[part] = to_table
        join_key = (from_table, to_table)

        if join_key not in joins:
            direction = rel.get("direction", "parent") if isinstance(rel, dict) else "parent"
            if direction == "child":
                # Child join: FK lives on the joined (child) table pointing back to from_table
                if join_type == "inner":
                    query = query.join(to_table).on(to_table[fk_col] == from_table.id)
                else:
                    query = query.left_join(to_table).on(to_table[fk_col] == from_table.id)
            else:
                # Parent join (default): FK lives on from_table pointing to joined table
                if join_type == "inner":
                    query = query.join(to_table).on(from_table[fk_col] == to_table.id)
                else:
                    query = query.left_join(to_table).on(from_table[fk_col] == to_table.id)
            joins[join_key] = True

    return query


def insert_into_tree(json_tree: Dict[str, Any], path: List[str], alias=None, aggregate=None):
    """Insert field path into json_tree for JSON aggregation."""
    tree = json_tree
    for i, part in enumerate(path):
        key = part if i < len(path) - 1 else alias or part
        if i == len(path) - 1:
            tree[key] = {"field": ".".join(path), "aggregate": aggregate}
        else:
            tree = tree.setdefault(part, {})


def resolve_field(field_path: str, base, base_table_name, tables, relationships, joins, query):
    """Resolve a field path into a table column, adding joins if needed."""
    parts = field_path.split(".")

    if parts and parts[0] == base_table_name:
        parts = parts[1:]

    if not parts:
        raise ValueError("Invalid field path")

    if len(parts) == 1:
        return base[parts[0]], query
    else:
        query = ensure_joins(query, tables, joins, parts[:-1], relationships, base, base_table_name)
        return tables[parts[-2]][parts[-1]], query


# def parse_condition(cond: Dict, clause_type, base, base_table_name, tables, relationships, joins, query, params: List):
#     """Parse a single condition into a Criterion."""
#     field, query = resolve_field(cond["field"], base, base_table_name, tables, relationships, joins, query)
#     value = cond["value"]
#     op = cond.get("operator", "=")

#     if clause_type in ("where", "having") and op not in ["in", "between"]:
#         params.append(value)

#     if op == "between":
#         start, end = value
#         params.extend([start, end])
#         return field.between(start, end), query
#     elif op == "in":
#         params.extend(value)
#         return field.isin(value), query
#     elif op == 'after':
#         if cond.get("cast", False) and cond.get("datatype") == 'timestamp':
#             value = datetime.fromisoformat(value)
#         params.append(value)
#         return field > value, query
#     elif op == 'before':
#         if cond.get("cast", False) and cond.get("datatype") == 'timestamp':
#             value = datetime.fromisoformat(value)
#         params.append(value)
#         return field < value, query
#     elif op == "not_in":    
#         params.extend(value)
#         return field.notin(value), query
#     elif op in ["ilike", "contains", "like"]:
#         params.append(value)
#         return field.ilike(f"%{value}%"), query        
#     elif op in "starts_with":
#         # params.append(value)
#         params.append(f"{value}%")
#         return field.like(f"{value}%"), query
#     elif op in ["not_starts_with"]:
#         params.append(value)
#         return field.not_ilike(f"{value}%"), query
#     elif op in ["not_contains"]:
#         params.append(value)
#         return field.not_ilike(f"%{value}%"), query
#     elif op in "not_ends_with":
#         params.append(value)
#         return field.not_ilike(f"%{value}"), query
#     elif op == 'equals':
#         if cond.get("cast", False) and cond.get("datatype") == 'timestamp':
#             return fn.Date(field) == value, query
#         params.append(value)
#         return field == value, query
#     elif op == 'not_equals':
#         if cond.get("cast", False) and cond.get("datatype") == 'timestamp':
#             return fn.Date(field) != value, query
#         params.append(value)
#         return field != value, query
#     elif op in ["not_contains", "not_ilike"]:
#         params.append(value)
#         return field.not_ilike(f"%{value}%"), query
#     elif op in "ends_with":
#         params.append(value)
#         return field.like(f"%{value}"), query
#     else:
#         return {
#             "=": field == value,             
#             "!=": field != value,
#             ">": field > value,
#             "greater_than": field > value,
#             "less_than": field < value,
#             "less_than_or_equal": field <= value,
#             "greater_than_or_equal": field >= value,
#             "<": field < value,
#             ">=": field >= value,
#             "<=": field <= value
#         }.get(op, field == value), query

from pypika.terms import Parameter

P = Parameter("%s")  # placeholder

def parse_condition(cond: Dict, clause_type, base, base_table_name, tables, relationships, joins, query, params: List):
    field, query = resolve_field(cond["field"], base, base_table_name, tables, relationships, joins, query)
    value = cond.get("value")
    op = cond.get("operator", "=")

    text_types = {"character varying", "varchar", "text", "citext"}

    def is_text_datatype() -> bool:
        return str(cond.get("datatype") or "").strip().lower() in text_types

    def cast_ts(v):
        if cond.get("cast") and cond.get("datatype") == "timestamp" and isinstance(v, str):
            return datetime.fromisoformat(v)
        return v

    # BETWEEN
    if op == "between":
        start, end = value
        start, end = cast_ts(start), cast_ts(end)
        params.extend([start, end])
        return field.between(Parameter("%s"), Parameter("%s")), query

    # DATE_RANGE — relative-date keyword (last_year / this_month / …)
    # The frontend's date filter pill stores `operator: "date_range"` with
    # the keyword in `value`. Without this branch the filter falls through
    # to the default-comparisons section below and gets emitted as
    # `<col> = 'last_year'`, which Postgres can't compare against a date
    # column — the filter silently doesn't apply, exactly the bug the
    # user just flagged. Resolve to (start, end) via the existing helper
    # and emit a BETWEEN.
    if op == "date_range":
        from api.ORM.sqlFunctions.utils.helpers import _resolve_relative_date
        # `all_time` is a no-op — emit a TRUE so AND-chains still
        # resolve (an unfiltered date counts as matching).
        if isinstance(value, str) and value.lower() == "all_time":
            return LiteralValue("TRUE"), query
        resolved = _resolve_relative_date(value) if isinstance(value, str) else None
        if resolved and resolved != "all_time":
            start, end = resolved
            params.extend([start, end])
            return field.between(Parameter("%s"), Parameter("%s")), query
        # Unknown keyword — fall through to a no-op so the rest of the
        # filter chain doesn't crash on an unmapped value.
        return LiteralValue("TRUE"), query

    # IN / NOT IN
    if op in ("in", "not_in"):
        vals = list(value or [])
        params.extend(vals)
        placeholders = [Parameter("%s") for _ in vals]
        crit = field.isin(placeholders)
        return (crit if op == "in" else ~crit), query

    # AFTER / BEFORE
    if op in ("after", "before"):
        v = cast_ts(value)
        params.append(v)
        return (field > Parameter("%s") if op == "after" else field < Parameter("%s")), query

    # CONTAINS / LIKE family
    if op in ("contains", "ilike"):
        params.append(f"%{value}%")
        return field.ilike(Parameter("%s")), query

    if op == "like":
        # caller provides full pattern
        params.append(value)
        return field.like(Parameter("%s")), query

    if op == "starts_with":
        params.append(f"{value}%")
        return field.ilike(Parameter("%s")), query

    if op == "ends_with":
        params.append(f"%{value}")
        return field.ilike(Parameter("%s")), query

    if op in ("not_contains", "not_ilike"):
        params.append(f"%{value}%")
        return field.not_ilike(Parameter("%s")), query

    if op == "not_starts_with":
        params.append(f"{value}%")
        return field.not_ilike(Parameter("%s")), query

    if op == "not_ends_with":
        params.append(f"%{value}")
        return field.not_ilike(Parameter("%s")), query

    # JSONB contains (@>)
    if op == "@>":
        params.append(value)
        return Criterion.all([LiteralValue(f'{field} @> %s::jsonb')]), query

    # NULL / BLANK checks (no params needed)
    if op == "is_null":
        return field.isnull(), query
    if op == "is_not_null":
        return field.notnull(), query
    if op == "is_blank":
        return Criterion.any([field.isnull(), field == LiteralValue("''")]), query
    if op == "is_not_blank":
        return Criterion.all([field.notnull(), field != LiteralValue("''")]), query

    # EQUALS / NOT EQUALS (with optional date cast)
    if op == "equals":
        v = cast_ts(value)
        params.append(v)
        if cond.get("cast") and cond.get("datatype") == "timestamp":
            return fn.Date(field) == Parameter("%s"), query
        if is_text_datatype():
            return fn.Lower(field) == fn.Lower(Parameter("%s")), query
        return field == Parameter("%s"), query

    if op == "not_equals":
        v = cast_ts(value)
        params.append(v)
        if cond.get("cast") and cond.get("datatype") == "timestamp":
            return fn.Date(field) != Parameter("%s"), query
        if is_text_datatype():
            return fn.Lower(field) != fn.Lower(Parameter("%s")), query
        return field != Parameter("%s"), query

    # DEFAULT comparisons
    v = cast_ts(value)
    if op in ("=", "=="):
        params.append(v); return field == Parameter("%s"), query
    if op in ("!=", "<>"):
        params.append(v); return field != Parameter("%s"), query
    if op in (">", "greater_than"):
        params.append(v); return field > Parameter("%s"), query
    if op in ("<", "less_than"):
        params.append(v); return field < Parameter("%s"), query
    if op in (">=", "greater_than_or_equal"):
        params.append(v); return field >= Parameter("%s"), query
    if op in ("<=", "less_than_or_equal"):
        params.append(v); return field <= Parameter("%s"), query

    # fallback
    params.append(v)
    return field == Parameter("%s"), query


def build_nested_criteria(tree: Union[Dict, List], clause_type, base, base_table_name, tables, relationships, joins, query, params: List):
    """Recursively build nested criteria with AND/OR/NOT logic."""
    LOGIC_KEYS = {"and", "or", "not"}

    if isinstance(tree, dict):
        keys = set(tree.keys())
        logic_keys = keys & LOGIC_KEYS

        if logic_keys:
            parts = []

            if "and" in tree:
                parts.append(Criterion.all([
                    build_nested_criteria(c, clause_type, base, base_table_name, tables, relationships, joins, query, params)
                    for c in tree["and"]
                ]))

            if "or" in tree:
                parts.append(Criterion.any([
                    build_nested_criteria(c, clause_type, base, base_table_name, tables, relationships, joins, query, params)
                    for c in tree["or"]
                ]))

            if "not" in tree:
                child = build_nested_criteria(
                            tree["not"],
                            clause_type, base, base_table_name,
                            tables, relationships, joins, query, params
                        )
                parts.append(~child)

            return Criterion.all(parts) if len(parts) > 1 else parts[0]

        return parse_condition(tree, clause_type, base, base_table_name, tables, relationships, joins, query, params)[0]

    elif isinstance(tree, list):
        return Criterion.all([
            build_nested_criteria(c, clause_type, base, base_table_name, tables, relationships, joins, query, params)
            for c in tree
        ])
    else:
        raise ValueError("Invalid clause structure")


def flatten_conditions(clause) -> List[str]:
    """Flatten nested conditions into a list of field names."""
    if isinstance(clause, dict):
        if "and" in clause:
            return sum([flatten_conditions(c) for c in clause["and"]], [])
        elif "or" in clause:
            return sum([flatten_conditions(c) for c in clause["or"]], [])
        elif "field" in clause:
            return [clause["field"]]
    elif isinstance(clause, list):
        return sum([flatten_conditions(c) for c in clause], [])
    return []
