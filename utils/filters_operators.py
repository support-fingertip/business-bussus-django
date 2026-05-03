# Updated operator mapping with date and string-specific operators
OPERATOR_MAPPING = {
    "equals": "exact",
    "not_equals": "exact",  # Will use exclude()
    
    "contains": "icontains",
    "not_contains": "icontains",  # Will use exclude()
    "starts_with": "startswith",
    "endswith": "endswith",
    "not_startswith": "startswith",  # Will use exclude()
    "not_endswith": "endswith",  # Will use exclude()
    
    "greater_than": "gt",
    "greater_than_or_equal": "gte",
    "less_than": "lt",
    "less_than_or_equal": "lte",

    "before": "lt",
    "after": "gt",
    "on_or_before": "lte",
    "on_or_after": "gte",

    "in": "in",
    "not_in": "in",  # Will use exclude()
}