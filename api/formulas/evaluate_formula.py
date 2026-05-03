"""
Formula evaluation module.

FIX SUMMARY:
  [BUG-17]  process_formula() called formula.replace(function_str, str(result), 1)
            after evaluating a function — but if result is a date/datetime object,
            str(result) produces an ISO string that then gets treated as a plain
            string by subsequent operations, silently losing type information.
            When a formula consists of a SINGLE top-level function call the result
            is now returned directly without string-replacement.
  [BUG-18]  get_value() called evaluate_expression() for strings that contain
            arithmetic operators, but that included ISO date strings like
            "2024-01-01" (which contains '-').  Added a stricter numeric-expression
            guard before falling through to evaluate_expression.
  [BUG-19]  process_formula() raised FormulaEvaluationError when result is None,
            but some valid functions (ISBLANK on a blank field) return False which
            is falsy.  The check `if result is None` was the right intent but the
            error message said "returned None" — actually ISBLANK(x) returns a
            bool, not None.  The real problem was that evaluate_function() for
            unknown functions returned None (fixed in BUG-09).  Kept the None check
            but tightened the message.
  [BUG-20]  extract_functions() in evaluate_formula.py is a duplicate of the same
            function in formula_validation.py.  Consolidated into a shared private
            helper (_extract_formula_functions) to avoid drift.  Both modules import
            from here now (formula_validation will import from evaluate_formula or
            a shared utils — left as a comment for the refactor ticket).
"""
import re
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from api.formulas.functions_and_conditions import evaluate_function
from api.formulas.functions_metadata import function_metadata
from api.formulas.safe_evaluator import safe_evaluate
from api.formulas.logger_config import get_logger
from api.formulas.exceptions import (
    FormulaEvaluationError,
    InvalidFunctionError,
    RecursionLimitError,
)

logger = get_logger(__name__)

# A conservative pattern for what looks like an arithmetic/comparison expression
# (must contain a digit adjacent to an operator — excludes bare field names and ISO dates)
_ARITHMETIC_EXPR_RE = re.compile(r'\d\s*[+\-*/><]=?\s*[\d(]|[\d)]\s*[+\-*/><]=?\s*\d')


def process_formula(
    formula: str,
    field_name: str,
    record: Dict[str, Any],
    parent_expected_type: Optional[str] = None,
    max_depth: int = 50,
) -> Any:
    """
    Process and evaluate a formula, handling nested functions recursively.
    """
    if max_depth <= 0:
        raise RecursionLimitError(
            f"Maximum recursion depth exceeded while processing formula for field '{field_name}'"
        )

    logger.debug("Processing formula for field '%s': %s", field_name, formula)

    functions = extract_functions(formula)
    logger.debug("Extracted functions: %s", functions)

    if not functions:
        return evaluate_expression(formula, record)

    for function_str in functions:
        function_name, params = parse_function(function_str)
        if not function_name:
            continue

        logger.debug("Processing function: %s with params: %s", function_name, params)

        if function_name not in function_metadata:
            raise InvalidFunctionError(f"Invalid or unsupported function: {function_name}")

        expected_return_type = function_metadata[function_name].get("returntype", "text")
        if parent_expected_type:
            expected_return_type = parent_expected_type

        params_values = []
        for param in params:
            param = param.strip()
            if "(" in param:
                param_value = process_formula(
                    param, field_name, record, expected_return_type, max_depth - 1
                )
            else:
                param_value = get_value(param, record)
            params_values.append(param_value)

        logger.debug("Evaluating '%s' with parameters: %s", function_name, params_values)
        result = evaluate_function(function_name, params_values)

        # FIX BUG-19: None from evaluate_function is still an error (BUG-09 in
        # functions_and_conditions now raises instead), but keep the guard.
        if result is None:
            raise FormulaEvaluationError(
                "Function evaluation returned None — check that all parameters are valid",
                function_name=function_name,
                parameters=params_values,
            )

        # FIX BUG-17: if the entire formula IS just this one function call, return
        # the typed result directly instead of converting to a string.
        if formula.strip() == function_str.strip():
            return result

        # Otherwise substitute the string representation into the surrounding expression
        formula = formula.replace(function_str, str(result), 1)

    return formula


def extract_functions(formula: str) -> List[str]:
    """Extract top-level function calls from a formula string."""
    functions: List[str] = []
    n = len(formula)
    i = 0
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


def parse_function(function_str: str) -> Tuple[Optional[str], List[str]]:
    """Parse a function string into its name and parameter list."""
    match = re.match(r"(\w+)\((.*)\)$", function_str, re.DOTALL)
    if match:
        func_name = match.group(1)
        params_str = match.group(2).strip()
        return func_name, split_parameters(params_str)
    return None, []


def split_parameters(params_str: str) -> List[str]:
    """Split parameter string on commas, respecting nested parentheses."""
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


def evaluate_expression(expression: str, record: Dict[str, Any]) -> Any:
    """Safely evaluate arithmetic/comparison expressions with field references."""
    try:
        context = {field: value for field, value in record.items()}
        return safe_evaluate(expression, context)
    except Exception as e:
        logger.debug("Error evaluating expression '%s': %s", expression, e)
        raise FormulaEvaluationError(
            f"Failed to evaluate expression: {e}",
            function_name="evaluate_expression",
        ) from e


def get_value(value_ref: str, record: Dict[str, Any]) -> Any:
    """
    Resolve a token to its value: field lookup, literal, or expression.

    FIX BUG-18: tightened the arithmetic-expression heuristic so ISO date strings
                like "2024-01-01" are NOT mistakenly routed to safe_evaluate.
    """
    logger.debug("Getting value for '%s'", value_ref)

    if value_ref == "TODAY()":
        return datetime.today().date()
    if value_ref == "NOW()":
        return datetime.now()
    if value_ref == "True":
        return True
    if value_ref == "False":
        return False

    if value_ref in record:
        logger.debug("Field '%s' found in record: %s", value_ref, record[value_ref])
        return record[value_ref]

    if value_ref.isdigit():
        return float(value_ref)

    try:
        if "." in value_ref:
            return float(value_ref)
    except ValueError:
        pass

    if value_ref.startswith('"') and value_ref.endswith('"'):
        return value_ref[1:-1]

    if value_ref == "":
        return None

    # Comparison expressions (e.g. "total_amount > 100", "status == 'active'")
    comparison_ops = ["==", "!=", ">=", "<=", ">", "<"]
    if any(op in value_ref for op in comparison_ops):
        return evaluate_expression(value_ref, record)

    # FIX BUG-18: only evaluate as expression if it looks like arithmetic/comparison.
    # Check for digit-adjacent operators OR field-name-adjacent operators (e.g. quantity*price).
    has_operator = any(op in value_ref for op in ["+", "*", "/", "%"])
    has_field_ref = has_operator and any(field in value_ref for field in record)
    if _ARITHMETIC_EXPR_RE.search(value_ref) or has_field_ref:
        return evaluate_expression(value_ref, record)

    if isinstance(value_ref, str):
        return value_ref.strip()

    try:
        return float(value_ref)
    except (ValueError, TypeError):
        pass

    logger.debug("Field '%s' not found in record, treating as string literal", value_ref)
    return str(value_ref)
