"""
Schema name validation utility to prevent SQL injection.

Schema names should only contain alphanumeric characters, underscores, and must not
exceed PostgreSQL identifier length limits.
"""
import re
from django.core.exceptions import ValidationError

def validate_schema_name(schema_name):
    """
    Validate that a schema name is safe to use in SQL queries.
    
    Args:
        schema_name (str): The schema name to validate
        
    Returns:
        bool: True if valid
        
    Raises:
        ValidationError: If schema name is invalid
    """
    if not schema_name:
        raise ValidationError("Schema name cannot be empty")
    
    # Check length (PostgreSQL identifier limit is 63 characters)
    if len(schema_name) > 63:
        raise ValidationError("Schema name cannot exceed 63 characters")
    
    # Check for valid characters (alphanumeric, underscore, must start with letter or underscore)
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', schema_name):
        raise ValidationError(
            "Schema name must start with a letter or underscore and contain only "
            "alphanumeric characters and underscores"
        )
    
    # Check for PostgreSQL reserved keywords (basic set)
    reserved_keywords = {
        'public', 'information_schema', 'pg_catalog', 'pg_toast'
    }
    if schema_name.lower() in reserved_keywords:
        raise ValidationError(f"Schema name '{schema_name}' is a reserved keyword")
    
    # Check for PostgreSQL reserved schema patterns
    if schema_name.lower().startswith('pg_'):
        raise ValidationError("Schema names starting with 'pg_' are reserved for PostgreSQL system schemas")
    
    return True

def get_safe_schema_name(schema_name):
    """
    Validate and return a safe schema name or raise ValidationError.
    
    Args:
        schema_name (str): The schema name to validate
        
    Returns:
        str: The validated schema name
        
    Raises:
        ValidationError: If schema name is invalid
    """
    validate_schema_name(schema_name)
    return schema_name
