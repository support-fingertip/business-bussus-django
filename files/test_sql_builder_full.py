
import sqlparse
from sql_builder import build_query
from itertools import product

relationships = {
    "invoice_items.invoice__r": { "key": "invoice_id", "table": "invoices" },
    "invoice__r.customer__r": { "key": "customer_id", "table": "customers" },
    "customer__r.region__r": { "key": "region_id", "table": "regions" },
    "region__r.zone__r": { "key": "zone_id", "table": "zones" },
    "invoice_items.product__r": { "key": "product_id", "table": "products" }
}

aliasing_options = ["auto", "none"]
relationship_outputs = ["flat", "json"]
field_types = ["direct", "related", "aggregate", "expression"]
where_types = ["none", "simple", "nested", "in", "between"]
order_by_options = ["none", "single", "multiple"]

combinations = list(product(
    aliasing_options,
    relationship_outputs,
    field_types,
    where_types,
    order_by_options
))

def generate_fields(field_type):
    if field_type == "direct":
        return ["invoice_id"]
    elif field_type == "related":
        return ["invoice__r.customer__r.customer_name", "product__r.product_name"]
    elif field_type == "aggregate":
        return [{"name": "quantity", "aggregate": "sum"}, "invoice_id", "product__r.product_name"]
    elif field_type == "expression":
        return [{"name": "quantity * unit_price", "expression": True, "alias": "total_value"}]

def extract_raw_fields(fields, order_by):
    raw_fields = set()
    for f in fields:
        if isinstance(f, str):
            raw_fields.add(f)
        elif isinstance(f, dict):
            if f.get("aggregate") or f.get("expression"):
                continue
            raw_fields.add(f["name"])
    if order_by:
        for ob in order_by:
            raw_fields.add(ob["field"])
    return list(raw_fields)

def has_aggregate(fields):
    for f in fields:
        if isinstance(f, dict) and f.get("aggregate"):
            return True
    return False

def generate_where(where_type):
    if where_type == "simple":
        return {"field": "quantity", "operator": ">", "value": 10}
    elif where_type == "nested":
        return {"and": [{"field": "quantity", "operator": ">", "value": 5}, {"field": "unit_price", "operator": "<", "value": 100}]}
    elif where_type == "in":
        return {"field": "invoice_id", "operator": "in", "value": [1, 2, 3]}
    elif where_type == "between":
        return {"field": "invoice__r.invoice_date", "operator": "between", "value": ["2023-01-01", "2023-12-31"]}
    else:
        return None

def generate_order_by(order_by_type):
    if order_by_type == "single":
        return [{"field": "invoice_id", "direction": "DESC"}]
    elif order_by_type == "multiple":
        return [
            {"field": "invoice_id", "direction": "DESC"},
            {"field": "product__r.product_name", "direction": "ASC"}
        ]
    return None

with open("bulk_test_output_robust_groupby.sql", "w", encoding="utf-8") as sqlfile:
    for idx, combo in enumerate(combinations):
        aliasing, rel_out, field_type, where_type, order_by_type = combo
        label = f"Test #{idx + 1}"
        comment = f"-- {label} | aliasing={aliasing}, jsonb={rel_out}, field={field_type}, where={where_type}, order_by={order_by_type}\n"

        fields = generate_fields(field_type)
        order_by = generate_order_by(order_by_type)

        input_data = {
            "tableName": "invoice_items",
            "fields": fields,
            "relationships": relationships,
            "aliasing": aliasing,
            "relationship_output": rel_out
        }

        if has_aggregate(fields):
            input_data["group_by"] = extract_raw_fields(fields, order_by)

        where = generate_where(where_type)
        if where:
            input_data["where"] = where

        if order_by:
            input_data["order_by"] = order_by

        try:
            query = build_query(input_data)
            formatted = sqlparse.format(query, reindent=True, keyword_case='upper')
            sqlfile.write(comment)
            sqlfile.write(formatted + ";\n\n")
        except Exception:
            sqlfile.write(comment)
            sqlfile.write(f"-- FAIL ❌\n\n")
