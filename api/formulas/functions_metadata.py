"""
Function metadata registry.

FIX SUMMARY:
  [BUG-29]  CONTAINS was defined twice — the second definition silently overwrote
            the first.  Both definitions were identical so the fix is simply to
            remove the duplicate.
  [BUG-30]  ADDMONTH was used in functions_and_conditions.py but had no entry here,
            causing InvalidFunctionError during process_formula().  Added as a
            deprecated alias pointing to the same signature as ADDMONTHS.
"""

function_metadata = {
    "DATE": {
        "datatype": ["number", "number", "number"],
        "paramnames": ["year", "month", "day"],
        "returntype": "date",
    },
    "DATEVALUE": {
        "datatype": ["text"],
        "paramnames": ["date_string"],
        "returntype": "date",
    },
    "DATETIMEVALUE": {
        "datatype": ["text"],
        "paramnames": ["datetime_string"],
        "returntype": "datetime",
    },
    "ADDDAY": {
        "datatype": ["datetime", "number"],
        "paramnames": ["datetime", "days"],
        "returntype": "datetime",
    },
    # FIX BUG-30: ADDMONTH added as deprecated alias for ADDMONTHS
    "ADDMONTH": {
        "datatype": ["datetime", "number"],
        "paramnames": ["date", "months"],
        "returntype": "datetime",
    },
    "ADDMONTHS": {
        "datatype": ["date", "number"],
        "paramnames": ["date", "number_of_months"],
        "returntype": "date",
    },
    "ADDYEAR": {
        "datatype": ["datetime", "number"],
        "paramnames": ["date", "years"],
        "returntype": "datetime",
    },
    "ADDMINUTES": {
        "datatype": ["datetime", "number"],
        "paramnames": ["datetime", "minutes"],
        "returntype": "datetime",
    },
    "ADDHOURS": {
        "datatype": ["datetime", "number"],
        "paramnames": ["datetime", "hours"],
        "returntype": "datetime",
    },
    "ADDSECONDS": {
        "datatype": ["datetime", "number"],
        "paramnames": ["datetime", "seconds"],
        "returntype": "datetime",
    },
    "CONCAT": {
        "datatype": ["text", "text"],
        "paramnames": ["string1", "string2"],
        "returntype": "text",
    },
    "SUM": {
        "datatype": ["number", "number"],
        "paramnames": ["num1", "num2"],
        "returntype": "number",
    },
    "MAX": {
        "datatype": ["number", "number"],
        "paramnames": ["num1", "num2"],
        "returntype": "number",
    },
    "MIN": {
        "datatype": ["number", "number"],
        "paramnames": ["num1", "num2"],
        "returntype": "number",
    },
    "TEXT": {
        "datatype": ["any"],
        "paramnames": ["text_value"],
        "returntype": "text",
    },
    # FIX BUG-29: removed duplicate CONTAINS definition (was defined twice)
    "CONTAINS": {
        "returntype": "boolean",
        "datatype": ["text", "text"],
        "paramnames": ["text", "substring"],
    },
    "IF": {
        "returntype": "any",
        "datatype": ["boolean", "any", "any"],
        "paramnames": ["condition", "true_value", "false_value"],
    },
    "ROUND": {
        "returntype": "number",
        "datatype": ["number", "number"],
        "paramnames": ["number", "decimal_places"],
    },
    "ISBLANK": {
        "returntype": "boolean",
        "datatype": ["any"],
        "paramnames": ["value"],
    },
    "NOW": {
        "returntype": "datetime",
        "datatype": [],
        "paramnames": [],
    },
    "TODAY": {
        "returntype": "date",
        "datatype": [],
        "paramnames": [],
    },
    "YEAR": {
        "returntype": "number",
        "datatype": ["date"],
        "paramnames": ["date"],
    },
    "MONTH": {
        "returntype": "number",
        "datatype": ["date"],
        "paramnames": ["date"],
    },
    "DAY": {
        "returntype": "number",
        "datatype": ["date"],
        "paramnames": ["date"],
    },
    "CEILING": {
        "returntype": "number",
        "datatype": ["number"],
        "paramnames": ["number"],
    },
    "FLOOR": {
        "returntype": "number",
        "datatype": ["number"],
        "paramnames": ["number"],
    },
    "MOD": {
        "returntype": "number",
        "datatype": ["number", "number"],
        "paramnames": ["dividend", "divisor"],
    },
    "ABS": {
        "returntype": "number",
        "datatype": ["number"],
        "paramnames": ["number"],
    },
    "AND": {
        "returntype": "boolean",
        "datatype": ["boolean", "boolean"],
        "paramnames": ["condition1", "condition2"],
    },
    "OR": {
        "returntype": "boolean",
        "datatype": ["boolean", "boolean"],
        "paramnames": ["condition1", "condition2"],
    },
    "ISNUMBER": {
        "returntype": "boolean",
        "datatype": ["any"],
        "paramnames": ["value"],
    },
    "BLANKVALUE": {
        "returntype": "any",
        "datatype": ["any", "any"],
        "paramnames": ["value", "default"],
    },
    "ISPICKVAL": {
        "returntype": "boolean",
        "datatype": ["picklist", "text"],
        "paramnames": ["picklist_field", "text_value"],
    },
    "YEARFRAC": {
        "returntype": "number",
        "datatype": ["date", "date"],
        "paramnames": ["start_date", "end_date"],
    },
    "DATEDIFF": {
        "returntype": "number",
        "datatype": ["date", "date"],
        "paramnames": ["start_date", "end_date"],
    },
    "SUBSTITUTE": {
        "returntype": "text",
        "datatype": ["text", "text", "text"],
        "paramnames": ["text", "oldtext", "newtext"],
    },
    "LEN": {
        "returntype": "number",
        "datatype": ["text"],
        "paramnames": ["text"],
    },
    "LENGTH": {
        "returntype": "number",
        "datatype": ["text"],
        "paramnames": ["text"],
    },
    "TRIM": {
        "returntype": "text",
        "datatype": ["text"],
        "paramnames": ["text"],
    },
    "LOWER": {
        "returntype": "text",
        "datatype": ["text"],
        "paramnames": ["text"],
    },
    "UPPER": {
        "returntype": "text",
        "datatype": ["text"],
        "paramnames": ["text"],
    },
    "LEFT": {
        "returntype": "text",
        "datatype": ["text", "number"],
        "paramnames": ["text", "num_chars"],
    },
    "RIGHT": {
        "returntype": "text",
        "datatype": ["text", "number"],
        "paramnames": ["text", "num_chars"],
    },
    "MID": {
        "returntype": "text",
        "datatype": ["text", "number", "number"],
        "paramnames": ["text", "start_position", "num_chars"],
    },
    # Aliases matching frontend naming
    "CEIL": {
        "returntype": "number",
        "datatype": ["number"],
        "paramnames": ["number"],
    },
    "REPLACE": {
        "returntype": "text",
        "datatype": ["text", "text", "text"],
        "paramnames": ["text", "oldtext", "newtext"],
    },
    "SUBSTRING": {
        "returntype": "text",
        "datatype": ["text", "number", "number"],
        "paramnames": ["text", "start_position", "num_chars"],
    },
    "ADDDAYS": {
        "datatype": ["datetime", "number"],
        "paramnames": ["datetime", "days"],
        "returntype": "datetime",
    },
    "ADDYEARS": {
        "datatype": ["datetime", "number"],
        "paramnames": ["date", "years"],
        "returntype": "datetime",
    },
    # Numeric
    "POWER": {
        "returntype": "number",
        "datatype": ["number", "number"],
        "paramnames": ["base", "exponent"],
    },
    "SQRT": {
        "returntype": "number",
        "datatype": ["number"],
        "paramnames": ["number"],
    },
    # Date extraction
    "HOUR": {
        "returntype": "number",
        "datatype": ["datetime"],
        "paramnames": ["datetime"],
    },
    "MINUTE": {
        "returntype": "number",
        "datatype": ["datetime"],
        "paramnames": ["datetime"],
    },
    "WEEKDAY": {
        "returntype": "number",
        "datatype": ["date"],
        "paramnames": ["date"],
    },
    # Logical
    "NOT": {
        "returntype": "boolean",
        "datatype": ["boolean"],
        "paramnames": ["condition"],
    },
    "ISNULL": {
        "returntype": "boolean",
        "datatype": ["any"],
        "paramnames": ["value"],
    },
    "NULLVALUE": {
        "returntype": "any",
        "datatype": ["any", "any"],
        "paramnames": ["value", "default"],
    },
    "CASE": {
        "returntype": "any",
        "datatype": ["any", "any", "any", "any", "any"],
        "paramnames": ["expression", "value1", "result1", "value2", "else_result"],
    },
}
