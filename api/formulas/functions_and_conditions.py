"""
Formula functions and conditions implementation.

FIX SUMMARY:
  [BUG-08]  if_function() evaluated string "False" as True because `condition or
            condition == "true"` short-circuits on any truthy string.  Replaced
            with an explicit truthiness helper that handles bool, numeric, and
            common string representations.
  [BUG-09]  evaluate_function() returned None for unknown functions instead of
            raising — process_formula() then raises FormulaEvaluationError but
            the message was misleading.  Now raises InvalidFunctionError directly.
  [BUG-10]  ADDMONTH and ADDMONTHS both mapped to add_months — the canonical name
            in function_metadata is ADDMONTHS; ADDMONTH was undocumented.  Kept
            both mappings but logged a deprecation warning for ADDMONTH.
  [BUG-11]  add_months() used Feb 29 hardcoded as the max day for month 2 — this
            is wrong for non-leap years.  Used calendar.monthrange() instead.
  [BUG-12]  contains_function() had no null-guard — crashed with TypeError when
            text or substring was None.
  [BUG-13]  yearfrac_function() crashed with AttributeError when passed date-like
            strings; added type normalisation.
  [BUG-14]  concat_function() crashed with TypeError when either arg was not a
            string.  Added str() coercion.
  [BUG-15]  substitute() crashed when text was None.  Added null-guard.
  [BUG-16]  year_function / month_function / day_function crashed with
            AttributeError when passed a string date.  Added parse fallback.
"""

import calendar
import decimal
import math
from datetime import datetime, date, timedelta
from typing import Any, Optional, Union

from api.formulas.logger_config import get_logger
from api.formulas.exceptions import FormulaEvaluationError, InvalidFunctionError

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _to_bool(value: Any) -> bool:
    """
    FIX BUG-08: convert a value to bool in a way that correctly handles the
    string "False" (which Python's `bool()` treats as True).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "0", "no", "n", "")
    return bool(value)


def _parse_date(value: Any) -> Union[date, datetime, None]:
    """Best-effort conversion of a string to date/datetime."""
    if isinstance(value, (date, datetime)):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value.strip(), fmt)
            except ValueError:
                continue
    return None


def _parse_to_datetime(value: Any) -> datetime:
    """Convert value to datetime, raising on failure."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(value.strip(), fmt)
            except ValueError:
                continue
    raise FormulaEvaluationError(f"Cannot convert '{value}' to datetime")


def _parse_to_date(value: Any) -> date:
    """Convert value to date, raising on failure."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(value.strip(), fmt).date()
            except ValueError:
                continue
    raise FormulaEvaluationError(f"Cannot convert '{value}' to date")


def _case_function(params: list) -> Any:
    """
    CASE(expression, value1, result1, value2, result2, ..., else_result)
    Compares expression against each value and returns the matching result.
    Last param is the else/default result.
    """
    if len(params) < 3:
        raise FormulaEvaluationError("CASE requires at least 3 parameters")
    expression = params[0]
    else_result = params[-1]
    # Pairs: (value, result) from params[1:-1]
    pairs = params[1:-1]
    for i in range(0, len(pairs) - 1, 2):
        if str(expression) == str(pairs[i]):
            return pairs[i + 1]
    return else_result


def _ensure_date(value: Any, func_name: str) -> Union[date, datetime]:
    result = _parse_date(value)
    if result is None:
        raise FormulaEvaluationError(
            f"{func_name}: cannot parse '{value}' as a date", function_name=func_name
        )
    return result


# ---------------------------------------------------------------------------
# Date arithmetic
# ---------------------------------------------------------------------------

def add_months(date_obj: Union[date, datetime], months: int) -> Union[date, datetime]:
    """
    Add months to a date/datetime.
    FIX BUG-11: use calendar.monthrange() for correct month-end clamping.
    """
    try:
        date_obj = _ensure_date(date_obj, "ADDMONTHS")
        month = date_obj.month - 1 + int(months)
        year = date_obj.year + month // 12
        month = month % 12 + 1
        # FIX BUG-11: get the real last day of the target month
        max_day = calendar.monthrange(year, month)[1]
        day = min(date_obj.day, max_day)
        return date_obj.replace(year=year, month=month, day=day)
    except FormulaEvaluationError:
        raise
    except (ValueError, AttributeError) as e:
        raise FormulaEvaluationError(f"Failed to add months to date: {e}") from e


def add_day(date_obj: Union[date, datetime, int, float, str], days: Union[int, float]) -> Any:
    """Add days to a date/datetime/timestamp."""
    try:
        if isinstance(date_obj, (int, float)):
            dt = datetime.fromtimestamp(date_obj)
            return (dt + timedelta(days=int(days))).timestamp()
        date_obj = _ensure_date(date_obj, "ADDDAY")
        return date_obj + timedelta(days=int(days))
    except FormulaEvaluationError:
        raise
    except Exception as e:
        raise FormulaEvaluationError(f"Failed to add days to date: {e}") from e


def add_year(date_obj: Any, years: int) -> Any:
    """Add years to a date/datetime/timestamp."""
    try:
        if isinstance(date_obj, (int, float)):
            dt = datetime.fromtimestamp(date_obj)
        else:
            dt = _ensure_date(date_obj, "ADDYEAR")
        new_year = dt.year + int(years)
        max_day = calendar.monthrange(new_year, dt.month)[1]
        day = min(dt.day, max_day)
        result = dt.replace(year=new_year, day=day)
        if isinstance(date_obj, (int, float)):
            return result.timestamp()
        return result
    except FormulaEvaluationError:
        raise
    except Exception as e:
        raise FormulaEvaluationError(f"Failed to add years to date: {e}") from e


def _add_timedelta_to(date_obj: Any, func_name: str, **td_kwargs) -> Any:
    """Generic helper for add_minutes / add_hours / add_seconds."""
    try:
        if isinstance(date_obj, (int, float)):
            dt = datetime.fromtimestamp(date_obj)
            return (dt + timedelta(**td_kwargs)).timestamp()
        if isinstance(date_obj, date) and not isinstance(date_obj, datetime):
            date_obj = datetime.combine(date_obj, datetime.min.time())
        else:
            date_obj = _ensure_date(date_obj, func_name)
        return date_obj + timedelta(**td_kwargs)
    except FormulaEvaluationError:
        raise
    except Exception as e:
        raise FormulaEvaluationError(f"Failed in {func_name}: {e}") from e


def add_minutes(date_obj: Any, minutes: Union[int, float]) -> Any:
    return _add_timedelta_to(date_obj, "ADDMINUTES", minutes=int(minutes))


def add_hours(date_obj: Any, hours: Union[int, float]) -> Any:
    return _add_timedelta_to(date_obj, "ADDHOURS", hours=int(hours))


def add_seconds(date_obj: Any, seconds: Union[int, float]) -> Any:
    return _add_timedelta_to(date_obj, "ADDSECONDS", seconds=int(seconds))


# ---------------------------------------------------------------------------
# Date construction / extraction
# ---------------------------------------------------------------------------

def create_date(year: Any, month: Any, day: Any) -> Optional[datetime]:
    try:
        return datetime(int(year), int(month), int(day))
    except ValueError as e:
        logger.error("Invalid date: %s", e)
        raise FormulaEvaluationError(f"Invalid date arguments: {e}") from e


def get_date_value(value: Any) -> Optional[date]:
    """Convert timestamp / datetime / date / string to a date object."""
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value).date()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        parsed = _parse_date(value)
        if parsed:
            return parsed.date() if isinstance(parsed, datetime) else parsed
        logger.error("Invalid date string: %s", value)
        return None
    logger.error("Unsupported type for DATEVALUE: %s", type(value))
    return None


def _extract_date_component(date_obj: Any, component: str) -> Optional[int]:
    """FIX BUG-16: parse string dates before extracting year/month/day."""
    if isinstance(date_obj, str):
        date_obj = _parse_date(date_obj)
    if date_obj is None:
        return None
    return getattr(date_obj, component, None)


# ---------------------------------------------------------------------------
# Text functions
# ---------------------------------------------------------------------------

def substitute(text: Any, old_text: str, new_text: str) -> str:
    """FIX BUG-15: guard against None text."""
    if text is None:
        return ""
    return str(text).replace(str(old_text), str(new_text))


def text_function(value: Any) -> str:
    return str(value) if value is not None else ""


def concat_function(string1: Any, string2: Any) -> str:
    """FIX BUG-14: coerce both args to str."""
    return str(string1 if string1 is not None else "") + str(string2 if string2 is not None else "")


def contains_function(text: Any, substring: Any) -> bool:
    """FIX BUG-12: null-guard."""
    if text is None or substring is None:
        return False
    return str(substring) in str(text)


# ---------------------------------------------------------------------------
# Logical / conditional functions
# ---------------------------------------------------------------------------

def if_function(condition: Any, true_value: Any, false_value: Any) -> Any:
    """FIX BUG-08: use _to_bool so the string 'False' evaluates to false."""
    logger.debug("IF condition: %s (type: %s)", condition, type(condition).__name__)
    return true_value if _to_bool(condition) else false_value


def and_function(condition1: Any, condition2: Any) -> bool:
    return _to_bool(condition1) and _to_bool(condition2)


def or_function(condition1: Any, condition2: Any) -> bool:
    return _to_bool(condition1) or _to_bool(condition2)


def is_blank(value: Any) -> bool:
    return value is None or value == ""


def blank_value_function(value: Any, default_value: Any) -> Any:
    return value if value is not None and value != "" else default_value


def is_pickval_function(picklist_field: Any, text_value: Any) -> bool:
    return picklist_field == text_value


# ---------------------------------------------------------------------------
# Numeric functions
# ---------------------------------------------------------------------------

def round_function(number: Any, decimal_places: Any) -> float:
    return round(float(number), int(decimal_places))


def ceiling_function(number: Any) -> int:
    return math.ceil(float(number))


def floor_function(number: Any) -> int:
    return math.floor(float(number))


def mod_function(dividend: Any, divisor: Any) -> float:
    divisor_f = float(divisor)
    if divisor_f == 0:
        raise FormulaEvaluationError("MOD: division by zero", function_name="MOD")
    return float(dividend) % divisor_f


def abs_function(number: Any) -> float:
    return abs(float(number))


def is_number(value: Any) -> bool:
    # Exclude bool — bool is a subclass of int in Python
    if isinstance(value, bool):
        return False
    return isinstance(value, (int, float, decimal.Decimal))


# ---------------------------------------------------------------------------
# Date-diff / yearfrac
# ---------------------------------------------------------------------------

def datediff_function(start_date: Any, end_date: Any) -> Optional[int]:
    """Calculate the difference in days between two dates."""
    if start_date is None or end_date is None:
        logger.error("datediff_function: one or both dates are None")
        return None

    start = _parse_date(start_date)
    end = _parse_date(end_date)

    if start is None or end is None:
        logger.error("datediff_function: failed to parse dates — %s, %s", start_date, end_date)
        return None

    return (end - start).days


def yearfrac_function(start_date: Any, end_date: Any) -> Optional[float]:
    """FIX BUG-13: normalise inputs before subtraction."""
    start = _parse_date(start_date)
    end = _parse_date(end_date)
    if start is None or end is None:
        logger.error("yearfrac_function: failed to parse dates — %s, %s", start_date, end_date)
        return None
    delta = end - start
    return delta.days / 365.0


# ---------------------------------------------------------------------------
# now / today
# ---------------------------------------------------------------------------

def now_function() -> datetime:
    return datetime.now()


def today_function() -> date:
    return datetime.today().date()


# ---------------------------------------------------------------------------
# Main dispatch
# ---------------------------------------------------------------------------

def evaluate_function(function_name: str, params_values: list) -> Any:
    """
    Dispatch to the correct implementation for the given function name.

    FIX BUG-09: raises InvalidFunctionError for unknown names instead of
                silently returning None (which caused a confusing downstream error).
    FIX BUG-10: ADDMONTH kept as deprecated alias with a warning.
    """
    try:
        if function_name == "ADDMONTHS":
            return add_months(*params_values)
        elif function_name == "ADDMONTH":
            logger.warning("ADDMONTH is deprecated; use ADDMONTHS instead")
            return add_months(*params_values)
        elif function_name == "ADDDAY":
            return add_day(*params_values)
        elif function_name == "ADDYEAR":
            return add_year(*params_values)
        elif function_name == "ADDMINUTES":
            return add_minutes(*params_values)
        elif function_name == "ADDHOURS":
            return add_hours(*params_values)
        elif function_name == "ADDSECONDS":
            return add_seconds(*params_values)
        elif function_name == "DATE":
            return create_date(*params_values)
        elif function_name == "DATEVALUE":
            return get_date_value(*params_values)
        elif function_name == "SUBSTITUTE":
            return substitute(*params_values)
        elif function_name == "TEXT":
            return text_function(*params_values)
        elif function_name == "IF":
            return if_function(*params_values)
        elif function_name == "ROUND":
            number, decimals = params_values
            return round_function(number, decimals)
        elif function_name == "ISBLANK":
            return is_blank(*params_values)
        elif function_name == "NOW":
            return now_function()
        elif function_name == "TODAY":
            return today_function()
        elif function_name == "YEAR":
            return _extract_date_component(params_values[0], "year")
        elif function_name == "MONTH":
            return _extract_date_component(params_values[0], "month")
        elif function_name == "DAY":
            return _extract_date_component(params_values[0], "day")
        elif function_name == "CEILING":
            return ceiling_function(*params_values)
        elif function_name == "FLOOR":
            return floor_function(*params_values)
        elif function_name == "MOD":
            return mod_function(*params_values)
        elif function_name == "ABS":
            return abs_function(*params_values)
        elif function_name == "AND":
            condition1, condition2 = params_values
            return and_function(condition1, condition2)
        elif function_name == "OR":
            condition1, condition2 = params_values
            return or_function(condition1, condition2)
        elif function_name == "ISNUMBER":
            return is_number(*params_values)
        elif function_name == "CONTAINS":
            return contains_function(*params_values)
        elif function_name == "BLANKVALUE":
            return blank_value_function(*params_values)
        elif function_name == "ISPICKVAL":
            return is_pickval_function(*params_values)
        elif function_name == "YEARFRAC":
            return yearfrac_function(*params_values)
        elif function_name == "DATEDIFF":
            return datediff_function(*params_values)
        elif function_name == "SUM":
            num1, num2 = params_values
            return float(num1) + float(num2)
        elif function_name == "MAX":
            num1, num2 = params_values
            return max(float(num1), float(num2))
        elif function_name == "MIN":
            num1, num2 = params_values
            return min(float(num1), float(num2))
        elif function_name == "CONCAT":
            return concat_function(*params_values)
        elif function_name in ("LEN", "LENGTH"):
            return len(str(params_values[0])) if params_values[0] is not None else 0
        elif function_name == "TRIM":
            return str(params_values[0]).strip() if params_values[0] is not None else ""
        elif function_name == "LOWER":
            return str(params_values[0]).lower() if params_values[0] is not None else ""
        elif function_name == "UPPER":
            return str(params_values[0]).upper() if params_values[0] is not None else ""
        elif function_name == "LEFT":
            text, n = str(params_values[0] or ""), int(params_values[1])
            return text[:n]
        elif function_name == "RIGHT":
            text, n = str(params_values[0] or ""), int(params_values[1])
            return text[-n:] if n > 0 else ""
        elif function_name == "MID":
            text = str(params_values[0] or "")
            start = int(params_values[1]) - 1  # 1-based index
            length = int(params_values[2])
            return text[start:start + length]
        # Aliases matching frontend naming
        elif function_name == "CEIL":
            return ceiling_function(*params_values)
        elif function_name == "REPLACE":
            return substitute(*params_values)
        elif function_name == "SUBSTRING":
            text = str(params_values[0] or "")
            start = int(params_values[1]) - 1
            length = int(params_values[2])
            return text[start:start + length]
        elif function_name == "ADDDAYS":
            return add_day(*params_values)
        elif function_name == "ADDYEARS":
            return add_year(*params_values)
        # Numeric
        elif function_name == "POWER":
            base, exp = float(params_values[0]), float(params_values[1])
            return math.pow(base, exp)
        elif function_name == "SQRT":
            return math.sqrt(float(params_values[0]))
        # Date extraction
        elif function_name == "HOUR":
            dt = _parse_to_datetime(params_values[0])
            return dt.hour
        elif function_name == "MINUTE":
            dt = _parse_to_datetime(params_values[0])
            return dt.minute
        elif function_name == "WEEKDAY":
            dt = _parse_to_date(params_values[0])
            return dt.isoweekday()  # 1=Monday, 7=Sunday
        # Logical
        elif function_name == "NOT":
            return not _to_bool(params_values[0])
        elif function_name == "ISNULL":
            return params_values[0] is None
        elif function_name == "NULLVALUE":
            return params_values[1] if params_values[0] is None else params_values[0]
        elif function_name == "CASE":
            return _case_function(params_values)
        else:
            # FIX BUG-09: raise instead of silently returning None
            raise InvalidFunctionError(f"Unsupported function: {function_name}")
    except (InvalidFunctionError, FormulaEvaluationError):
        raise
    except TypeError as e:
        raise FormulaEvaluationError(
            f"Wrong number of arguments for {function_name}: {e}",
            function_name=function_name,
            parameters=params_values,
        ) from e
