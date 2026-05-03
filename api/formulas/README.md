# Formula Processing Module

## Overview

This module provides a secure and efficient implementation for processing Salesforce-like formulas in Django applications. It includes formula validation, evaluation, and support for a wide range of functions.

## Features

- **Secure Expression Evaluation**: Uses AST-based parsing instead of `eval()` to prevent code injection
- **Comprehensive Function Library**: Supports 30+ functions including date/time, mathematical, text, and logical operations
- **Type Safety**: Strong type checking and validation
- **Performance Optimization**: Caching mechanisms for frequently used formulas
- **Proper Error Handling**: Custom exception classes for detailed error reporting
- **Logging**: Comprehensive logging for debugging and monitoring

## Security Improvements

### Before
```python
# INSECURE - Direct eval() usage
result = eval(expression)  # Vulnerable to code injection
```

### After
```python
# SECURE - AST-based safe evaluation
from api.formulas.safe_evaluator import safe_evaluate
result = safe_evaluate(expression, context)  # Safe from injection
```

## Module Structure

```
api/formulas/
├── __init__.py
├── evaluate_formula.py       # Formula evaluation logic
├── formula_validation.py     # Formula validation
├── functions_and_conditions.py  # Function implementations
├── functions_metadata.py     # Function metadata and signatures
├── safe_evaluator.py         # Secure expression evaluator
├── exceptions.py             # Custom exception classes
├── logger_config.py          # Logging configuration
├── cache.py                  # Caching utilities
├── validators.py             # Input validation utilities
└── test_formulas.py          # Unit tests
```

## Usage Examples

### Basic Formula Evaluation

```python
from api.formulas.evaluate_formula import process_formula

# Simple arithmetic
record = {"price": 100, "quantity": 5}
result = process_formula("price * quantity", "total", record)
# Result: 500

# Date functions
record = {"created_date": datetime(2024, 1, 1)}
result = process_formula("ADDMONTH(created_date, 6)", "due_date", record)
# Result: datetime(2024, 7, 1)

# Conditional logic
record = {"amount": 1000}
result = process_formula('IF(amount > 500, "High", "Low")', "category", record)
# Result: "High"
```

### Formula Validation

```python
from api.formulas.formula_validation import validate_formula

# Define field metadata
fields_metadata = {
    "price": "number",
    "quantity": "number",
    "total": "number"
}

# Validate formula
try:
    return_type = validate_formula(
        "price * quantity",
        fields_metadata,
        "total"
    )
    print(f"Formula is valid, returns: {return_type}")
except FormulaValidationError as e:
    print(f"Validation error: {e}")
```

## Supported Functions

### Date/Time Functions
- `DATE(year, month, day)` - Create a date
- `ADDDAY(date, days)` - Add days to a date
- `ADDMONTH(date, months)` - Add months to a date
- `ADDYEAR(date, years)` - Add years to a date
- `ADDHOURS(datetime, hours)` - Add hours to datetime
- `ADDMINUTES(datetime, minutes)` - Add minutes to datetime
- `ADDSECONDS(datetime, seconds)` - Add seconds to datetime
- `TODAY()` - Get current date
- `NOW()` - Get current datetime
- `YEAR(date)` - Extract year from date
- `MONTH(date)` - Extract month from date
- `DAY(date)` - Extract day from date
- `DATEDIFF(date1, date2)` - Calculate days between dates
- `YEARFRAC(date1, date2)` - Calculate years between dates

### Mathematical Functions
- `SUM(num1, num2)` - Sum two numbers
- `MAX(num1, num2)` - Maximum of two numbers
- `MIN(num1, num2)` - Minimum of two numbers
- `ROUND(number, decimals)` - Round to decimal places
- `CEILING(number)` - Round up to integer
- `FLOOR(number)` - Round down to integer
- `MOD(dividend, divisor)` - Modulo operation
- `ABS(number)` - Absolute value

### Text Functions
- `TEXT(value)` - Convert to text
- `CONCAT(string1, string2)` - Concatenate strings
- `SUBSTITUTE(text, old, new)` - Replace text
- `CONTAINS(text, substring)` - Check if text contains substring

### Logical Functions
- `IF(condition, true_value, false_value)` - Conditional expression
- `AND(condition1, condition2)` - Logical AND
- `OR(condition1, condition2)` - Logical OR
- `ISBLANK(value)` - Check if value is blank
- `ISNUMBER(value)` - Check if value is a number
- `ISPICKVAL(field, value)` - Check picklist value
- `BLANKVALUE(value, default)` - Return default if blank

## Configuration

### Logging

Configure logging level in your Django settings:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'api.formulas': {
            'handlers': ['console'],
            'level': 'INFO',  # Change to DEBUG for detailed logs
        },
    },
}
```

### Performance Tuning

Adjust cache settings:

```python
from api.formulas.cache import get_formula_cache

# Set maximum cache size
cache = get_formula_cache()
cache._max_size = 2000  # Default is 1000

# Clear cache if needed
cache.clear()
```

## Error Handling

The module provides custom exceptions for different error scenarios:

- `FormulaError` - Base exception for all formula errors
- `FormulaValidationError` - Validation failures
- `FormulaEvaluationError` - Evaluation failures
- `InvalidFunctionError` - Invalid or unsupported functions
- `InvalidParameterError` - Invalid function parameters
- `TypeMismatchError` - Type mismatches
- `RecursionLimitError` - Maximum recursion depth exceeded

## Testing

Run the test suite:

```bash
python -m unittest api.formulas.test_formulas -v
```

## Best Practices

1. **Always validate formulas** before evaluation in production
2. **Use type hints** for better code maintainability
3. **Handle exceptions** appropriately in your views
4. **Monitor performance** using the logging facilities
5. **Cache frequently used formulas** for better performance
6. **Set appropriate recursion limits** to prevent infinite loops

## Migration Guide

If you're migrating from the old implementation:

### Old Code
```python
# Unsafe evaluation
result = eval(formula)
print(f"Result: {result}")
```

### New Code
```python
from api.formulas.evaluate_formula import process_formula
from api.formulas.exceptions import FormulaEvaluationError
import logging

logger = logging.getLogger(__name__)

try:
    result = process_formula(formula, field_name, record)
    logger.info(f"Result: {result}")
except FormulaEvaluationError as e:
    logger.error(f"Formula evaluation failed: {e}")
    raise
```

## Performance Considerations

- Formula parsing is cached to avoid redundant operations
- Use the cache for frequently evaluated formulas
- Set appropriate max_depth limits for recursive formulas (default: 50)
- Monitor log levels in production (use INFO or WARNING)

## Contributing

When adding new functions:

1. Add the function implementation to `functions_and_conditions.py`
2. Add metadata to `functions_metadata.py`
3. Update this README with the new function
4. Add unit tests to `test_formulas.py`
5. Ensure proper error handling and logging

## License

This module is part of the Bussus-backend project.
