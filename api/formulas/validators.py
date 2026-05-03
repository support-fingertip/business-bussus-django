"""
Validation utilities for formula inputs.

This module provides functions for validating and sanitizing
formula inputs to handle edge cases and prevent errors.
"""
from typing import Any, Dict, Optional
from datetime import datetime, date

from api.formulas.logger_config import get_logger
from api.formulas.exceptions import FormulaValidationError

logger = get_logger(__name__)


def validate_field_value(
    field_name: str,
    value: Any,
    expected_type: Optional[str] = None
) -> Any:
    """
    Validate and sanitize a field value.
    
    Args:
        field_name: Name of the field
        value: The value to validate
        expected_type: Expected data type
        
    Returns:
        Validated and sanitized value
        
    Raises:
        FormulaValidationError: If validation fails
    """
    # Handle None/null values
    if value is None:
        logger.debug(f"Field '{field_name}' has None value")
        return None
    
    # Handle empty strings
    if isinstance(value, str) and value.strip() == '':
        logger.debug(f"Field '{field_name}' has empty string value")
        return None
    
    # Type-specific validation
    if expected_type:
        if expected_type in ['number', 'currency', 'percent']:
            return validate_numeric(field_name, value)
        elif expected_type in ['date', 'datetime']:
            return validate_date(field_name, value)
        elif expected_type in ['text', 'textarea', 'picklist', 'email', 'phone', 'url']:
            return validate_text(field_name, value)
        elif expected_type == 'boolean':
            return validate_boolean(field_name, value)
    
    return value


def validate_numeric(field_name: str, value: Any) -> float:
    """
    Validate and convert a numeric value.
    
    Args:
        field_name: Name of the field
        value: The value to validate
        
    Returns:
        Validated numeric value
        
    Raises:
        FormulaValidationError: If validation fails
    """
    if isinstance(value, (int, float)):
        return float(value)
    
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            raise FormulaValidationError(
                f"Cannot convert value to number",
                field_name=field_name
            )
    
    raise FormulaValidationError(
        f"Invalid numeric value type: {type(value).__name__}",
        field_name=field_name
    )


def validate_date(field_name: str, value: Any) -> datetime:
    """
    Validate and convert a date value.
    
    Args:
        field_name: Name of the field
        value: The value to validate
        
    Returns:
        Validated datetime value
        
    Raises:
        FormulaValidationError: If validation fails
    """
    if isinstance(value, datetime):
        return value
    
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    
    if isinstance(value, str):
        # Try common date formats
        for fmt in ['%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%Y/%m/%d', '%d-%m-%Y']:
            try:
                return datetime.strptime(value.strip(), fmt)
            except ValueError:
                continue
        
        raise FormulaValidationError(
            f"Cannot parse date string",
            field_name=field_name
        )
    
    raise FormulaValidationError(
        f"Invalid date value type: {type(value).__name__}",
        field_name=field_name
    )


def validate_text(field_name: str, value: Any) -> str:
    """
    Validate and convert a text value.
    
    Args:
        field_name: Name of the field
        value: The value to validate
        
    Returns:
        Validated text value
    """
    if value is None:
        return ''
    
    return str(value)


def validate_boolean(field_name: str, value: Any) -> bool:
    """
    Validate and convert a boolean value.
    
    Args:
        field_name: Name of the field
        value: The value to validate
        
    Returns:
        Validated boolean value
    """
    if isinstance(value, bool):
        return value
    
    if isinstance(value, str):
        value_lower = value.lower().strip()
        if value_lower in ['true', '1', 'yes', 'y']:
            return True
        elif value_lower in ['false', '0', 'no', 'n']:
            return False
    
    return bool(value)


def sanitize_record(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitize a record dictionary to handle edge cases.
    
    Args:
        record: The record dictionary to sanitize
        
    Returns:
        Sanitized record dictionary
    """
    sanitized = {}
    
    for key, value in record.items():
        # Handle None values
        if value is None:
            sanitized[key] = None
            continue
        
        # Handle empty strings
        if isinstance(value, str) and value.strip() == '':
            sanitized[key] = None
            continue
        
        # Keep the value as is
        sanitized[key] = value
    
    return sanitized
