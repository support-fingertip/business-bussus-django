import uuid
import json
from django.db import connection, transaction
from concurrent.futures import ThreadPoolExecutor
from utils.prefix_generator import get_prefix
from utils.string_converters import validate_name
from django.utils import timezone

def debug_print(query, params):
    """Utility function to print SQL queries and parameters for debugging."""
    
def load_objects():
    with open('public/utils/objects/objects.json') as f:
        return json.load(f)
def load_fields(filename):
    with open(f"public/utils/objects/fields/{filename}.json") as f:
        return json.load(f)

def load_layouts():
    with open('public/utils/objects/layouts.json') as f:
        return json.load(f)
def load_selected_fields():
    with open('public/utils/objects/selected_fields.json') as f:
        return json.load(f)

def load_workflow_objects():
    with open('public/utils/objects/workflow.json') as f:
        return json.load(f)
    
def load_path_builder():
    with open('public/utils/objects/path_builder.json') as f:
        return json.load(f)


def resolve_field_id(cursor, object_id, path_config):
    """Resolve the field id for a path builder entry using object/field names instead of ids."""
    candidates = []
    if path_config.get('field_name'):
        candidates.append(path_config['field_name'])
    if path_config.get('name'):
        # Prefer normalized lowercase version; tolerate validation failures
        candidates.append(path_config['name'].lower().replace(' ', '_'))
        try:
            candidates.append(validate_name(path_config['name']))
        except Exception:
            pass

    for candidate in candidates:
        if not candidate:
            continue
        cursor.execute("SELECT id FROM fields WHERE object_id = %s AND name = %s LIMIT 1", [object_id, candidate])
        row = cursor.fetchone()
        if row:
            return row[0]

    return None


def create_path_builder(cursor, object_id, object_name, user_id):
    """Insert path builder configurations for the given object if present in seed data."""
    path_data = load_path_builder().get('path', [])
    for path_config in path_data:
        if path_config.get('object_name') != object_name:
            continue

        resolved_field_id = resolve_field_id(cursor, object_id, path_config)
        if not resolved_field_id:
            print(f"Skipping path builder '{path_config.get('name')}' - field not found for object {object_name}")
            continue

        path_id = path_config.get('id') or "pBl_" + uuid.uuid4().hex[:12]
        query = """
            INSERT INTO path_builder (
                id, name, label, object_id, field_id, stages, is_active,
                created_by_id, last_modified_by_id, owner_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """
        params = [
            path_id,
            path_config.get('name'),
            path_config.get('label'),
            object_id,
            resolved_field_id,
            json.dumps(path_config.get('stages', [])),
            path_config.get('is_active', True),
            user_id,
            user_id,
            user_id
        ]
        debug_print(query, params)
        cursor.execute(query, params)

def create_field(cursor, field, object_id, profile_ids, object_name):
    """Create a field in the database."""
    try:
        # Replace None with 'NULL' for specific fields in the query
        object_name = object_name if object_name is not None else None
        parent_object = field.get('parent_object') if field.get('parent_object') is not None else None
        relationship_name = field.get('relationship_name') if field.get('relationship_name') is not None else None
        datatype = field.get('datatype', 'text') if field.get('datatype') is not None else None
        length = field.get('length', 255) if field.get('length') is not None else None
        field_id = "fLd_" + uuid.uuid4().hex[:10]

        # Formula and rollup_summary fields cannot be required
        required = field.get("required", False)
        if datatype in ('formula', 'rollup_summary'):
            required = False

        # Query to insert the field, with NULL for missing values
        query = """
            INSERT INTO fields (id, name, label, parent_object, unique_field, required, object_id, object_name, datatype, length, relationship_name, is_modifiable, pickup_values, default_value, first_as_default,
                                formula_expression, formula_return_type,
                                summarized_object, rollup_type, field_to_aggregate, filter_criteria)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s) RETURNING id
        """
        params = [
            field_id,
            field.get('name'),
            field.get('label'),
            parent_object,
            field.get('unique'),
            required,
            object_id,
            object_name,
            datatype,
            length,
            relationship_name,
            field.get('is_modifiable', True),
            field.get('pickup_values', None),
            field.get('default_value', None),
            field.get('first_as_default', False),
            field.get('formula_expression', None),
            field.get('formula_return_type', None),
            field.get('summarized_object', None),
            field.get('rollup_type', None),
            field.get('field_to_aggregate', None),
            json.dumps(field.get('filter_criteria')) if field.get('filter_criteria') else None
        ]        
        # Debug print before executing the query
        debug_print(query, params)
        try:
            cursor.execute(query, params)
        except Exception as e:
            print(f"Error executing query for field {field.get('name')} and {object_name}: {str(e)}")

        # Insert field permissions
        for profile_id in profile_ids:
            query = """
                INSERT INTO field_permissions (fields_id, object_id, profile_id, read_access, edit_access, read_only, visible)
                VALUES (%s, %s, %s, TRUE, TRUE, TRUE, TRUE)
            """
            params = [field_id, object_id, profile_id]
            # Debug print for field permission insertion
            debug_print(query, params)
            cursor.execute(query, params)    
    except Exception as e:
        print(f"Error creating field {field.get('name')}: {str(e)}")


def create_object(USER_ID, object, schema):
    """Create an object in the database."""
    name = object.get('name')
    fields = load_fields(name)
    selected_fields = load_selected_fields()
    try:
        if not name:
            raise Exception("Object name is required.")        
        prefix = get_prefix(name)    

        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO %s", [schema])

            cursor.execute("SELECT id FROM profile")
            profile_ids = [row[0] for row in cursor.fetchall()]

            object_id = "obJ_" + uuid.uuid4().hex[:14]
            
            query = """
                INSERT INTO object (
                    id, name, label, description, show_tab, icon, icon_color, plural_label, record_name,
                    allow_activities, allow_bulk_api_access, allow_in_chatter_groups,
                    allow_reports, allow_sharing, allow_streaming_api_access,
                    datatype, deployment_status, enable_licensing, search_status,
                    starts_with_vowel_sound, track_field_history, prefix, type, 
                    created_by_id, last_modified_by_id, owner_id
                )
                VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, 'standard',
                    %s, %s, %s
                ) RETURNING id
            """
            params = [
                object_id,
                object['name'],
                object.get('label'),
                object.get('description'),
                object.get('show_tab'),
                object.get('icon'),
                object.get('icon_color'),
                object.get('plural_label'),
                object.get('record_name'),

                object.get('allow_activities', False),
                object.get('allow_bulk_api_access', False),
                object.get('allow_in_chatter_groups', False),
                object.get('allow_reports', False),
                object.get('allow_sharing', False),
                object.get('allow_streaming_api_access', False),

                object.get('datatype'),
                object.get('deployment_status'),
                object.get('enable_licensing', False),
                object.get('search_status', False),
                object.get('starts_with_vowel_sound', False),
                object.get('track_field_history', False),
                prefix,
                USER_ID,
                USER_ID,    
                USER_ID
            ]
            
            # Debug print before executing the query
            debug_print(query, params)
            
            cursor.execute(query, params)        

            # ListView (with empty visible_columns for now)
            query = """
                INSERT INTO listviews (id, object_id, name, label, visible_columns, is_pinned)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            params = [
                "lsTv" + uuid.uuid4().hex[:12],
                object_id,
                'all',
                'ALL',             # PostgreSQL array
                json.dumps(selected_fields.get(object["name"], ["name","created_by_id", "created_date", "owner_id"])),  # <-- Serialize to JSON string
                True           # Explicit value for is_pinned
            ]
            # Debug print before executing the query
            debug_print(query, params)
            cursor.execute(query, params)

            query = """
                INSERT INTO search_layouts (object_id, search_results_fields, lookup_dialog_fields, recent_items_fields)
                VALUES (%s, %s, %s, %s)
            """
            params = [
                object_id,
                json.dumps(["name"]),  # Default search result fields
                json.dumps(["name"]),  # Default lookup fields
                json.dumps(["name"])   # Default recent fields
            ]
            # Debug print before executing the query
            debug_print(query, params)
            cursor.execute(query, params)  

            # Use thread pool to handle field creation
            with ThreadPoolExecutor() as field_executor:
                futures = []
                for field in fields:
                    futures.append(field_executor.submit(create_field, cursor, field, object_id, profile_ids, name))

                for future in futures:
                    future.result()  # Wait for all threads to finish

            # Seed path builder configuration for this object (if available)
            create_path_builder(cursor, object_id, name, USER_ID)
            layouts = load_layouts()
            layout = layouts.get(name, {})
            # PageLayout (empty fields section initially)
            sections = json.dumps(layout.get('sections', [{"title": "Basic Information", "fields": ["name"]}, {"title": "System Details", "fields": ["created_by_id", "created_date", "last_modified_by_id", "last_modified_date", "owner_id"]}] ))
            related_lists_json = json.dumps(layout.get('related_lists', []))
            query = """
                INSERT INTO page_layouts (object_name, label, name, sections, object_id, created_by, last_modified_by, related_lists)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """
            params = [
                object["name"],
                f"{object['label']} Page Layout",
                'default_layout',
                sections,
                object_id,
                USER_ID,
                USER_ID,
                related_lists_json
            ]
            # Debug print before executing the query
            debug_print(query, params)
            cursor.execute(query, params)
            layout_id = cursor.fetchone()[0]
            
            # Assign layout to profiles
            with ThreadPoolExecutor() as layout_executor:
                layout_futures = []
                for profile_id in profile_ids:
                    layout_futures.append(layout_executor.submit(cursor.execute, """
                        INSERT INTO layout_assignment (profile_id, object_id, page_layouts_id, record_type, created_date, last_modified_date, created_by_id, last_modified_by_id)
                        VALUES (%s, %s, %s, %s, now(), now(), %s, %s)
                    """, [profile_id, object_id, layout_id, 'default', USER_ID, USER_ID]))

                for future in layout_futures:
                    future.result()

            # Object & Tab Permissions
            tab_type = "Default ON" if object.get("show_tab") else "Off"
            with ThreadPoolExecutor() as tab_executor:
                tab_futures = []
                for profile_id in profile_ids:
                    tab_futures.append(tab_executor.submit(cursor.execute, """
                        INSERT INTO object_permissions (object_id, profile_id, read, write, edit, delete, view_all, modify_all)
                        VALUES (%s, %s, TRUE, TRUE, TRUE, TRUE, TRUE, TRUE)
                    """, [object_id, profile_id]))

                    tab_futures.append(tab_executor.submit(cursor.execute, """
                        INSERT INTO tab_permissions (object_id, profile_id, type)
                        VALUES (%s, %s, %s)
                    """, [object_id, profile_id, tab_type])) 

                for future in tab_futures:
                    future.result()

            # Sharing settings
            query = """
                INSERT INTO sharing_records (object_id, access_level)
                VALUES (%s, 'Public Read Write')
            """
            params = [object_id]
            # Debug print before executing the query
            debug_print(query, params)
            cursor.execute(query, params)

        return {
            "success": True,
            "message": f"Custom object '{name}' created successfully."
        }

    except Exception as e:
        print(f"Error in create_object: {str(e)}")
        raise Exception(str(e))

def create_bulk_objects(USER_ID, schema):
    """Create all objects concurrently."""
    OBJECTS = load_objects()
    with ThreadPoolExecutor() as executor:
        futures = []
        for object in OBJECTS:
            futures.append(executor.submit(create_object, USER_ID, object, schema))

        for future in futures:
            future.result()  # Wait for all threads to finish
    # create_workflow_graph(USER_ID, schema)
    return 'all executed'

def create_workflow_graph(USER_ID, schema):
    """
    Insert workflow, workflow_node, and workflow_edge records into the specified schema
    using the seed data in public/utils/objects/workflow.json.
    """
    data = load_workflow_objects()
    workflows = data.get("workflow", [])
    nodes = data.get("workflow_node", [])
    edges = data.get("workflow_edge", [])
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("SET search_path TO %s, public;", [schema])

                # Insert workflows
                for wf in workflows:
                    cursor.execute(
                        """
                        INSERT INTO workflow (id, name, description, trigger_type, module_name,
                                              created_date, last_modified_date, created_by_id, last_modified_by_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        [
                            wf.get("id"),
                            wf.get("name"),
                            wf.get("description"),
                            wf.get("trigger_type"),
                            wf.get("module_name"),
                            wf.get("created_date", timezone.now()),
                            wf.get("last_modified_date", timezone.now()),
                            wf.get("created_by_id", USER_ID),
                            wf.get("last_modified_by_id", USER_ID),
                        ],
                    )
                for node in nodes:
                    cursor.execute(
                        """
                        INSERT INTO workflow_node (id, workflow_id, label, type, node_type, position, data, measured,
                                                   created_date, last_modified_date, created_by_id, last_modified_by_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        [
                            node.get("id"),
                            node.get("workflow_id"),
                            node.get("label"),
                            node.get("type"),
                            node.get("node_type"),
                            json.dumps(node.get("position", {})),
                            json.dumps(node.get("data", {})),
                            json.dumps(node.get("measured", {})),
                            node.get("created_date", timezone.now()),
                            node.get("last_modified_date", timezone.now()),
                            node.get("created_by_id", USER_ID),
                            node.get("last_modified_by_id", USER_ID),
                        ],
                    )

                # Insert edges
                for edge in edges:
                    cursor.execute(
                        """
                        INSERT INTO workflow_edge (id, workflow_id, source_id, target_id, source_handle,
                                                   created_date, last_modified_date, created_by_id, last_modified_by_id)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO NOTHING
                        """,
                        [
                            edge.get("id"),
                            edge.get("workflow_id"),
                            edge.get("source_id") or edge.get("source"),
                            edge.get("target_id") or edge.get("target"),
                            edge.get("source_handle") or edge.get("sourceHandle"),
                            edge.get("created_date", timezone.now()),
                            edge.get("last_modified_date", timezone.now()),
                            edge.get("created_by_id", USER_ID),
                            edge.get("last_modified_by_id", USER_ID),
                        ],
                    )
        return "workflow graph inserted"
    except Exception as e:
        print(f"Error inserting workflow graph: {e}")
        raise