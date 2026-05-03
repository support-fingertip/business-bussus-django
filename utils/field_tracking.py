from api.security.schema_authority import get_validated_schema
from django.db import connection
from django.db import transaction

# def get_field_tracking_data(object_name):
#     result = []

#     with connection.cursor() as cursor:
#         # Step 1: Get all fields for the given object
#         cursor.execute("""
#             SELECT id, name, label
#             FROM fields
#             WHERE object_name = %s
#         """, [object_name])
#         all_fields = cursor.fetchall()

#         # Step 2: Get tracked field names
#         cursor.execute("""
#             SELECT field_name
#             FROM field_tracking_config
#             WHERE object_name = %s AND is_tracked = TRUE
#         """, [object_name])
#         tracked_fields = set(row[0] for row in cursor.fetchall())

#         # Step 3: Construct response
#         for field_id, field_name, field_label in all_fields:
#             result.append({
#                 "id": field_id,
#                 "name": field_name,
#                 "label": field_label,
#                 "is_tracked": field_name in tracked_fields
#             })

#     return {"fields": result}

def get_field_tracking_data(object_name, **kwargs):
    result = []
    schema = (get_validated_schema(kwargs) or 'public')

    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO %s", [schema])
        # Get object_id
        cursor.execute("SELECT id FROM object WHERE name = %s", [object_name])
        row = cursor.fetchone()
        if not row:
            return {"fields": []}
        object_id = row[0]

        # Get all fields
        cursor.execute("""
            SELECT id, name, label
            FROM fields
            WHERE object_id = %s
        """, [object_id])
        all_fields = cursor.fetchall()

        # Get tracked fields
        cursor.execute("""
            SELECT field_name
            FROM field_tracking_config
            WHERE object_name = %s AND is_tracked = TRUE
        """, [object_name])
        tracked_fields = set(row[0] for row in cursor.fetchall())

        # Build result
        for field_id, field_name, field_label in all_fields:
            result.append({
                "id": field_id,
                "name": field_name,
                "label": field_label,
                "is_tracked": field_name in tracked_fields
            })

    return {"fields": result}


def update_tracked_fields(object_name, selected_field_ids,**kwargs):
    if not object_name:
        raise Exception("Missing 'object_name'.")

    if not isinstance(selected_field_ids, list):
        raise Exception("'tracked_fields' must be a list of field IDs.")

    schema = (get_validated_schema(kwargs) or 'public')

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO %s", [schema])
            # Check if object exists
            cursor.execute("""
                SELECT id FROM object WHERE name = %s
            """, [object_name])
            obj = cursor.fetchone()
            if not obj:
                raise Exception("Object with provided name does not exist.")

            # Delete previous tracking config for this object
            cursor.execute("""
                DELETE FROM field_tracking_config
                WHERE object_name = %s
            """, [object_name])

            if not selected_field_ids:
                return {'message': 'Tracked fields cleared successfully.'}

            # Get field names for selected field IDs
            cursor.execute("""
                SELECT id, name FROM fields
                WHERE id IN %s
            """, [tuple(selected_field_ids)])
            fields = cursor.fetchall()

            if not fields:
                return {'message': 'No matching fields found.'}

            # Insert new tracked fields
            insert_values = [
                (object_name, field_name, True)
                for _, field_name in fields
            ]
            cursor.executemany("""
                INSERT INTO field_tracking_config (object_name, field_name, is_tracked)
                VALUES (%s, %s, %s)
            """, insert_values)
    return {'message': 'Tracked fields updated successfully.'}



def get_field_history(object_name, record_id, schema=None):
    # query = """
    #     SELECT field_name, old_value, new_value, changed_at, user_id
    #     FROM field_history_log

    #     WHERE object_name = %s AND record_id = %s
    #     ORDER BY changed_at DESC
    # """
    query = """SELECT
                fhl.field_name,
                fhl.old_value,
                fhl.new_value,
                fhl.changed_at,
                fhl.user_id,
                u.name,
                u.email
            FROM field_history_log fhl
            LEFT JOIN public.users u ON fhl.user_id = u.id
            WHERE fhl.object_name = %s
            AND fhl.record_id = %s
            ORDER BY fhl.changed_at DESC;"""
    return run_raw_query(query, [object_name, str(record_id)], fetchall=True, schema=schema)

def run_raw_query(query, params=None, fetchone=False, fetchall=False, schema='public'): 
    with connection.cursor() as cursor: 
        cursor.execute("SET search_path TO %s", [schema]) 
        # Ensure the search path is set to the specified schema 
        cursor.execute(query, params or []) 
        if fetchone: 
            return cursor.fetchone() 
        if fetchall: 
            return cursor.fetchall()
