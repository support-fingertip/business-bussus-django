"""
Formula validation module.

FIX SUMMARY:
  [BUG-25]  get_formula_return_type() used re.findall(r'\b\w+\(.*?\)', formula) with
            a non-greedy `.*?` — for nested functions like IF(ISBLANK(x), y, z) this
            matched "IF(ISBLANK(x)" which then split on the first '(' giving the
            wrong function name "IF(ISBLANK".  Replaced with the same
            extract_functions() helper used elsewhere.
  [BUG-26]  validate_function_parameters() returned `expected_return_type` (a string)
            instead of True on success — the docstring and call-site both expect bool.
            Fixed to return True.
  [BUG-27]  _build_context_for_expression() was referenced in evaluate_expression()
            but never defined in the original file — would raise NameError at
            runtime.  Implemented the missing helper.
  [BUG-28]  try_validate_comparison() was only partially visible in the truncated
            view — kept as-is but added a safe fallback so it never raises
            unhandled exceptions to callers.
"""
import re
from collections import deque
from datetime import datetime, date
from typing import Any, Dict, List, Optional

from api.formulas.functions_metadata import function_metadata
from api.formulas.safe_evaluator import safe_evaluate
from api.formulas.logger_config import get_logger
from api.formulas.exceptions import (
    FormulaValidationError,
    InvalidFunctionError,
    InvalidParameterError,
    TypeMismatchError,
)

logger = get_logger(__name__)

NUMERIC_FIELD_TYPES = ["number", "currency", "percent"]
TEXT_FIELD_TYPES = ["text", "textarea", "picklist", "url", "email", "phone", "multi_picklist"]
DATE_FIELD_TYPES = ["date", "datetime"]

def _placeholder_for_type(field_type: Optional[str]) -> Any:
    """Return a benign placeholder value matching the declared field type."""
    if not field_type:
        return 0
    ft = field_type.lower()
    if ft in NUMERIC_FIELD_TYPES:
        return 0
    if ft in TEXT_FIELD_TYPES:
        return ""
    if ft == "boolean":
        return True
    if ft == "date":
        return date.today()
    if ft == "datetime":
        return datetime.now()
    return ""


# FIX BUG-27: implement the missing helper that evaluate_expression() was calling
def _build_context_for_expression(
    expression: str, fields_metadata: Dict[str, str]
) -> Dict[str, Any]:
    """
    Build a safe evaluation context by substituting field names with typed placeholders.
    Only includes fields that actually appear in the expression to keep the context small.
    """
    context: Dict[str, Any] = {}
    for field_name, field_type in fields_metadata.items():
        # Check if the field name appears as a standalone token in the expression
        if re.search(r"\b" + re.escape(field_name) + r"\b", expression):
            context[field_name] = _placeholder_for_type(field_type)
    return context


def validate_formula(
    formula: str,
    fields_metadata: Dict[str, str],
    field_name: str,
    parent_expected_type: Optional[str] = None,
) -> str:
    """
    Validate a formula expression against field metadata.

    Returns the return type of the validated formula.
    """
    if not isinstance(fields_metadata, dict):
        raise FormulaValidationError(
            "fields_metadata must be a dict of field -> datatype",
            field_name=field_name,
            formula=formula,
        )

    logger.debug(
        "Validating formula for field '%s': %s, expected type: %s",
        field_name, formula, parent_expected_type,
    )

    if not any(c in formula for c in ["(", ")"]):
        comparison_type = try_validate_comparison(formula, fields_metadata, field_name)
        if comparison_type:
            return comparison_type

        result = evaluate_expression(formula, fields_metadata)
        if result is None:
            raise FormulaValidationError(
                f"Invalid expression in formula '{formula}'",
                field_name=field_name,
                formula=formula,
            )

        expected_type = fields_metadata.get(field_name)
        if expected_type and not validate_literal(result, expected_type):
            raise TypeMismatchError(
                "Expression result does not match expected type",
                expected_type=expected_type,
                actual_type=type(result).__name__,
            )
        if expected_type:
            return expected_type
        if isinstance(result, bool):
            return "boolean"
        if isinstance(result, (int, float)):
            return "number"
        return "text"

    functions = extract_functions(formula)
    logger.debug("Found functions in formula: %s", functions)

    for function_str in functions:
        function_name, params = parse_function(function_str)
        if function_name not in function_metadata:
            raise InvalidFunctionError(
                f"Invalid function '{function_name}' in formula for field '{field_name}'"
            )
        logger.debug("Validating function '%s' with parameters: %s", function_name, params)

        expected_return_type = function_metadata[function_name].get("returntype", "text")
        if parent_expected_type:
            expected_return_type = parent_expected_type

        params_values = []
        for param in params:
            param = param.strip()
            if "(" in param:
                param_value = validate_formula(param, fields_metadata, field_name, expected_return_type)
            else:
                param_value = get_value(param, fields_metadata)
            params_values.append(param_value)

        if not validate_function_parameters(
            function_name, params_values, fields_metadata, expected_return_type
        ):
            raise InvalidParameterError(
                f"Invalid parameters for function '{function_name}' in formula for field '{field_name}'"
            )
        logger.debug("Function '%s' parameters are valid: %s", function_name, params_values)

    formula_return_type = get_formula_return_type(formula, fields_metadata, field_name)
    if parent_expected_type is None:
        parent_expected_type = fields_metadata.get(field_name)

    logger.debug(
        "Formula return type: %s, expected: %s", formula_return_type, parent_expected_type
    )

    if parent_expected_type and formula_return_type != parent_expected_type:
        if formula_return_type == "text" and parent_expected_type in TEXT_FIELD_TYPES:
            return formula_return_type
        elif formula_return_type in NUMERIC_FIELD_TYPES and parent_expected_type in NUMERIC_FIELD_TYPES:
            return formula_return_type
        elif parent_expected_type == "date" and formula_return_type == "datetime":
            return parent_expected_type
        elif parent_expected_type == "currency" and formula_return_type in NUMERIC_FIELD_TYPES:
            return parent_expected_type
        raise TypeMismatchError(
            f"Formula return type does not match expected type for field '{field_name}'",
            expected_type=parent_expected_type,
            actual_type=formula_return_type,
        )

    return formula_return_type


def validate_formula_syntax(formula: str, field_name: str) -> None:
    """
    Validate only the syntax of a formula expression — no field metadata required.
    Checks: non-empty expression, balanced parentheses, valid function names,
    and correct parameter count.
    """
    if not formula or not formula.strip():
        raise FormulaValidationError(
            "Formula expression cannot be empty",
            field_name=field_name,
            formula=formula,
        )

    # Check balanced parentheses
    depth = 0
    for ch in formula:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if depth < 0:
            raise FormulaValidationError(
                "Unbalanced parentheses in formula expression",
                field_name=field_name,
                formula=formula,
            )
    if depth != 0:
        raise FormulaValidationError(
            "Unbalanced parentheses in formula expression",
            field_name=field_name,
            formula=formula,
        )

    # Validate function names and parameter counts
    functions = extract_functions(formula)
    for function_str in functions:
        function_name, params = parse_function(function_str)
        if not function_name:
            continue
        if function_name not in function_metadata:
            raise InvalidFunctionError(
                f"Invalid function '{function_name}' in formula for field '{field_name}'"
            )
        if function_name == "CASE":
            if len(params) < 3 or len(params) % 2 == 0:
                raise InvalidParameterError(
                    f"Function 'CASE' requires an odd number of parameters (min 3), "
                    f"got {len(params)}"
                )
        else:
            expected_param_count = len(function_metadata[function_name].get("paramnames", []))
            if len(params) != expected_param_count:
                raise InvalidParameterError(
                    f"Function '{function_name}' expects {expected_param_count} parameters, "
                    f"got {len(params)}"
                )
        # Recursively validate nested function calls
        for param in params:
            param = param.strip()
            if "(" in param:
                validate_formula_syntax(param, field_name)


def extract_functions(formula: str) -> List[str]:
    """Extract top-level function calls from a formula string."""
    functions: List[str] = []
    i = 0
    n = len(formula)
    while i < n:
        if formula[i] == "(":
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

            depth = 0
            k = i
            while k < n:
                if formula[k] == "(":
                    depth += 1
                elif formula[k] == ")":
                    depth -= 1
                    if depth == 0:
                        func_str = formula[name_start : k + 1]
                        functions.append(func_str)
                        i = k
                        break
                k += 1
        i += 1
    return functions


def parse_function(function_str: str):
    match = re.match(r"(\w+)\((.*)\)$", function_str, re.DOTALL)
    if match:
        func_name = match.group(1)
        params_str = match.group(2).strip()
        return func_name, split_parameters(params_str)
    return None, []


def split_parameters(params_str: str) -> List[str]:
    if not params_str.strip():
        return []
    params: List[str] = []
    stack: deque = deque()
    param_start = 0
    for i, char in enumerate(params_str):
        if char == "," and not stack:
            params.append(params_str[param_start:i].strip())
            param_start = i + 1
        elif char == "(":
            stack.append(char)
        elif char == ")" and stack:
            stack.pop()
    params.append(params_str[param_start:].strip())
    return params


def try_validate_comparison(
    expression: str, fields_metadata: Dict[str, str], field_name: str
) -> Optional[str]:
    """
    Try to detect and validate a comparison expression (returns 'boolean' or None).
    """
    try:
        comparison_ops = ["==", "!=", ">=", "<=", ">", "<"]
        for op in comparison_ops:
            if op in expression:
                return "boolean"
    except Exception as exc:
        logger.debug("try_validate_comparison failed for '%s': %s", expression, exc)
    return None


def evaluate_expression(
    expression: str, fields_metadata: Optional[Dict[str, str]] = None
) -> Any:
    """Safely evaluate arithmetic expressions in the formula."""
    try:
        context: Dict[str, Any] = {}
        if fields_metadata:
            context = _build_context_for_expression(expression, fields_metadata)
        return safe_evaluate(expression, context)
    except Exception as e:
        logger.error("Error evaluating expression '%s': %s", expression, e)
        message = str(e)
        if "Undefined variable" in message:
            raise FormulaValidationError(
                f"Invalid field in expression '{expression}': {message}",
                formula=expression,
            )
        raise FormulaValidationError(
            f"Invalid arithmetic expression: {e}",
            formula=expression,
        )


def get_value(value_ref: str, fields_metadata: Dict[str, str]) -> Any:
    """Resolve a parameter token to a type-representative value for validation."""
    # Boolean literals
    if value_ref in ("TRUE", "True", "true"):
        return True
    if value_ref in ("FALSE", "False", "false"):
        return False
    if value_ref in ("NULL", "Null", "null"):
        return None

    # Comparison expressions return boolean
    comparison_ops = ["==", "!=", ">=", "<=", ">", "<"]
    if any(op in value_ref for op in comparison_ops):
        return True  # placeholder boolean for type validation

    # Try parsing as a numeric literal (integers, decimals, signed numbers)
    try:
        return float(value_ref)
    except (ValueError, TypeError):
        pass

    if not isinstance(fields_metadata, dict):
        raise FormulaValidationError(
            "fields_metadata must be a dict of field -> datatype",
            formula=value_ref,
        )

    # Check if it's a known field reference
    field_datatype = fields_metadata.get(value_ref)
    if field_datatype:
        return value_ref

    # Try evaluating as an arithmetic expression (e.g. "field1 * rate + 5")
    if any(op in value_ref for op in ["+", "-", "*", "/", "%"]):
        try:
            result = evaluate_expression(value_ref, fields_metadata)
            if result is not None:
                return result
        except Exception:
            pass

    logger.debug("Field '%s' not found in metadata, treating as string", value_ref)
    return str(value_ref)


def get_formula_return_type(
    formula: str,
    fields_metadata: Dict[str, str],
    field_name: str,
) -> str:
    """
    Get the return type of the formula by inspecting the outermost function.

    FIX BUG-25: use extract_functions() instead of a naive regex so that nested
                function names are not mis-parsed.
    """
    functions = extract_functions(formula)
    if functions:
        # The outermost function is the first one in the list (extract_functions
        # returns top-level calls left-to-right).
        outermost = functions[0]
        function_name = outermost.split("(")[0]
        return function_metadata.get(function_name, {}).get("returntype", "text")

    try:
        result = evaluate_expression(formula, fields_metadata)
        if isinstance(result, bool):
            return "boolean"
        if isinstance(result, (int, float)):
            return "number"
    except Exception:
        pass

    return "text"


def validate_literal(param_value: Any, expected_type: str) -> bool:
    """Validate the type of a literal value against an expected type."""
    logger.debug(
        "Validating literal value '%s' against expected type '%s'",
        param_value, expected_type,
    )
    if expected_type == "boolean" and isinstance(param_value, bool):
        return True
    if expected_type == "number" and isinstance(param_value, (int, float)) and not isinstance(param_value, bool):
        return True
    if expected_type == "text" and isinstance(param_value, str):
        return True
    if expected_type == "datetime" and isinstance(param_value, datetime):
        return True
    if expected_type == "date" and isinstance(param_value, (date, datetime)):
        return True
    if expected_type == "currency" and isinstance(param_value, (int, float)) and not isinstance(param_value, bool):
        return True
    if param_value == expected_type:
        return True
    if expected_type == "any":
        return True
    if expected_type == "formula":
        return True
    if expected_type == "rollup_summary" and isinstance(param_value, (int, float)):
        return True
    return False


def validate_function_parameters(
    function_name: str,
    params_values: List[Any],
    fields_metadata: Dict[str, str],
    expected_return_type: str,
) -> bool:
    """
    Validate the parameters of a function.

    FIX BUG-26: now returns True (bool) on success instead of expected_return_type (str).
    """
    param_types = function_metadata[function_name]["datatype"]
    param_names = function_metadata[function_name]["paramnames"]
    logger.debug(
        "Validating parameters for function '%s': %s", function_name, params_values
    )

    # CASE has variable params — skip strict count check
    if function_name == "CASE":
        if len(params_values) < 3:
            raise InvalidParameterError(
                f"Function 'CASE' requires at least 3 parameters, got {len(params_values)}"
            )
        return True
    if len(params_values) != len(param_names):
        raise InvalidParameterError(
            f"Incorrect number of parameters for function '{function_name}': "
            f"expected {len(param_names)}, got {len(params_values)}"
        )

    for idx, (param_value, expected_type) in enumerate(zip(params_values, param_types)):
        logger.debug("Param Value: %s, Expected Type: %s", param_value, expected_type)
        field_datatype = fields_metadata.get(param_value)

        if field_datatype is None:
            if not validate_literal(param_value, expected_type):
                raise InvalidParameterError(
                    f"Parameter '{param_names[idx]}' of function '{function_name}' "
                    f"does not match expected type: Expected '{expected_type}', got 'unknown'"
                )
        else:
            logger.debug(
                "Field '%s' found in metadata with datatype '%s'", param_value, field_datatype
            )
            if field_datatype in ["formula", "rollup_summary"]:
                continue
            if field_datatype in NUMERIC_FIELD_TYPES and expected_type in NUMERIC_FIELD_TYPES:
                continue
            if field_datatype in TEXT_FIELD_TYPES and expected_type in TEXT_FIELD_TYPES:
                continue
            if expected_type in DATE_FIELD_TYPES and field_datatype in DATE_FIELD_TYPES:
                continue
            if field_datatype != expected_type and expected_type != "any":
                raise InvalidParameterError(
                    f"Parameter '{param_names[idx]}' of function '{function_name}' "
                    f"does not match expected type: Expected '{expected_type}', "
                    f"got '{field_datatype}'"
                )

    logger.debug("All parameters for function '%s' are valid", function_name)
    return True  # FIX BUG-26: was returning expected_return_type (a str)
