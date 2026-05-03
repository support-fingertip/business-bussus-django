"""
Shared utility functions for database schema operations.
"""
from django.core.exceptions import ValidationError
import re


# Comprehensive list of PostgreSQL reserved keywords
POSTGRES_RESERVED_KEYWORDS = {
    'all', 'analyse', 'analyze', 'and', 'any', 'array', 'as', 'asc', 'asymmetric',
    'authorization', 'binary', 'both', 'case', 'cast', 'check', 'collate', 'collation',
    'column', 'concurrently', 'constraint', 'create', 'cross', 'current_catalog',
    'current_date', 'current_role', 'current_schema', 'current_time', 'current_timestamp',
    'current_user', 'default', 'deferrable', 'desc', 'distinct', 'do', 'else', 'end',
    'except', 'false', 'fetch', 'for', 'foreign', 'freeze', 'from', 'full', 'grant',
    'group', 'having', 'ilike', 'in', 'initially', 'inner', 'intersect', 'into', 'is',
    'isnull', 'join', 'lateral', 'leading', 'left', 'like', 'limit', 'localtime',
    'localtimestamp', 'natural', 'not', 'notnull', 'null', 'offset', 'on', 'only',
    'or', 'order', 'outer', 'overlaps', 'placing', 'primary', 'references', 'returning',
    'right', 'select', 'session_user', 'similar', 'some', 'symmetric', 'table',
    'tablesample', 'then', 'to', 'trailing', 'true', 'union', 'unique', 'user', 'using',
    'variadic', 'verbose', 'when', 'where', 'window', 'with',
    # Schema-specific reserved names
    'public', 'information_schema', 'pg_catalog', 'pg_toast', 'pg_temp', 'pg_toast_temp',
}


def validate_schema_name(schema_name):
    """
    Validate schema name to prevent SQL injection and ensure PostgreSQL compatibility.
    
    This function performs comprehensive validation including:
    - Non-empty check
    - Length validation (PostgreSQL identifier limit is 63 characters)
    - Format validation (must start with letter or underscore, followed by alphanumeric or underscore)
    - Reserved keyword checking
    
    Args:
        schema_name: The schema name to validate
        
    Raises:
        ValidationError: If schema name is invalid
        
    Examples:
        >>> validate_schema_name("my_schema")  # Valid
        >>> validate_schema_name("public")  # Raises ValidationError (reserved keyword)
        >>> validate_schema_name("123schema")  # Raises ValidationError (starts with number)
    """
    if not schema_name:
        raise ValidationError("Schema name cannot be empty")
    
    # Check length (PostgreSQL identifier limit is 63)
    if len(schema_name) > 63:
        raise ValidationError("Schema name too long (max 63 characters)")
    
    # Check format: must start with letter or underscore, followed by alphanumeric or underscore
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', schema_name):
        raise ValidationError(
            "Invalid schema name format: must start with letter or underscore, "
            "followed by alphanumeric characters or underscores"
        )
    
    # Check against reserved keywords (case-insensitive)
    if schema_name.lower() in POSTGRES_RESERVED_KEYWORDS:
        raise ValidationError(f"Schema name '{schema_name}' is a reserved PostgreSQL keyword")
