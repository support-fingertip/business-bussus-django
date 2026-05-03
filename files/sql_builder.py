# This works with complex multi level parent in select, where and group by with auto aliasing with direct text in group by


import json
from django.db import connection
from pypika import Table, Query, Order, Criterion, functions as fn
from pypika.terms import LiteralValue
from typing import Dict, List, Tuple, Any, Union

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
        if isinstance(val, dict) and "field" in val:
            parts = val["field"].split(".")
            col = tables[parts[-2]][parts[-1]]
            if val["aggregate"]:
                col = get_aggregate_function(val["aggregate"], col)
            args.extend([LiteralValue(f"'{key}'"), col])
        else:
            args.extend([LiteralValue(f"'{key}'"), build_json_tree(val, tables, get_aggregate_function)])
    return fn.Function("jsonb_build_object", *args)

def build_query(input_data: Dict) -> Tuple[str, List[Any], Dict]:
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
    relationship_output = input_data.get("relationship_output", "flat")
    alias_mode = input_data.get("aliasing", "auto")

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



    def generate_alias():
        nonlocal alias_counter
        alias = f"expr{alias_counter}"
        alias_counter += 1
        return alias

    def ensure_joins(path: List[str]):
        nonlocal query
        for i, part in enumerate(path):
            if part not in tables:
                tables[part] = Table(part)

            if i == 0:
                from_table = base
                from_name = base_table_name
            else:
                from_table = tables[path[i - 1]]
                from_name = path[i - 1]

            key = f"{from_name}.{part}"
            rel = relationships.get(key)

            if rel is None:
                fk_col = f"{part}_id"
                to_table_name = part
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
                raise ValueError(f"Invalid relationship config for key: {key}")

            to_table = Table(to_table_name).as_(part)
            tables[part] = to_table
            join_key = (from_table, to_table)

            if join_key not in joins:
                if join_type == "inner":
                    query = query.join(to_table).on(from_table[fk_col] == to_table.id)
                else:
                    query = query.left_join(to_table).on(from_table[fk_col] == to_table.id)
                joins[join_key] = True

    def insert_into_tree(path: List[str], alias=None, aggregate=None):
        tree = json_tree
        for i, part in enumerate(path):
            key = part + "" if i < len(path) - 1 else alias or part
            if i == len(path) - 1:
                tree[key] = {"field": ".".join(path), "aggregate": aggregate}
            else:
                tree = tree.setdefault(part, {})
 
    def resolve_field(field_path: str):
        if field_path in alias_map:
            if(alias_map[field_path] ==  field_path):
                return base[field_path] 
            else:
                return resolve_field(alias_map[field_path])

        parts = field_path.split(".")
        if len(parts) == 1:
            return base[parts[0]]
        else:
            ensure_joins(parts[:-1])
            return tables[parts[-2]][parts[-1]]

    def parse_condition(cond: Dict, clause_type="where") -> Criterion:
        field = resolve_field(cond["field"])
        value = cond["value"]
        op = cond.get("operator", "=")

        if clause_type in ("where", "having") and op not in ["in", "between"]:
            params.append(value)

        if op == "between":
            start, end = value
            params.extend([start, end])
            return field.between(start, end)
        elif op == "in":
            params.extend(value)
            return field.isin(value)
        elif op == "like":
            params.append(value)
            return field.like(value)
        else:
            return {
                "=": field == value,
                "!=": field != value,
                ">": field > value,
                "<": field < value,
                ">=": field >= value,
                "<=": field <= value
            }.get(op, field == value)

    def build_nested_criteria(tree: Union[Dict, List], clause_type="where") -> Criterion:
        if isinstance(tree, dict):
            if "and" in tree:
                return Criterion.all([build_nested_criteria(c, clause_type) for c in tree["and"]])
            elif "or" in tree:
                return Criterion.any([build_nested_criteria(c, clause_type) for c in tree["or"]])
            else:
                return parse_condition(tree, clause_type)
        elif isinstance(tree, list):
            return Criterion.all([build_nested_criteria(c, clause_type) for c in tree])
        else:
            raise ValueError("Invalid clause structure")

    def flatten_conditions(clause) -> List[str]:
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

    select_fields = []
    all_fields = []
    for f in fields:
        if isinstance(f, str):
            all_fields.append(f)
        elif isinstance(f, dict) and "name" in f:
            all_fields.append(f["name"])

    all_fields += flatten_conditions(where_clauses) + flatten_conditions(having_clauses) + group_by

    for field in all_fields:
        parts = field.split(".")
        if len(parts) > 1:
            ensure_joins(parts[:-1])

    for f in fields:
        if isinstance(f, str):
            name = f
            if alias_mode == "none":
                alias = name.split(".")[-1]
            elif alias_mode == "auto":
                alias = generate_alias()
            else:
                raise ValueError(f"Explicit alias required for field: {name}")
            col = resolve_field(name)
            select_fields.append(col.as_(alias))
            alias_map[alias] = name
            if relationship_output == "json" : 
                parts = name.split(".")
                if not alias:
                    alias = generate_alias() if alias_mode == "auto" else ( name + "_"+  agg ) 
                insert_into_tree(parts, alias=alias)
                if alias != parts[0] and mapped_aliases.get(parts[0]) is None:
                    json_aliases[alias] = parts[0]
                    mapped_aliases[parts[0]] = parts[0]
        elif isinstance(f, dict):
            name = f["name"]
            alias = f.get("alias")
            if f.get("expression", False):
                if not alias:
                    alias = generate_alias() if alias_mode == "auto" else ( name + "_"+  agg )
                select_fields.append(fn.Function("", name).as_(alias))
                alias_map[alias] = name
                continue
            agg = f.get("aggregate")
            if agg:
                if name in alias_map:
                    raise ValueError(f"Aggregates must apply to base fields only, not aliases: {name}")
                if not alias:
                    alias = generate_alias() if alias_mode == "auto" else ( name + "_"+  agg )
                col = resolve_field(name)
                col = get_aggregate_function(agg, col)
                select_fields.append(col.as_(alias))              
                alias_map[alias] = name
            elif relationship_output == "json" and name.endswith("__r"):
                parts = name.split(".")
                if not alias:
                    alias = generate_alias() if alias_mode == "auto" else ( name + "_"+  agg ) 
                insert_into_tree(parts, alias=alias)
                json_aliases[alias] = parts[0]
            else:
                if not alias:
                    alias = generate_alias() if alias_mode == "auto" else ( name + "_"+  agg )
                col = resolve_field(name)
                select_fields.append(col.as_(alias))
                alias_map[alias] = name
    for alias, root_key in json_aliases.items():
        if root_key in json_tree :
            select_fields.append(build_json_tree(json_tree[root_key], tables, get_aggregate_function).as_(root_key))

    query = query.select(*select_fields)

    if where_clauses:
        query = query.where(build_nested_criteria(where_clauses, clause_type="where"))

    for gb in group_by:
        #if gb in alias_map:
        #   raise ValueError(f"Group by cannot use alias: {gb}")
        query = query.groupby(resolve_field(gb))

    if having_clauses:
        query = query.having(build_nested_criteria(having_clauses, clause_type="having"))

    for ob in order_by:
        key = ob["field"]
        resolved = alias_map.get(key, key)
        field = resolve_field(resolved)
        direction = ob["direction"].upper()
        query = query.orderby(field, order=Order.desc if direction == "DESC" else Order.asc)

    if limit:
        query = query.limit(limit)
    if offset:
        query = query.offset(offset)
    print(str(query))
    result = str(query)
    return result
 
  
sample_json =   {
        "tableName": "invoice_items",
        "fields": [
            "invoices.invoice_date",
            "invoices.customers.customer_name",
            "products.product_name"
        ],
        "relationships": {
            "invoice_items.invoices": {"key": "invoice_id", "table": "invoices"},
            "invoices.customers": {"key": "customer_id", "table": "customers"},
            "invoice_items.products": {"key": "product_id", "table": "products"}
        }
    }





if __name__ == "__main__":
    builder = build_query(sample_json) 
    print( builder)
 


