from typing import Dict, Any

VALID_OPERATORS = {'=', '!=', '>', '<', '>=', '<=', 'like'}
VALID_DIRECTIONS = {'asc', 'desc'}

def validate_and_extract_query_info(query: Dict[str, Any]) -> Dict[str, Any]:
    errors = []
    fields_set = set()
    extracted_fields = []

    # FROM
    table_name = query.get('from')
    if not table_name or not isinstance(table_name, str):
        errors.append("Missing or invalid 'from' table name.")

    # FIELDS
    if 'fields' in query:
        if not isinstance(query['fields'], list):
            errors.append("'fields' must be a list of strings.")
        else:
            for idx, entry in enumerate(query['fields']):
                if not isinstance(entry, str):
                    errors.append(f"Field at index {idx+1} must be a string.")
                else:
                    extracted_fields.append(entry)
                    parts = entry.lower().split(" as ")
                    raw_expr = parts[0].strip()
                    if "(" in raw_expr and ")" in raw_expr:
                        args_part = raw_expr[raw_expr.find("(")+1 : raw_expr.find(")")]
                        if args_part != "*":
                            fields_set.add(args_part)
                    else:
                        fields_set.add(raw_expr)
    else:
        extracted_fields = ["id"]
        fields_set.add("id")

    # COUNT BY
    count_by = query.get("count_by")
    if count_by:
        if not isinstance(count_by, str):
            errors.append("'count_by' must be a string.")
        elif count_by != "*":
            fields_set.add(count_by)

    # GROUP BY
    group_by = query.get('group_by', [])
    if group_by:
        if not isinstance(group_by, list):
            errors.append("'group_by' must be a list.")
        else:
            for field in group_by:
                if not isinstance(field, str):
                    errors.append(f"Group by field '{field}' must be a string.")
                fields_set.add(field)

            # ✅ Enforce that all non-aggregated fields must appear in group_by
            for field in fields_set:
                if not field.lower().startswith(('count(', 'sum(', 'avg(', 'min(', 'max(')) and field not in group_by:
                    if 'fields' in query:
                        for f in query['fields']:
                            if f == field or f.startswith(field + " "):  # crude match
                                errors.append(f"Field '{field}' must be included in 'group_by' or used in an aggregate function.")

    # WHERE
    if 'where' in query and 'and' in query['where']:
        conditions = query['where']['and']
        if not isinstance(conditions, list):
            errors.append("'where.and' must be a list.")
        else:
            for cond in conditions:
                if not all(k in cond for k in ['field', 'operator', 'value']):
                    errors.append("Each condition in 'where.and' must have 'field', 'operator', and 'value'.")
                else:
                    fields_set.add(cond['field'])

    # HAVING
    if 'having' in query:
        hv = query['having']
        if not all(k in hv for k in ['function', 'args', 'operator', 'value']):
            errors.append("Missing keys in 'having'.")
        else:
            args = hv['args']
            if not isinstance(args, list):
                errors.append("Invalid 'args' in 'having'.")
            for arg in args:
                if isinstance(arg, str) and arg != "*":
                    fields_set.add(arg)

    # ORDER BY
    if 'order_by' in query:
        if not isinstance(query['order_by'], list):
            errors.append("'order_by' must be a list.")
        else:
            for ob in query['order_by']:
                if not all(k in ob for k in ['field', 'direction']):
                    errors.append("Each 'order_by' item must have 'field' and 'direction'.")
                elif ob['direction'].lower() not in VALID_DIRECTIONS:
                    errors.append(f"Invalid direction '{ob['direction']}' in order_by.")
                else:
                    fields_set.add(ob['field'])

    # LIMIT / OFFSET
    for key in ['limit', 'offset']:
        if key in query and not isinstance(query[key], int):
            errors.append(f"'{key}' must be an integer.")

    if errors:
        return {"valid": False, "errors": errors}
    else:
        return {
            "valid": True,
            "table": table_name,
            "fields": sorted(fields_set),
            "original_fields": extracted_fields
        }
