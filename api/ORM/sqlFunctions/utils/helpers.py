from datetime import datetime
from typing import Dict, List, Any, Union
from pypika import Table, Query, Order, Criterion, functions as fn
from pypika.terms import LiteralValue
import re

# ------------------------------
# Helper functions extracted
# ------------------------------

def validate_identifier(identifier: str) -> str:
    """
    Validate a database identifier (table, column, schema name).
    Raises ValueError if the identifier contains unsafe characters.
    Returns the validated identifier.
    
    Note: PostgreSQL identifiers should start with a letter or underscore
    and contain only letters, digits, and underscores. Dollar signs are
    intentionally excluded for security reasons.
    """
    if not identifier:
        raise ValueError("Identifier cannot be empty")
    
    # Allow alphanumeric and underscore only (no dollar sign for security)
    # Must start with letter or underscore
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier):
        raise ValueError(f"Invalid identifier: {identifier}. Only alphanumeric characters and underscores are allowed, and it must start with a letter or underscore.")
    
    return identifier

def get_aggregate_function(name: str, column):
    from pypika.terms import LiteralValue

    def _median(col):
        # PostgreSQL has no MEDIAN aggregate — use the ordered-set
        # PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY col). PyPika doesn't
        # model WITHIN GROUP, so we emit the whole expression as a literal
        # term. fn.Function("…literal…") would append a stray "()" because
        # it always renders as `name(args)`; LiteralValue avoids that.
        col_sql = (
            col.get_sql(with_alias=False, quote_char='"')
            if hasattr(col, "get_sql")
            else f'"{col}"'
        )
        return LiteralValue(
            f'PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY {col_sql})'
        )

    mapping = {
        "sum": fn.Sum,
        "count": fn.Count,
        "avg": fn.Avg,
        "min": fn.Min,
        "max": fn.Max,
        "median": _median,
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

# def ensure_joins(query, tables, joins, path: List[str], relationships, base, base_table_name):
#     """Ensure the required joins are added to the query."""
#     for i, part in enumerate(path):
#         if part not in tables:
#             tables[part] = Table(part)
#         if i == 0:
#             from_table = base
#             from_name = base_table_name
#         else:
#             from_table = tables[path[i - 1]]
#             from_name = path[i - 1]

#         key = f"{from_name}.{part}"
#         rel = relationships.get(key)

#         if rel is None:
#             fk_col = f"{part}"
#             to_table_name = part
#             join_type = "left"
#         elif isinstance(rel, str):
#             fk_col = rel
#             to_table_name = part
#             join_type = "left"
#         elif isinstance(rel, dict):
#             fk_col = rel["key"]
#             to_table_name = rel.get("table", part)
#             join_type = rel.get("type", "left")
#         else:
#             raise ValueError(f"Invalid relationship config for key: {key}")

#         to_table = Table(to_table_name).as_(part)
#         tables[part] = to_table
#         join_key = (from_table, to_table)

#         if join_key not in joins:
#             if join_type == "inner":
#                 query = query.join(to_table).on(from_table[fk_col] == to_table.id)
#             else:
#                 query = query.left_join(to_table).on(from_table[fk_col] == to_table.id)
#             joins[join_key] = True

#     return query


from pypika import Table

FALLBACK_REL_TABLE_MAP = {
    "account": "accounts",
    "owner": "users",
    "created_by": "users",
    "last_modified_by": "users",
    "assigned_to": "users",
}

def ensure_joins(query, tables, joins, path, relationships, base, base_table_name):
    path = list(path)
    if path and path[0] == base_table_name:
        path = path[1:]

    if not path:
        return query

    alias_map = joins.setdefault("__alias_map__", {})

    from_table = base
    prefix = base_table_name  # used for relationship keys like invoice_item.invoice, invoice.created_by

    for part in path:
        rel_key = f"{prefix}.{part}"

        # already joined
        if rel_key in alias_map:
            from_table = tables[alias_map[rel_key]]
            prefix = part
            continue

        rel = relationships.get(rel_key)

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
            raise ValueError(f"Invalid relationship config for key: {rel_key}")

        # ✅ unique alias per rel_key
        join_alias = rel_key.replace(".", "__")  # invoice__created_by, invoice_item__created_by, etc.

        to_table = Table(to_table_name).as_(join_alias)
        tables[join_alias] = to_table
        alias_map[rel_key] = join_alias

        direction = rel.get("direction", "parent") if isinstance(rel, dict) else "parent"
        if direction == "child":
            # Child join: FK lives on the joined (child) table pointing back to from_table
            # e.g. accounts LEFT JOIN leads ON leads.accounts_id = accounts.id
            if join_type == "inner":
                query = query.join(to_table).on(to_table[fk_col] == from_table.id)
            else:
                query = query.left_join(to_table).on(to_table[fk_col] == from_table.id)
        else:
            # Parent join (default): FK lives on from_table pointing to joined table
            # e.g. leads LEFT JOIN accounts ON leads.accounts_id = accounts.id
            if join_type == "inner":
                query = query.join(to_table).on(from_table[fk_col] == to_table.id)
            else:
                query = query.left_join(to_table).on(from_table[fk_col] == to_table.id)

        from_table = to_table
        prefix = part

    return query


def resolve_field(field_path: str, base, base_table_name, tables, relationships, joins, query):
    parts = field_path.split(".")

    if parts and parts[0] == base_table_name:
        parts = parts[1:]

    if not parts:
        raise ValueError("Invalid field path")

    if len(parts) == 1:
        return base[parts[0]], query

    query = ensure_joins(query, tables, joins, parts[:-1], relationships, base, base_table_name)

    alias_map = joins.get("__alias_map__", {})
    prefix = base_table_name
    last_alias = None

    for rel in parts[:-1]:
        rel_key = f"{prefix}.{rel}"
        last_alias = alias_map[rel_key]
        prefix = rel

    return tables[last_alias][parts[-1]], query



def insert_into_tree(json_tree: Dict[str, Any], path: List[str], alias=None, aggregate=None):
    """Insert field path into json_tree for JSON aggregation."""
    tree = json_tree
    for i, part in enumerate(path):
        key = part if i < len(path) - 1 else alias or part
        if i == len(path) - 1:
            tree[key] = {"field": ".".join(path), "aggregate": aggregate}
        else:
            tree = tree.setdefault(part, {})


# def resolve_field(field_path: str, base, base_table_name, tables, relationships, joins, query):
#     """Resolve a field path into a table column, adding joins if needed."""
#     parts = field_path.split(".")
#     if len(parts) == 1:
#         return base[parts[0]], query
#     else:
#         query = ensure_joins(query, tables, joins, parts[:-1], relationships, base, base_table_name)
#         print(tables[parts[-2]][parts[-1]], parts)
#         return tables[parts[-2]][parts[-1]], query


def _resolve_relative_date(value):
    """
    Convert relative date keywords (e.g. 'last_7_days', 'this_week') into a
    (start_date, end_date) tuple, or return None if value is not a keyword.
    """
    if not isinstance(value, str):
        return None

    from datetime import date, timedelta

    today = date.today()
    weekday = today.weekday()  # Monday=0, Sunday=6
    week_start = today - timedelta(days=weekday)  # Monday

    mapping = {
        # Day
        "today": (today, today),
        "yesterday": (today - timedelta(days=1), today - timedelta(days=1)),
        "tomorrow": (today + timedelta(days=1), today + timedelta(days=1)),
        # Week (Mon-Sun)
        "this_week": (week_start, week_start + timedelta(days=6)),
        "last_week": (week_start - timedelta(days=7), week_start - timedelta(days=1)),
        "next_week": (week_start + timedelta(days=7), week_start + timedelta(days=13)),
        # Month
        "this_month": (today.replace(day=1), (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)),
        "last_month": ((today.replace(day=1) - timedelta(days=1)).replace(day=1), today.replace(day=1) - timedelta(days=1)),
        "next_month": ((today.replace(day=28) + timedelta(days=4)).replace(day=1),
                        ((today.replace(day=28) + timedelta(days=4)).replace(day=1).replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)),
        # Quarter
        "this_quarter": (date(today.year, (today.month - 1) // 3 * 3 + 1, 1),
                         date(today.year, (today.month - 1) // 3 * 3 + 3, 1).replace(day=28) + timedelta(days=4)),
        "last_quarter": (date(today.year if today.month > 3 else today.year - 1,
                              ((today.month - 1) // 3 * 3 - 2) if today.month > 3 else 10, 1),
                         date(today.year, (today.month - 1) // 3 * 3 + 1, 1) - timedelta(days=1)),
        "next_quarter": None,  # computed below
        # Year
        "this_year": (date(today.year, 1, 1), date(today.year, 12, 31)),
        "last_year": (date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)),
        "next_year": (date(today.year + 1, 1, 1), date(today.year + 1, 12, 31)),
        # Rolling
        "last_7_days": (today - timedelta(days=7), today),
        "last_30_days": (today - timedelta(days=30), today),
        "last_60_days": (today - timedelta(days=60), today),
        "last_90_days": (today - timedelta(days=90), today),
        "next_7_days": (today, today + timedelta(days=7)),
        "next_30_days": (today, today + timedelta(days=30)),
    }

    # Fix this_quarter end date
    if "this_quarter" in mapping and mapping["this_quarter"]:
        q_start, q_end_raw = mapping["this_quarter"]
        mapping["this_quarter"] = (q_start, (q_end_raw).replace(day=1) - timedelta(days=1))

    # Compute next_quarter
    current_q_end = mapping.get("this_quarter", (None, None))[1]
    if current_q_end:
        nq_start = current_q_end + timedelta(days=1)
        nq_end = (date(nq_start.year, nq_start.month + 2, 28) + timedelta(days=4)).replace(day=1) - timedelta(days=1) if nq_start.month <= 10 else date(nq_start.year, 12, 31)
        mapping["next_quarter"] = (nq_start, nq_end)

    if value == "all_time":
        return "all_time"

    return mapping.get(value)


def _coerce_numeric(value):
    """Convert string values to numbers when possible for correct SQL comparisons."""
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return value
    return value


def _is_date_string(value: str) -> bool:
    """Check if a string looks like a date (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)."""
    import re
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}", value))


def parse_condition(cond: Dict, clause_type, base, base_table_name, tables, relationships, joins, query, params: List):
    """Parse a single condition into a Criterion."""
    field, query = resolve_field(cond["field"], base, base_table_name, tables, relationships, joins, query)
    value = cond["value"]
    op = cond.get("operator", "=")

    # NULL / BLANK checks — these ignore `value` entirely. Must be handled
    # before any value coercion or date parsing, otherwise an empty `value`
    # gets cast to the column type (e.g. '' → timestamp) and Postgres errors.
    if op in ("is_null", "is null"):
        return field.isnull(), query
    if op in ("is_not_null", "is not null"):
        return field.notnull(), query
    if op in ("is_blank", "is blank"):
        return (field.isnull() | (field == "")), query
    if op in ("is_not_blank", "is not blank"):
        return (field.notnull() & (field != "")), query

    # Resolve relative date keywords (e.g. "last_7_days", "this_month") into date ranges
    relative = _resolve_relative_date(value)
    if relative == "all_time":
        # No date filter needed — return a tautology
        return LiteralValue("1=1"), query
    if relative is not None:
        start_date, end_date = relative
        start_str = start_date.isoformat()
        end_str = end_date.isoformat()
        params.extend([start_str, end_str])
        return field.between(start_str, end_str), query

    # Detect comma-separated date range strings (e.g. "2025-02-03,2026-04-02")
    if isinstance(value, str) and "," in value:
        parts = value.split(",", 1)
        if len(parts) == 2 and _is_date_string(parts[0].strip()) and _is_date_string(parts[1].strip()):
            start_str = parts[0].strip()
            end_str = parts[1].strip()
            params.extend([start_str, end_str])
            return field.between(start_str, end_str), query

    # Coerce numeric strings for comparison operators to avoid string comparison
    NUMERIC_OPS = {">", "<", ">=", "<=", "=", "!=", "greater_than", "less_than",
                   "greater_than_or_equal", "less_than_or_equal", "between", "after", "before"}
    if op in NUMERIC_OPS:
        if isinstance(value, list):
            value = [_coerce_numeric(v) for v in value]
        else:
            value = _coerce_numeric(value)

    if clause_type in ("where", "having") and op not in ["in", "between"]:
        params.append(value)

    if op == "between":
        start, end = value
        params.extend([start, end])
        return field.between(start, end), query
    elif op == "in":
        params.extend(value)
        return field.isin(value), query
    elif op == 'after':
        if cond.get("cast", False) and cond.get("datatype") == 'timestamp':
            value = datetime.fromisoformat(value)
        params.append(value)
        return field > value, query
    elif op == 'before':
        if cond.get("cast", False) and cond.get("datatype") == 'timestamp':
            value = datetime.fromisoformat(value)
        params.append(value)
        return field < value, query
    elif op == "not_in":    
        params.extend(value)
        return field.notin(value), query
    elif op in ["ilike", "contains", "like"]:
        params.append(value)
        return field.ilike(f"%{value}%"), query        
    elif op in "starts_with":
        params.append(value)
        return field.like(f"{value}%"), query
    elif op in ["not_starts_with"]:
        params.append(value)
        return field.not_ilike(f"{value}%"), query
    elif op in ["not_contains"]:
        params.append(value)
        return field.not_ilike(f"%{value}%"), query
    elif op in "not_ends_with":
        params.append(value)
        return field.not_ilike(f"%{value}"), query
    elif op == 'equals':
        if cond.get("cast", False) and cond.get("datatype") == 'timestamp':
            return fn.Date(field) == value, query
        params.append(value)
        return field == value, query
    elif op == 'not_equals':
        if cond.get("cast", False) and cond.get("datatype") == 'timestamp':
            return fn.Date(field) != value, query
        params.append(value)
        return field != value, query
    elif op in ["not_contains", "not_ilike"]:
        params.append(value)
        return field.not_ilike(f"%{value}%"), query
    elif op in "ends_with":
        params.append(value)
        return field.like(f"%{value}"), query
    else:
        return {
            "=": field == value,             
            "!=": field != value,
            ">": field > value,
            "greater_than": field > value,
            "less_than": field < value,
            "less_than_or_equal": field <= value,
            "greater_than_or_equal": field >= value,
            "<": field < value,
            ">=": field >= value,
            "<=": field <= value
        }.get(op, field == value), query


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
                parts.append(Criterion.not_(
                    build_nested_criteria(tree["not"], clause_type, base, base_table_name, tables, relationships, joins, query, params)
                ))

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
