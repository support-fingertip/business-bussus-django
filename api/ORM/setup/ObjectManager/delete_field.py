from django.db import connection, transaction
import json
from psycopg2 import sql

from api.ORM.AuditLogs.audit_trail_logs import log_audit

def delete_field(data, user=None, section=None ,**kwargs):
    """
    Deletes a field from an object using raw SQL and updates related layouts, list views, and permissions atomically.
    """
    schema = kwargs.get('schema', 'public')
    object_name = data.get('object')
    field_name = data.get('field_name')
    try:
        if not object_name or not field_name:
            raise Exception("Object name and field name are required.")

        with connection.cursor() as cursor, transaction.atomic():
            # Set the search path to the specified schema
            cursor.execute(f"SET search_path TO {schema};")
            # ✅ Get object ID
            cursor.execute("SELECT id, prefix FROM object WHERE name = %s", [object_name])
            object_row = cursor.fetchone()
            if not object_row:
                raise Exception(f"Object '{object_name}' does not exist.")
            object_id, object_prefix = object_row

            # ✅ Get field metadata ID
            cursor.execute("SELECT id FROM fields WHERE object_id = %s AND name = %s", [object_id, field_name])
            field_row = cursor.fetchone()
            if not field_row:
                raise Exception(f"Field '{field_name}' does not exist in object '{object_name}'.")
            field_id = field_row[0]

            # ✅ Update Page Layouts
            cursor.execute("SELECT id, sections FROM page_layouts WHERE object_name = %s", [object_name])
            page_layouts = cursor.fetchall()
            for layout_id, sections in page_layouts:
                sections_data = json.loads(sections)
                modified = False
                for section in sections_data:
                    if field_name in section.get("fields", []):
                        section["fields"].remove(field_name)
                        modified = True
                if modified:
                    cursor.execute(
                        "UPDATE page_layouts SET sections = %s WHERE id = %s",
                        [json.dumps(sections_data), layout_id]
                    )

            # ✅ Update Search Layouts
            cursor.execute("SELECT id, search_results_fields, lookup_dialog_fields, recent_items_fields FROM search_layouts WHERE object_id = %s", [object_id])
            row = cursor.fetchone()
           
            if row:
                layout_id, srf, ldf, rif = row
                srf_list = [f for f in json.loads(srf) if f != field_name]
                ldf_list = [f for f in json.loads(ldf) if f != field_name]
                rif_list = [f for f in json.loads(rif) if f != field_name]
                cursor.execute("""
                    UPDATE search_layouts 
                    SET search_results_fields = %s, lookup_dialog_fields = %s, recent_items_fields = %s 
                    WHERE id = %s
                """, [json.dumps(srf_list), json.dumps(ldf_list), json.dumps(rif_list), layout_id])

            # ✅ Update List Views
            cursor.execute("SELECT id, visible_columns FROM listviews WHERE object_id = %s", [object_id])
            listviews = cursor.fetchall()
            for listview_id, columns in listviews:
                if isinstance(columns, list):
                    col_list = [f for f in columns if f != field_name]
                    cursor.execute("UPDATE listviews SET visible_columns = %s WHERE id = %s", [col_list, listview_id])
                       
            # ✅ Delete Field Permissions
            cursor.execute("DELETE FROM field_permissions WHERE fields_id = %s", [field_id])
            
            # ✅ Delete Field Metadata
            cursor.execute("DELETE FROM fields WHERE id = %s", [field_id])

            query = sql.SQL("ALTER TABLE {table} DROP COLUMN IF EXISTS {column}")
            cursor.execute(
                query.format(
                    table=sql.Identifier(object_name),
                    column=sql.Identifier(field_name)
                )
            )
            
            log_audit(
                action=f"Deleted field {field_name} from object {object_name}",
                section=f"Field Deletion",
                **kwargs
            )

            return {"success": True, "message": f"Field '{field_name}' deleted successfully from object '{object_name}'."}

    except Exception as e:
        raise Exception(str(e))
