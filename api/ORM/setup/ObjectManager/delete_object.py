from django.db import connection, transaction

from api.ORM.AuditLogs.audit_trail_logs import log_audit

def delete_customobject(name, **kwargs):
    schema = kwargs.get('schema', 'public')
    """
    Deletes a custom object and all related records using raw SQL queries.
    """
    try:
        if not name:
            raise Exception("Object name is required.")

        with connection.cursor() as cursor, transaction.atomic():
            # Check if object exists
            cursor.execute(f"SET search_path TO {schema};")
            cursor.execute("SELECT id, type FROM object WHERE name = %s", [name])
            row = cursor.fetchone()
            if not row:
                raise Exception(f"Object '{name}' does not exist.")
            
            if row[1] == 'standard':
                raise Exception(f"Object '{name}' is a standard can't delete it.")
                

            object_id = row[0]

            # Delete related fields
            cursor.execute("DELETE FROM fields WHERE object_id = %s", [object_id])

            # Delete field permissions
            cursor.execute("DELETE FROM field_permissions WHERE object_id = %s", [object_id])

            # Delete object permissions
            cursor.execute("DELETE FROM object_permissions WHERE object_id = %s", [object_id])

            # Delete list views
            cursor.execute("DELETE FROM listviews WHERE object_id = %s", [object_id])

            # Delete page layouts
            cursor.execute("DELETE FROM page_layouts WHERE object_name = %s", [name])

            # Delete search layouts
            cursor.execute("DELETE FROM search_layouts WHERE object_id = %s", [object_id])

            # ✅ Delete sharing records before deleting the object
            cursor.execute("DELETE FROM sharing_records WHERE object_id = %s", [object_id])

            # ✅ Delete sharing records before deleting the object
            cursor.execute("DELETE FROM tab_permissions WHERE object_id = %s", [object_id])

            # Delete the object itself
            cursor.execute("DELETE FROM object WHERE id = %s", [object_id])
            
            try:
                remove_tab_from_apps(name, schema)
            except Exception as e:
                print(str(e))
            try:
                query = f"DROP TABLE IF EXISTS {name} CASCADE;"
                cursor.execute(query)            
            except Exception as e:
                print(str(e))
            log_audit(
                'Deleted custom object {name} and its related records',
                'Custom Object Deletion',
                **kwargs
            )
        return {
            "success": True,
            "message": f"Custom object '{name}' and its related records have been deleted successfully."
        }

    except Exception as e:
        raise Exception(str(e))
    
    
def remove_tab_from_apps(name: str, schema: str):
    """
    Remove an object from the JSONB 'tabs' array in <schema>.apps
    where elem->>'name' equals the given name.
    """
    sql = f"""
        UPDATE {schema}.app
        SET tabs = (
            SELECT COALESCE(
                jsonb_agg(elem),
                '[]'::jsonb
            )
            FROM jsonb_array_elements(tabs) AS elem
            WHERE elem->>'name' <> %s
        )
        WHERE tabs IS NOT NULL;
    """

    with connection.cursor() as cursor:
        cursor.execute(sql, [name])
