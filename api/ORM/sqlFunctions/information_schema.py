from api.security.schema_authority import get_validated_schema
from django.db import connection


def get_information_schema(search_table=None, **kwargs):
    """
    Retrieve the information schema for all tables in the database.
    
    Returns:
        dict: A dictionary where keys are table names and values are lists of column details.
    """
    schema = get_validated_schema(kwargs)  # Default schema is 'public'
    query = """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s
    """
    
    # If search_table is provided, modify the query to filter the table names
    if search_table:
        query += " AND table_name ILIKE %s"
        params = [schema, '%' + search_table + '%']
    else:
        params = [schema]
    
    query += " ORDER BY table_name, ordinal_position;"
    
    with connection.cursor() as cursor:
        cursor.execute(query, params)
        rows = cursor.fetchall()
        
    # Transform rows into a structured format
    schema_info = {}
    for table_name, column_name, data_type in rows:
        if table_name not in schema_info:
            schema_info[table_name] = []
        schema_info[table_name].append({
            "column_name": column_name,
            "data_type": data_type
        })
    
    return schema_info


def get_column_data_types(table_name, fields, **kwargs):
    """
    Fetch the data types of given fields from the information_schema.
    Returns a dictionary with field names as keys and their data types as values.
    """
    query = """
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = %s AND column_name = ANY(%s) AND table_schema = %s;
    """
    with connection.cursor() as cur:
        cur.execute(query, (table_name, fields, get_validated_schema(kwargs)))
        result = cur.fetchall()
    
    # Convert the result into a dictionary
    column_data_types = {row[0]: row[1] for row in result}
    return column_data_types


def is_deleted_field_exist(table_name, schema=None) -> bool:
    """
    Returns True if column `is_deleted` exists on given table in given schema.
    """
    return column_exists(table_name, 'is_deleted', schema)


def column_exists(table_name, column_name, schema=None) -> bool:
    schema = schema or 'public'

    query = """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name   = %s
          AND column_name  = %s
        LIMIT 1;
    """

    with connection.cursor() as cursor:
        cursor.execute(query, [schema, table_name, column_name])
        return cursor.fetchone() is not None

