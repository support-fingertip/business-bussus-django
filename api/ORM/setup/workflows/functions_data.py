"""
functions_data.py  —  fixed version

BUG / SECURITY FIXES APPLIED
─────────────────────────────
[BUG-22] The metadata key for return type was inconsistently named.
         functions_data.py used "return_type" while the previous
         functions_metadata.py (from the last review) used "returntype"
         (no underscore).  formula_validation.py in THIS package uses
         "return_type" (with underscore) so that is the canonical key here.
         All entries confirmed to use "return_type" consistently.

[BUG-23] Several functions were missing from the registry that
         formula_validation.py needs to accept:
           - IF, ROUND, ISBLANK, NOW, TODAY, YEAR, MONTH, DAY,
             CEILING, FLOOR, MOD, ABS, AND, OR, ISNUMBER, BLANKVALUE,
             ISPICKVAL, YEARFRAC, DATEDIFF, SUBSTITUTE, ADDMONTHS
         Added all of them so validate_formula() does not reject valid
         function names.

[BUG-24] TEXT function metadata declared datatype ["text"] but TEXT()
         is a conversion function that accepts ANY type — changed to ["any"].

[BUG-25] NOW and TODAY take zero parameters — their datatype and paramnames
         lists must be empty [], otherwise the parameter-count check in
         validate_formula() would incorrectly reject them.
"""

function_metadata = {
    # ── date construction ────────────────────────────────────────────────────
    "DATE": {
        "datatype": ["number", "number", "number"],
        "paramnames": ["year", "month", "day"],
        "return_type": "date",
    },
    "DATEVALUE": {
        "datatype": ["text"],
        "paramnames": ["date_string"],
        "return_type": "date",
    },
    "DATETIMEVALUE": {
        "datatype": ["text"],
        "paramnames": ["datetime_string"],
        "return_type": "datetime",
    },

    # ── date arithmetic ──────────────────────────────────────────────────────
    "ADDDAY": {
        "datatype": ["datetime", "number"],
        "paramnames": ["date", "days"],
        "return_type": "datetime",
    },
    "ADDMONTH": {                          # deprecated alias — kept for back-compat
        "datatype": ["datetime", "number"],
        "paramnames": ["date", "months"],
        "return_type": "datetime",
    },
    "ADDMONTHS": {                         # BUG-23: canonical name, was missing
        "datatype": ["date", "number"],
        "paramnames": ["date", "months"],
        "return_type": "date",
    },
    "ADDYEAR": {
        "datatype": ["datetime", "number"],
        "paramnames": ["date", "years"],
        "return_type": "datetime",
    },
    "ADDMINUTES": {
        "datatype": ["datetime", "number"],
        "paramnames": ["datetime", "minutes"],
        "return_type": "datetime",
    },
    "ADDHOURS": {
        "datatype": ["datetime", "number"],
        "paramnames": ["datetime", "hours"],
        "return_type": "datetime",
    },
    "ADDSECONDS": {
        "datatype": ["datetime", "number"],
        "paramnames": ["datetime", "seconds"],
        "return_type": "datetime",
    },

    # ── date extraction ──────────────────────────────────────────────────────
    "YEAR": {                              # BUG-23
        "datatype": ["date"],
        "paramnames": ["date"],
        "return_type": "number",
    },
    "MONTH": {                             # BUG-23
        "datatype": ["date"],
        "paramnames": ["date"],
        "return_type": "number",
    },
    "DAY": {                               # BUG-23
        "datatype": ["date"],
        "paramnames": ["date"],
        "return_type": "number",
    },
    "DATEDIFF": {                          # BUG-23
        "datatype": ["date", "date"],
        "paramnames": ["start_date", "end_date"],
        "return_type": "number",
    },
    "YEARFRAC": {                          # BUG-23
        "datatype": ["date", "date"],
        "paramnames": ["start_date", "end_date"],
        "return_type": "number",
    },

    # ── current date/time ────────────────────────────────────────────────────
    "NOW": {                               # BUG-25: empty lists for zero-param functions
        "datatype": [],
        "paramnames": [],
        "return_type": "datetime",
    },
    "TODAY": {                             # BUG-25
        "datatype": [],
        "paramnames": [],
        "return_type": "date",
    },

    # ── text functions ───────────────────────────────────────────────────────
    "CONCAT": {
        "datatype": ["text", "text"],
        "paramnames": ["string1", "string2"],
        "return_type": "text",
    },
    "TEXT": {
        "datatype": ["any"],               # BUG-24: was ["text"], accepts any type
        "paramnames": ["value"],
        "return_type": "text",
    },
    "CONTAINS": {
        "datatype": ["text", "text"],
        "paramnames": ["text", "substring"],
        "return_type": "boolean",
    },
    "SUBSTITUTE": {                        # BUG-23
        "datatype": ["text", "text", "text"],
        "paramnames": ["text", "old_text", "new_text"],
        "return_type": "text",
    },

    # ── numeric functions ────────────────────────────────────────────────────
    "SUM": {
        "datatype": ["number", "number"],
        "paramnames": ["num1", "num2"],
        "return_type": "number",
    },
    "MAX": {
        "datatype": ["number", "number"],
        "paramnames": ["num1", "num2"],
        "return_type": "number",
    },
    "MIN": {
        "datatype": ["number", "number"],
        "paramnames": ["num1", "num2"],
        "return_type": "number",
    },
    "ROUND": {                             # BUG-23
        "datatype": ["number", "number"],
        "paramnames": ["number", "decimal_places"],
        "return_type": "number",
    },
    "CEILING": {                           # BUG-23
        "datatype": ["number"],
        "paramnames": ["number"],
        "return_type": "number",
    },
    "FLOOR": {                             # BUG-23
        "datatype": ["number"],
        "paramnames": ["number"],
        "return_type": "number",
    },
    "MOD": {                               # BUG-23
        "datatype": ["number", "number"],
        "paramnames": ["dividend", "divisor"],
        "return_type": "number",
    },
    "ABS": {                               # BUG-23
        "datatype": ["number"],
        "paramnames": ["number"],
        "return_type": "number",
    },

    # ── logical functions ────────────────────────────────────────────────────
    "IF": {                                # BUG-23
        "datatype": ["boolean", "any", "any"],
        "paramnames": ["condition", "true_value", "false_value"],
        "return_type": "any",
    },
    "AND": {                               # BUG-23
        "datatype": ["boolean", "boolean"],
        "paramnames": ["condition1", "condition2"],
        "return_type": "boolean",
    },
    "OR": {                                # BUG-23
        "datatype": ["boolean", "boolean"],
        "paramnames": ["condition1", "condition2"],
        "return_type": "boolean",
    },
    "ISBLANK": {                           # BUG-23
        "datatype": ["any"],
        "paramnames": ["value"],
        "return_type": "boolean",
    },
    "ISNUMBER": {                          # BUG-23
        "datatype": ["any"],
        "paramnames": ["value"],
        "return_type": "boolean",
    },
    "BLANKVALUE": {                        # BUG-23
        "datatype": ["any", "any"],
        "paramnames": ["value", "default"],
        "return_type": "any",
    },
    "ISPICKVAL": {                         # BUG-23
        "datatype": ["picklist", "text"],
        "paramnames": ["picklist_field", "text_value"],
        "return_type": "boolean",
    },
}
