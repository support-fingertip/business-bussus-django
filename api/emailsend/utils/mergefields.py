from django.apps import apps
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import re 
from psycopg2 import sql
from django.db import connection
from pprint import pprint
from datetime import datetime






def replace_merge_fields(template, object_name, record_data):
    """
    Replace merge fields in the format {!Model.Field} or {!Model.Field, Default}
    Using a dictionary (record_data) fetched from raw SQL
    """
    pattern = r"{!([\w]+)\.([\w]+)(?:,\s*(.*?))?}"

    def replacer(match):
        model_name, field_name, default = match.groups()

        if model_name == object_name and field_name in record_data:
            print(f"Replacing merge field for {model_name}.{field_name} with value: {record_data[field_name]['value']} and datatype: {record_data[field_name]['datatype']}  Default: {default}")
            value = record_data[field_name]["value"]
            if isinstance(value, datetime):
                value = value.strftime("%d-%m-%Y")
        else:
            value = None

        return str(value if value is not None else (default if default is not None else ''))

    return re.sub(pattern, replacer, template)

def is_html_template(template):
    return bool(re.search(r'</?(html|head|body|p|div|span|br|h\d|strong|em|table|tr|td|a)[^>]*>', template, re.IGNORECASE))



def get_record_from_sql(table_name, record_id, schema):
    try:
        with connection.cursor() as cursor:
            query = sql.SQL("SELECT * FROM {}.{} WHERE id = %s").format(
                sql.Identifier(schema),
                sql.Identifier(table_name)
            )
            field_types_query = sql.SQL("SELECT name, datatype FROM {}.fields WHERE object_name = %s").format(
                sql.Identifier(schema)
            )
            cursor.execute(field_types_query, [table_name])
            field_types = {name: dtype for name, dtype in cursor.fetchall()}
            cursor.execute(query, [record_id])
            desc = [col[0] for col in cursor.description]
            row = cursor.fetchone()
            if not row:
                raise Exception(f"Record with ID {record_id} not found in {table_name}.")
            result = {}
            for col_name, value, col_meta in zip(desc, row, cursor.description):
                datatype = field_types.get(col_name, col_meta.type_code)
                if col_name in {"owner_id", "created_by", "last_modified_by_id", "last_modified_by","created_by_id"}:
                    cursor.execute(
                        sql.SQL("SELECT name FROM {}.users WHERE id = %s").format(sql.Identifier(schema)),
                        [value],
                    )
                    user_row = cursor.fetchone()
                    if user_row and user_row[0]:
                        value = user_row[0]
                elif datatype == 'lookup_relationship' and value is not None:
                    cursor.execute(
                        sql.SQL("SELECT name FROM {}.{} WHERE id = %s").format(
                            sql.Identifier(schema),
                            sql.Identifier(col_name[:-3])
                        ),
                        [value],
                    )
                    related_row = cursor.fetchone()
                    if related_row and related_row[0]:
                        value = related_row[0]
                result[col_name] = {
                    "value": value,
                    "datatype": datatype,
                }
            return result
    except Exception as e:
        raise Exception(f"Error fetching record: {str(e)}")
    
def get_object_details(table_name, schema):
    try:
        with connection.cursor() as cursor:
            query = sql.SQL("SELECT id, name FROM {}.object WHERE name = %s").format(
                sql.Identifier(schema)
            )
            cursor.execute(query, [table_name])
            record = cursor.fetchone()
            if not record:
                raise Exception(f"Object '{table_name}' not found.")
            return dict(zip(['id', 'name'], record))
    except Exception as e:
        raise Exception(f"Error fetching object details: {str(e)}")