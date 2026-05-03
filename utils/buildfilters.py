import re
from datetime import datetime
from django.db.models import Q
from utils.filters_operators import OPERATOR_MAPPING

def preprocess_filter_logic(filter_logic):
    # Replace numeric references with filter identifiers
    filter_logic = re.sub(r'\b(\d+)\b', r'filter\1', filter_logic)

    # Replace logical operators with Django Q equivalents
    filter_logic = filter_logic.replace('AND', '&')
    filter_logic = filter_logic.replace('OR', '|')
    filter_logic = filter_logic.replace('NOT', '~')

    return filter_logic

def build_filter_conditions(filters, filter_logic=None):
    exclude_conditions = Q()
    filter_mapping = {}

    for index, f in enumerate(filters):
        field_name = f.get("field")
        operator = f.get("operator")
        value = f.get("value")

        if not field_name or not operator:
            raise ValueError("Each filter must have 'field' and 'operator'.")

        if operator not in OPERATOR_MAPPING:
            raise ValueError(f"Unsupported operator '{operator}' in filters.")

        orm_operator = OPERATOR_MAPPING[operator]

        if field_name in ["created_date", "last_modified_date"]:
            try:
                value = datetime.fromisoformat(value[:10]).date()
                filter_key = f"{field_name}__{orm_operator}"
            except ValueError:
                raise ValueError(f"Invalid date format for field '{field_name}'. Use YYYY-MM-DD.")
        else:
            filter_key = f"{field_name}__{orm_operator}"

        if operator in ["in", "not_in"] and isinstance(value, str):
            value = value.split(",")

        condition = Q(**{filter_key: value})

        if operator in ["not_equals", "not_contains", "not_in", "not_startswith", "not_endswith"]:
            exclude_conditions |= condition

        filter_mapping[f"filter{index + 1}"] = condition

    if filter_logic:
        try:
            processed_logic = preprocess_filter_logic(filter_logic)
            combined_filters = eval(processed_logic, {"Q": Q}, filter_mapping)
        except Exception as e:
            raise ValueError(f"Invalid filter logic: {e}")
    else:
        combined_filters = Q()
        for cond in filter_mapping.values():
            combined_filters &= cond
    return combined_filters, exclude_conditions


