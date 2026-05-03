
import copy
import random
import uuid
import json
from datetime import datetime
from django.db import connection, transaction
from django.apps import apps
from api.ORM.AuditLogs.audit_trail_logs import log_audit
from utils.columns_metadata_conversion import field_to_columns_metadata
from utils.prefix_generator import get_prefix
from utils.string_converters import validate_name
from .initial_fields import initial_fields
from api.ORM.setup.utils.create_dynamic_table import create_dynamic_table

def post_customobject(data, **kwargs):
    name = data.get("name")
    schema_name = kwargs.get("schema", "public")
    validate_name(name)
    datatype = data.get("datatype", "text")
    try:
        if not name:
            raise Exception("Object name is required.")
        prefix = get_prefix(name)

        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO %s", [kwargs.get('schema')])
            cursor.execute("SELECT COUNT(*) FROM object WHERE name = %s", [name])
            if cursor.fetchone()[0] > 0:
                raise Exception(f"Object '{name}' already exists.")

        fields = copy.deepcopy(initial_fields)
        if not fields:
            raise Exception("Fields data is missing.")
        

        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO %s", [kwargs.get('schema')])
                cursor.execute("SELECT id FROM profile")
                profile_ids = [row[0] for row in cursor.fetchall()]
                object_uid = uuid.uuid4().hex[:10]                
                cursor.execute("""
                    INSERT INTO object (
                        id, name, label, description, show_tab, icon, plural_label, record_name,
                        allow_activities, allow_bulk_api_access, allow_in_chatter_groups,
                        allow_reports, allow_sharing, allow_streaming_api_access,
                        datatype, deployment_status, enable_licensing, search_status,
                        starts_with_vowel_sound, track_field_history, prefix, type,starting_number,display_format,icon_color
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, 'custom',%s,%s,%s
                    )
                    RETURNING id
                """, [
                    object_uid,
                    data['name'],
                    data.get('label'),
                    data.get('description'),
                    data.get('show_tab'),
                    data.get('icon'),
                    data.get('plural_label'),
                    data.get('record_name'),

                    data.get('allow_activities', False),
                    data.get('allow_bulk_api_access', False),
                    data.get('allow_in_chatter_groups', False),
                    data.get('allow_reports', False),
                    data.get('allow_sharing', False),
                    data.get('allow_streaming_api_access', False),

                    data.get('datatype'),
                    data.get('deployment_status'),
                    data.get('enable_licensing', False),
                    data.get('search_status', False),
                    data.get('starts_with_vowel_sound', False),
                    data.get('track_field_history', False),
                    prefix, 
                    data.get('starting_number',1) or None,
                    data.get('display_format','ID'),
                    data.get('icon_color','#000000')
                ])
                row = cursor.fetchone()

                if not row:
                    raise Exception("Insert returned no ID")
                object_id = row[0]

                try:
                    cursor.execute(
                        """
                            UPDATE app SET tabs = COALESCE(tabs, '[]'::jsonb) || %s
                            where name = 'sales';
                        """,
                        [
                            json.dumps({
                                "name": name,
                                "type": "object"
                            })
                        ]
                    )
                except Exception as e:
                    print(e)
                    raise Exception(f"Error occured {e}")             

                # ✅ Now create the actual table
                create_dynamic_table(cursor, schema_name, name, prefix, datatype, data.get('display_format', 'ID'),starting_number=data.get('starting_number',1))              

                # ListView (with empty visible_columns for now)
                cursor.execute("""
                    INSERT INTO listviews (id, object_id, name, label, visible_columns, is_pinned)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, [
                    uuid.uuid4().hex[:10],
                    object_id,
                    'all',
                    'ALL',             # PostgreSQL array
                    json.dumps(["name","created_by_id"]),  # <-- Serialize to JSON string
                    True           # Explicit value for is_pinned
                ])
                
                cursor.execute("""
                    INSERT INTO search_layouts (object_id, search_results_fields, lookup_dialog_fields, recent_items_fields)
                    VALUES (%s, %s, %s, %s)
                """, [
                    object_id,
                    json.dumps(["name"]),  # Default search result fields
                    json.dumps(["name"]),  # Default lookup fields
                    json.dumps(["name"])   # Default recent fields
                ])                
                for field in fields:
                    if field.get('name') == 'name':
                        if datatype in ['number', 'auto_number']:
                            field['datatype'] = 'auto_number'
                            field['display_format'] = data.get('display_format', 'ID')
                            field['required'] = False
                        field['label'] = data.get('record_name', 'Name')
                    
                    try:
                        cursor.execute("""
                                    INSERT INTO fields (name, label, parent_object, unique_field, required, object_id, object_name, datatype, length, relationship_name, is_modifiable, display_format)
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id
                                    """, [field.get('name'), field.get('label'), field.get('parent_object'), field.get('unique'), field.get("required", False), object_id, name, field.get('datatype', 'text'), field.get('length', 255), field.get('relationship_name'), field.get('is_modifiable', True), field.get('display_format', None)])
                        field_id = cursor.fetchone()[0]
                        
                        for profile_id in profile_ids:
                            cursor.execute("""
                                INSERT INTO field_permissions (fields_id, object_id, profile_id, read_access, edit_access, read_only, visible)
                                VALUES (%s, %s, %s, TRUE, TRUE, TRUE, TRUE)
                            """, [field_id, object_id, profile_id])
                    except Exception as e:
                        print(str(e))

                # PageLayout (include all required fields in Basic Information)
                required_fields = [f.get('name') for f in fields if f.get('required')]
                if 'name' not in required_fields:
                    required_fields.insert(0, 'name')
                
                sections_data = [
                    {"title": "Basic Information", "fields": required_fields},
                    {"title": "System Details", "fields": ["created_by_id", "created_date", "last_modified_by_id", "last_modified_date", "owner_id"]}
                ]
                sections = json.dumps(sections_data)
                cursor.execute("""
                    INSERT INTO page_layouts (object_name, label, name, sections,created_by,last_modified_by)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, [
                    data["name"],
                    f"{data['label']} Page Layout",
                    'default_layout',
                    sections,
                    kwargs.get('user_',{}).get("id"),
                    kwargs.get('user_',{}).get("id")
                ])
                layout_id = cursor.fetchone()[0]
                
                for profile_id in profile_ids:
                    cursor.execute("""
                        INSERT INTO layout_assignment (profile_id, object_id, page_layouts_id, record_type, created_date, last_modified_date)
                        VALUES (%s, %s, %s, %s, now(), now())
                    """, [
                        profile_id,
                        object_id,
                        layout_id,
                        'default'
                    ])
                # Object & Tab Permissions
                tab_type = "Default ON" if data.get("show_tab") else "Off"
                for profile_id in profile_ids:
                    cursor.execute("""
                        INSERT INTO object_permissions (object_id, profile_id, read, write, edit, delete, view_all, modify_all)
                        VALUES (%s, %s, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE)
                    """, [object_id, profile_id])                   
                    
                    cursor.execute("""
                        INSERT INTO tab_permissions (object_id, profile_id, type)
                        VALUES (%s, %s, %s)
                    """, [object_id, profile_id, tab_type])

                #Sharing settings
                cursor.execute("""
                    INSERT INTO sharing_records (object_id, access_level)
                    VALUES (%s, 'Public Read Write')
                """, [object_id])
                
            log_audit(
                'Created custom object {name}',
                'Custom Object Creation',
                **kwargs
            )
        return {
            "success": True,
            "message": f"Custom object '{name}' created successfully.",
            "object_name":name
        }

    except Exception as e:
        print(e)
        raise Exception(str(e))
