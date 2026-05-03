"""
formula_validation.py  —  fixed version

BUG / SECURITY FIXES APPLIED
─────────────────────────────
[BUG-15] parse_functions() split the formula by top-level commas, treating
         the entire formula string as a comma-delimited list of functions.
         This is wrong — the formula IS one expression; its top-level commas
         separate the parameters of the outermost function, not separate
         functions.  "ADDDAY(created_date, 5)" was split into
         ["ADDDAY(created_date", "5)"] — neither of which is a valid
         function string.
         Fixed: replaced parse_functions() with extract_functions(), which
         correctly walks the string character-by-character and extracts
         complete function calls (name + balanced parentheses), matching the
         proven implementation from evaluate_formula.py.

[BUG-16] parse_function() split parameters with a plain .split(',') which
         broke on nested functions: "IF(a > 1, SUM(x, y), 0)" → the SUM
         params were split at the inner comma giving 4 params instead of 3.
         Fixed: replaced with split_parameters() that tracks parenthesis
         depth.

[BUG-17] get_field_datatype() iterated fields_metadata as if it were a
         list of dicts ({'name': ..., 'datatype': ...}) but
         get_fields_metadata() returns a plain dict {name: datatype}.
         The iteration always returned None, meaning every field reference
         failed the datatype check and every formula silently returned False.
         Fixed: fields_metadata is a dict; just use .get().

[BUG-18] validate_formula() returned False (bool) on invalid function names
         instead of raising — the caller in create_workflow.py checked for
         exceptions, not return values, so invalid functions were silently
         accepted.
         Fixed: raise ValueError for invalid function names.

[BUG-19] validate_formula() returned True / False (bool); callers (both
         create_workflow and update_workflow) treated exceptions as the
         error signal.  Mixed contract.  Fixed: always raise on failure,
         return the formula return-type string on success (matching the
         validated-formula contract from the previous review session).

[BUG-20] get_value() attempted to return the datatype string (e.g.
         "datetime") as the value when looking up a field in metadata,
         then passed that string to validate_literal() which checked
         isinstance(param_value, datetime) — always False for a string.
         Fixed: when a field is found in metadata, return a typed
         placeholder that matches the declared datatype so validate_literal
         can actually succeed.

[BUG-21] validate_formula() accepted a 4th positional arg
         (parent_expected_type) in the original file docstring but the
         actual signature only had 3 params.  Callers were passing 4 args
         (see BUG-02 / BUG-10).  Added the optional 4th param back with a
         default of None so both 3-arg and 4-arg call sites work.

[LOGIC-05] validate_literal() had no boolean or date/number-subtype support.
           Added 'boolean', 'date', 'currency', 'percent', 'any' handling to
           match the richer type system used by functions_data.py.
"""

import re
from collections import deque
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple

from .functions_data import function_metadata

# ── type groups ───────────────────────────────────────────────────────────────
NUMERIC_TYPES = {"number", "currency", "percent"}
TEXT_TYPES    = {"text", "textarea", "picklist", "email", "phone", "url", "multi_picklist"}


# ── placeholder factory ───────────────────────────────────────────────────────
def _placeholder(field_type: Optional[str]) -> Any:
    """Return a typed placeholder value for validation purposes."""
    if not field_type:
        return 0
    ft = field_type.lower()
    if ft in NUMERIC_TYPES:
        return 0.0
    if ft in TEXT_TYPES:
        return ""
    if ft == "boolean":
        return True
    if ft == "date":
        return date.today()
    if ft == "datetime":
        return datetime.now()
    return ""


# ── main entry point ──────────────────────────────────────────────────────────
def validate_formula(
    formula: str,
    fields_metadata: Dict[str, str],
    field_name: str,
    parent_expected_type: Optional[str] = None,   # BUG-21: 4th optional param
) -> str:
    """
    Validate a formula expression against field metadata.

    Returns the formula's return-type string (e.g. 'datetime', 'number') on
    success, raises ValueError on failure.
    """
    if not isinstance(fields_metadata, dict):
        raise ValueError("fields_metadata must be a plain dict {field_name: datatype}.")

    # ── extract top-level function calls ─────────────────────────────────────
    functions = extract_functions(formula)   # FIX BUG-15

    if not functions:
        # No functions — treat as a literal or field reference
        return _infer_literal_type(formula, fields_metadata, field_name)

    for function_str in functions:
        function_name, params = parse_function(function_str)

        if not function_name:
            continue

        # FIX BUG-18: raise instead of returning False
        if function_name not in function_metadata:
            raise ValueError(
                f"Invalid or unsupported function '{function_name}' in formula for field '{field_name}'."
            )

        meta        = function_metadata[function_name]
        param_types = meta["datatype"]
        param_names = meta["paramnames"]

        # FIX BUG-16: use depth-aware parameter splitter
        param_list = split_parameters(params)
        params_values = [_resolve_param(p.strip(), fields_metadata) for p in param_list]

        # Validate parameter count (functions with empty datatype list take 0 params, e.g. NOW/TODAY)
        if param_types and len(params_values) != len(param_types):
            raise ValueError(
                f"Function '{function_name}' expects {len(param_types)} parameter(s), "
                f"got {len(params_values)}."
            )

        # Validate each parameter type
        for idx, (param_value, expected_type) in enumerate(zip(params_values, param_types)):
            if expected_type == "any":
                continue
            if not validate_literal(param_value, expected_type):
                raise ValueError(
                    f"Parameter '{param_names[idx]}' of function '{function_name}' "
                    f"expects type '{expected_type}', got {type(param_value).__name__!r}."
                )

    # Return the return_type of the outermost function
    outer_name = extract_functions(formula)[0].split("(")[0]
    return_type = function_metadata.get(outer_name, {}).get("return_type", "text")
    return return_type


# ── function string extraction ────────────────────────────────────────────────
def extract_functions(formula: str) -> List[str]:
    """
    Extract top-level function calls from a formula string.
    FIX BUG-15: replaces the broken parse_functions() implementation.
    """
    functions: List[str] = []
    n = len(formula)
    i = 0
    while i < n:
        if formula[i] == "(":
            # Walk backward for the function name
            j = i - 1
            while j >= 0 and formula[j].isspace():
                j -= 1
            name_end = j + 1
            while j >= 0 and (formula[j].isalnum() or formula[j] == "_"):
                j -= 1
            name_start = j + 1
            func_name = formula[name_start:name_end]
            if not func_name:
                i += 1
                continue
            # Find the matching closing parenthesis
            depth = 0
            k = i
            while k < n:
                if formula[k] == "(":
                    depth += 1
                elif formula[k] == ")":
                    depth -= 1
                    if depth == 0:
                        functions.append(formula[name_start: k + 1])
                        i = k
                        break
                k += 1
        i += 1
    return functions


def parse_function(function_str: str) -> Tuple[Optional[str], str]:
    """Return (function_name, params_string) for a function call string."""
    match = re.match(r"(\w+)\((.*)\)$", function_str, re.DOTALL)
    if match:
        return match.group(1), match.group(2).strip()
    return None, ""


def split_parameters(params_str: str) -> List[str]:
    """
    Split a parameter string on commas, respecting nested parentheses.
    FIX BUG-16: replaces the plain .split(',') in the original parse_function().
    """
    params: List[str] = []
    stack: deque = deque()
    start = 0
    for i, ch in enumerate(params_str):
        if ch == "," and not stack:
            params.append(params_str[start:i].strip())
            start = i + 1
        elif ch == "(":
            stack.append(ch)
        elif ch == ")" and stack:
            stack.pop()
    params.append(params_str[start:].strip())
    return [p for p in params if p]  # drop empty strings


# ── parameter resolution ──────────────────────────────────────────────────────
def _resolve_param(param: str, fields_metadata: Dict[str, str]) -> Any:
    """
    Resolve a parameter token to a typed value for validation.
    FIX BUG-20: returns a typed placeholder, not the datatype string.
    """
    # Nested function — recursively extract its return type as a placeholder
    if "(" in param:
        nested = extract_functions(param)
        if nested:
            outer = nested[0].split("(")[0]
            rt = function_metadata.get(outer, {}).get("return_type", "text")
            return _placeholder(rt)

    # Boolean literals
    if param == "True":
        return True
    if param == "False":
        return False

    # Quoted string literal
    if (param.startswith('"') and param.endswith('"')) or \
       (param.startswith("'") and param.endswith("'")):
        return param[1:-1]

    # Numeric literal
    try:
        return int(param)
    except ValueError:
        pass
    try:
        return float(param)
    except ValueError:
        pass

    # Field reference — FIX BUG-17: fields_metadata is a dict, use .get()
    if param in fields_metadata:
        return _placeholder(fields_metadata[param])   # FIX BUG-20

    # Unknown — return as string (will fail type check if type != 'text')
    return param


# ── literal type validation ───────────────────────────────────────────────────
def validate_literal(value: Any, expected_type: str) -> bool:
    """
    Check whether a resolved value is compatible with expected_type.
    FIX LOGIC-05: extended to cover boolean, date, and numeric subtypes.
    """
    if expected_type == "any":
        return True
    if expected_type in NUMERIC_TYPES:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type in TEXT_TYPES:
        return isinstance(value, str)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "date":
        return isinstance(value, (date, datetime))
    if expected_type == "datetime":
        return isinstance(value, datetime)
    # Fallback: exact equality (handles unknown / custom types)
    return False


# ── literal / field-reference inference ──────────────────────────────────────
def _infer_literal_type(formula: str, fields_metadata: Dict[str, str], field_name: str) -> str:
    """Return an inferred type string for a formula with no function calls."""
    stripped = formula.strip()

    # Field reference
    if stripped in fields_metadata:
        return fields_metadata[stripped]

    # Boolean
    if stripped in ("True", "False"):
        return "boolean"

    # Numeric
    try:
        int(stripped)
        return "number"
    except ValueError:
        pass
    try:
        float(stripped)
        return "number"
    except ValueError:
        pass

    # Quoted string
    if (stripped.startswith('"') and stripped.endswith('"')) or \
       (stripped.startswith("'") and stripped.endswith("'")):
        return "text"

    # Arithmetic expression — infer from field types in the expression
    for fname, ftype in fields_metadata.items():
        if fname in stripped:
            return ftype

    return "text"
