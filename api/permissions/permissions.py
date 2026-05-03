# from django.db import connection
# from api.ORM.AuditLogs.audit_trail_logs import log_audit
# from api.ORM.sqlFunctions.createSQLFunction import post_data_sql
# from api.ORM.sqlFunctions.updateSQLFunction import get_instance_by_id, updateRawSQL
# from api.ORM.sqlFunctions.deleteSQLFunction import delete_data_sql
# from api.ORM.setup.create_app import create_app
# from api.ORM.setup.newprofile import new_profile
# from api.permissions.FetchUsers.fetch_all_subordinates import get_all_subordinate_ids
# from api.permissions.FetchUsers.fetch_shared_records import fetch_shared_records
# from api.workflows.workflow_executor import execute_workflows
# from api.ORM.sqlFunctions.getQueryBuilder import build_query
# from utils.access_level_filter import add_private_owner_filter
# import logging

# logger = logging.getLogger(__name__)

# # ------------------------
# # Utility: Permission & Metadata
# # ------------------------

# def get_object_details(table_name, **kwargs):
#     cursor = connection.cursor()
#     cursor.execute("SET search_path TO %s", [kwargs.get('schema')])  # Ensure the search path is set to public schema
#     cursor.execute("SELECT id, label FROM object WHERE name = %s AND setup = FALSE", [table_name])
#     return cursor.fetchone()

# def profile_has_admin_access(profile_id, schema):
#     cursor = connection.cursor()
#     cursor.execute("SET search_path TO %s", [schema])
#     cursor.execute("SELECT COUNT(1) FROM profile WHERE id = %s AND profile_type IN ('admin', 'superadmin', 'manager', 'system', 'system_administrator', 'superadmin')", [profile_id])
#     count = cursor.fetchone()[0]
#     return count > 0

# def get_all_fields_for_table(table_name, **kwargs):
#     cursor = connection.cursor() # Ensure the search path is set to public schema
#     cursor.execute("""
#         SELECT column_name
#         FROM information_schema.columns
#         WHERE table_schema = %s AND table_name = %s
#         ORDER BY ordinal_position
#     """, [kwargs.get('schema'), table_name])
#     columns = cursor.fetchall()
#     return [col[0] for col in columns]

# def check_permission(object_id, permission_type, **kwargs):
#     cursor = connection.cursor()
#     cursor.execute("SET search_path TO %s", [kwargs.get('schema')])
#     cursor.execute(f"""
#         SELECT 1 FROM object_permissions 
#         WHERE object_id = %s AND profile_id = %s AND {permission_type} = TRUE
#     """, [object_id, kwargs.get('profile_id')])
#     return cursor.fetchone() is not None

# def get_field_metadata(object_id, access_type, **kwargs):
#     cursor = connection.cursor()
#     cursor.execute("SET search_path TO %s", [kwargs.get('schema')])
#     cursor.execute(f"""
#         SELECT f.name, f.label, f.datatype, f.required, f.parent_object, f.pickup_values, f.is_modifiable, f.relationship_name
#         FROM field_permissions fp
#         JOIN fields f ON fp.fields_id = f.id
#         WHERE fp.object_id = %s AND fp.profile_id = %s AND fp.{access_type}_access = TRUE
#     """, [object_id, kwargs.get('profile_id')])

#     permitted_fields = []
#     fields_metadata = []

#     for row in cursor.fetchall():
#         name, label, datatype, required, parent_object, pickup_values, is_modifiable, relationship_name = row
#         field_data = {"name": name, "label": label, "datatype": datatype, "required": required, "is_modifiable": is_modifiable, "relationship_name": relationship_name}

#         if datatype == 'lookup_relationship' and parent_object:
#             field_data["parent_object"] = parent_object
#             field_data["relationship_name"] = relationship_name
#         elif datatype in ['picklist', 'multi_picklist']:
#             field_data["values"] = pickup_values

#         permitted_fields.append(name)
#         fields_metadata.append(field_data)

#     return permitted_fields, fields_metadata

# def apply_audit_fields(data, mode='create', **kwargs):
#     user_id = kwargs.get('user_', {}).get('id')
#     if isinstance(data, list):
#         for entry in data:
#             if mode == 'create':
#                 entry['owner_id'] = entry['created_by_id'] = entry['last_modified_by_id'] = user_id
#             else:
#                 entry['last_modified_by_id'] = user_id
#     elif isinstance(data, dict):
#         if mode == 'create':
#             data.update({
#                 'owner_id': user_id,
#                 'created_by_id': user_id,
#                 'last_modified_by_id': user_id
#             })
#         else:
#             data.update({'last_modified_by_id': user_id})
#     return data

# # ------------------------
# # CRUD Handlers
# # ------------------------

# def get_permissions(request, **kwargs):
#     # browser = kwargs.get('browser', True)
#     browser = True
#     table_name = kwargs.get('tableName')
#     user_id = kwargs.get('user_', {}).get('id')
#     fields = kwargs.get('fields', None) 
#     if not fields:
#         fields = get_all_fields_for_table(table_name, **kwargs)
#         kwargs['fields'] = fields
#     cursor = connection.cursor()
#     object_row = get_object_details(table_name, **kwargs)    

#     if not object_row:
#         return {"data": build_query(**kwargs)}

#     object_id, object_label = object_row

#     if not check_permission(object_id, "read", **kwargs):
#         raise Exception(f'Access to {object_label} is denied for this user.')
    
#         # Step 2: Get access level from sharing_records
#     cursor.execute("SET search_path TO %s", [kwargs.get('schema')])  # Ensure the search path is set to public schema
#     cursor.execute("""
#         SELECT access_level 
#         FROM sharing_records 
#         WHERE object_id = %s
#     """, [object_id])
#     access_row = cursor.fetchone()

#     if access_row:
#         access_level = access_row[0]
#         if access_level == 'Private':
#             ids = get_all_subordinate_ids(user_id, kwargs.get('schema'))
#             shared_recs = fetch_shared_records(user_id, table_name, kwargs.get('schema'), type='read') # Debug print to check shared records
#             # Inject private filter (owner_id)
#             existing_filters = kwargs.get('where')
#             kwargs['where'] = add_private_owner_filter(existing_filters, ids, shared_recs)  

#     permitted_fields, fields_metadata = get_field_metadata(object_id, "read", **kwargs)
#     json_fields = []
#     dot_fields = []
#     new_permitted_fields = []
#     if fields:
#         for field in fields:
#             if field is None:
#                 continue
#             if isinstance(field, dict):
#                 json_fields.append(field)
#             elif '.' in field:
#                 dot_fields.append(field)
#             elif field=='id':
#                 new_permitted_fields.append('id')
#                 continue
#             else:
#                 field_name = field
#             for field_name in permitted_fields:
#                 if field_name == field:
#                     new_permitted_fields.append(field_name)

#     relationship_fields = []
#     if browser and not kwargs.get('report', False):
#         for field in fields:
#             if isinstance(field, dict):
#                 continue
#             else:
#                 field_name = field  # If it's a string, use it directly
#             if field_name not in new_permitted_fields:
#                 continue
#             for metadata in fields_metadata:
#                 if metadata['name'] == field and metadata['datatype'] == 'lookup_relationship':
#                     relationship_fields.append(f"{metadata['relationship_name']}.id")
#                     relationship_fields.append(f"{metadata['relationship_name']}.name")        
#     new_permitted_fields = new_permitted_fields + relationship_fields + json_fields + dot_fields  
#     kwargs.pop("fields", None)
#     return {
#         "data": build_query(fields=new_permitted_fields, **kwargs),
#         "all_columns": fields_metadata
#     }

# def post_permission(request, table_name, **kwargs):
#     user = kwargs.get('user_', {})
#     user_id = user.get('id')

#     object_row = get_object_details(table_name, **kwargs)

#     if not object_row:        
#         log_audit(f'Created record in {table_name}', 'Create', **kwargs)
#         if kwargs.get('setup_check', True):
#             if profile_has_admin_access(kwargs.get('profile_id'), kwargs.get('schema')):
#                 if table_name == 'app':
#                     return create_app(kwargs.get('create_data'), section='New app Created', **kwargs)
#                 elif table_name == 'profile':
#                     return new_profile(kwargs.get('new_profile'), kwargs.get('name'), **kwargs)
#                 return post_data_sql(table_name, kwargs.get('create_data'), section=f"Create - {table_name}", **kwargs)
#             else:
#                 raise Exception(f'Access Denied for the action. Please contact your administrator.')
#         else:
#             return post_data_sql(table_name, kwargs.get('create_data'), section=f"Create - {table_name}", **kwargs)
        

#     object_id, object_label = object_row

#     if not check_permission(object_id, "write", **kwargs):
#         raise Exception(f'Access to {object_label} is denied for this user.')

#     data = kwargs.get('create_data')
#     modified_data = apply_audit_fields(data, mode='create', **kwargs)
#     result = post_data_sql(table_name, modified_data, section=f"Create - {table_name}", **kwargs)
#     try:
#        data = execute_workflows(result.get('data')[0], table_name, "create_records", **kwargs)
#        if data and "authurl" in data:
#            result["authurl"] = data["authurl"]
#            result["verification"] = True
#     except Exception as e:
#         logger.error(f"Error executing workflows: {str(e)}")
#     return result

# def patch_permission(request, table_name, **kwargs):
#     cursor = connection.cursor()
#     user_id = kwargs.get('user_',{}).get('id')
#     object_row = get_object_details(table_name, **kwargs)
#     if not object_row:
#         log_audit(f'Updated record in {table_name}', 'Update', **kwargs)
#         if kwargs.get('setup_check', True):
#             if profile_has_admin_access(kwargs.get('profile_id'), kwargs.get('schema')):
#                 return updateRawSQL(table_name, **kwargs)
#             else:
#                 raise Exception(f'Access Denied for the action. Please contact your administrator.')
#         else:
#             return updateRawSQL(table_name, **kwargs)

#     object_id, object_label = object_row
#     if not check_permission(object_id, "edit", **kwargs):
#         raise Exception(f'Access to {object_label} is denied for this user.')
#     cursor.execute("SET search_path TO %s", [kwargs.get('schema')])  # Ensure the search path is set to public schema
#     # Step 3: Get sharing access level
#     cursor.execute("""
#         SELECT access_level 
#         FROM sharing_records 
#         WHERE object_id = %s
#     """, [object_id])
#     access_row = cursor.fetchone()
#     access_level = access_row[0] if access_row else None

#     # Step 4: If not Public Read Write, check if user is owner of the records
#     update_data = kwargs.get('update_data')
#     child_tables = []

#     if isinstance(update_data, dict):
#         child_tables = update_data.pop('child_tables', [])
#     elif isinstance(update_data, list):
#         for record in update_data:
#             if isinstance(record, dict) and 'child_tables' in record:
#                 child_tables.extend(record.pop('child_tables'))

#     records_to_check = update_data if isinstance(update_data, list) else [update_data]

#     if access_level not in ['Public Read Write']:
#         for record in records_to_check:
#             record_id = record.get("id")
#             ids = get_all_subordinate_ids(user_id, kwargs.get('schema'))
#             if not record_id:
#                 raise Exception("Each record must have an 'id' field for update.")

#             db_record = get_instance_by_id(table_name, record_id, kwargs.get('schema', 'public'))
#             if not db_record:
#                 raise Exception(f"Record not found.")

#             if db_record.get('owner_id') not in ids:
#                 raise Exception(f"Access denied.")

#     permitted_fields, fields_metadata = get_field_metadata(object_id, "edit", **kwargs)

#     updated_data = kwargs.pop('update_data', None)
#     modified_data = apply_audit_fields(updated_data, mode='update', **kwargs)

#     kwargs.pop("fields", None)

#     result = updateRawSQL(
#         object_name=table_name,
#         update_data=modified_data,
#         fields_metadata=fields_metadata,
#         section=f"Update - {table_name}",
#         **kwargs
#     )

#         # 🔄 Handle child tables update
#     for child in child_tables:
#         child_table = child.get('table')
#         child_records = child.get('records', [])

#         for record in child_records:
#             record = apply_audit_fields(record, mode='update', **kwargs)
#             updateRawSQL(
#                 object_name=child_table,
#                 update_data=record,
#                 section=f"Update - {child_table}",
#                 **kwargs
#             )
#     try:
#         for i in result.get('updated_records', []):    
#             execute_workflows(i.get('updated_data'), table_name, "update_records", **kwargs)
#     except Exception as e:
#         logger.error(f"Error executing workflows: {str(e)}")
#     return result


# def delete_permission(request, table_name, **kwargs):
#     object_row = get_object_details(table_name, **kwargs)
#     cursor = connection.cursor()
#     if not object_row:
#         log_audit(f'Deleted record in {table_name}', 'Deleted', **kwargs)
#         if kwargs.get('setup_check', True):
#             if profile_has_admin_access(kwargs.get('profile_id'), kwargs.get('schema')):
#                 return delete_data_sql(table_name, kwargs.get('ids'), **kwargs)
#             else:
#                 raise Exception(f'Access Denied for the action. Please contact your administrator.')
#         else:
#             return delete_data_sql(table_name, kwargs.get('ids'), **kwargs)

#     object_id, object_label = object_row

#     if not check_permission(object_id, "delete", **kwargs):
#         raise Exception(f"Access to {object_label} is denied for this user.")
#     cursor.execute("SET search_path TO %s", [kwargs.get('schema')])  # Ensure the search path is set to public schema
#     # Step 1: Get access level from sharing_records
#     cursor.execute("""
#         SELECT access_level 
#         FROM sharing_records 
#         WHERE object_id = %s
#     """, [object_id])
#     access_row = cursor.fetchone()

#     access_level = access_row[0] if access_row else None

#     # Step 2: If not Public Read Write, only owner can delete
#     if access_level != 'Public Read Write':
#         record_ids = kwargs.get('ids', [])
#         for record_id in record_ids:
#             record_data = get_instance_by_id(table_name, record_id, schema=kwargs.get('schema', 'public'))
#             if not record_data:
#                 raise Exception(f"Record with id={record_id} not found in {table_name}.")
#             if record_data.get('owner_id') != kwargs.get('user_', {}).get('id'):
#                 raise Exception(f"You do not have permission to delete record {record_id} in '{object_label}'. Only the owner can delete this record.")
#     try:
#         id = kwargs.get('ids')[0]
#         query = f"SELECT * FROM {table_name} WHERE id = %s"    
#         # Execute the query using parameterized input for the id
#         cursor.execute(query, [id])
#         result = cursor.fetchone()
#         if result:
#             # Convert the result into a key-value pair (dictionary)
#             column_names = [desc[0] for desc in cursor.description]  # Get column names
#             result_dict = dict(zip(column_names, result))
#             execute_workflows(result_dict, table_name, "delete_records", **kwargs)
#     except Exception as e:
#         logger.error(f"Error executing workflows: {str(e)}")
    
#     if isinstance(kwargs.get('ids'), list):
#         log_audit(
#             f'Mass Deleted records in {table_name}',
#             'Mass Delete',
#             **kwargs
#         )            
#     result = delete_data_sql(
#         table_name,
#         kwargs.get('ids'),
#         section=f"Delete - {table_name}",
#         **kwargs
#     )   
#     return result
























from django.db import connection, transaction
from api.ORM.AuditLogs.audit_trail_logs import log_audit
from api.ORM.sqlFunctions.createSQLFunction import post_data_sql
from api.ORM.sqlFunctions.updateSQLFunction import get_instance_by_id, updateRawSQL
from api.ORM.sqlFunctions.utils.helpers import validate_identifier
from api.ORM.sqlFunctions.deleteSQLFunction import delete_data_sql
from api.ORM.setup.create_app import create_app
from api.ORM.setup.newprofile import new_profile
from api.permissions.FetchUsers.fetch_all_subordinates import get_all_subordinate_ids
from api.permissions.FetchUsers.fetch_shared_records import fetch_shared_records
from api.workflows.workflow_executor import execute_workflows
from api.ORM.sqlFunctions.getQueryBuilder import build_query
from utils.access_level_filter import add_private_owner_filter
import logging
from psycopg2 import sql

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Authorization constants — single source of truth.
# ---------------------------------------------------------------------------
# Profile types granted blanket "admin" access in the legacy profile_type
# column. Prior to Phase 2 this list was inlined into the SQL, included a
# duplicate 'superadmin' entry, and was easy to miss when adding a new role.
ADMIN_ROLES: frozenset[str] = frozenset({
    "admin",
    "superadmin",
    "manager",
    "system",
    "system_administrator",
})

# Object-level permission columns we'll accept for `check_permission`. The
# value is interpolated into a SQL identifier (sql.Identifier) downstream;
# the whitelist guarantees we never reflect arbitrary user input into the
# table-column name.
VALID_PERMISSION_TYPES: frozenset[str] = frozenset({
    "read", "write", "edit", "delete",
})

# Sharing-records access levels. When no sharing_records row exists for an
# object we now default to PRIVATE — the audit-flagged "Public Read Write"
# fallback was a default-allow drift.
DEFAULT_OBJECT_ACCESS_LEVEL = "Private"

# Audit fields that must be set by the server, not the client. Any value
# the caller submits for these is silently overwritten by apply_audit_fields.
SERVER_SET_AUDIT_FIELDS_CREATE = ("owner_id", "created_by_id", "last_modified_by_id")
SERVER_SET_AUDIT_FIELDS_UPDATE = ("last_modified_by_id",)

# ------------------------
# Utility: Permission & Metadata
# ------------------------

def _perm_cache(request):
    """Per-request cache store. Lives on the request object so it survives
    for the duration of one HTTP request and is GC'd with it."""
    if request is None:
        return None
    cache = getattr(request, "_perm_cache", None)
    if cache is None:
        cache = {}
        try:
            request._perm_cache = cache
        except Exception:
            return None
    return cache


def get_object_details(table_name, **kwargs):
    schema = kwargs.get('schema')
    include_setup = kwargs.get('include_setup', False)
    request = kwargs.get('request')
    cache = _perm_cache(request)
    cache_key = ("object_details", schema, table_name, bool(include_setup))
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    cursor = connection.cursor()
    cursor.execute("SET search_path TO %s", [schema])  # Ensure the search path is set to public schema
    if include_setup:
        # Include all objects (setup=TRUE and setup=FALSE) — used by data export
        cursor.execute("SELECT id, label, setup FROM object WHERE name = %s", [table_name])
    else:
        # Original behaviour: exclude setup objects
        cursor.execute("SELECT id, label FROM object WHERE name = %s AND setup = FALSE", [table_name])
    result = cursor.fetchone()
    if cache is not None:
        cache[cache_key] = result
    return result

def profile_has_admin_access(profile_id, schema):
    """Return True iff ``profile_id`` is one of the privileged roles.

    Roles come from the ``ADMIN_ROLES`` constant — see that constant for
    the single source of truth. Adding a new admin tier should require
    editing exactly one place.
    """
    cursor = connection.cursor()
    cursor.execute("SET search_path TO %s", [schema])
    # Bind the role list as a parameter (psycopg2 expects a tuple for IN).
    # The previous version inlined the literal list into the SQL string,
    # which meant role names were hard-coded in two places (the SQL and
    # the docstring) and 'superadmin' was duplicated by accident.
    cursor.execute(
        "SELECT 1 FROM profile WHERE id = %s AND profile_type = ANY(%s) LIMIT 1",
        [profile_id, list(ADMIN_ROLES)],
    )
    return cursor.fetchone() is not None

def get_all_fields_for_table(table_name, **kwargs):
    cursor = connection.cursor() # Ensure the search path is set to public schema
    cursor.execute("""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
    """, [kwargs.get('schema'), table_name])
    columns = cursor.fetchall()
    return [col[0] for col in columns]

def check_permission(object_id, permission_type, **kwargs):
    """Return True iff ``profile_id`` has ``permission_type`` on ``object_id``.

    ``permission_type`` is whitelisted against ``VALID_PERMISSION_TYPES``
    before being used as a SQL identifier — this is defence-in-depth on
    top of ``sql.Identifier``: a typo or unexpected caller input fails
    with a clear ValueError instead of selecting an unrelated column.
    """
    if permission_type not in VALID_PERMISSION_TYPES:
        raise ValueError(
            f"Invalid permission_type {permission_type!r}; "
            f"expected one of {sorted(VALID_PERMISSION_TYPES)}"
        )
    schema = kwargs.get('schema')
    profile_id = kwargs.get('profile_id')
    request = kwargs.get('request')
    cache = _perm_cache(request)
    cache_key = ("check_permission", schema, object_id, profile_id, permission_type)
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    cursor = connection.cursor()
    cursor.execute("SET search_path TO %s", [schema])
    query = sql.SQL("""
        SELECT 1 FROM object_permissions
        WHERE object_id = %s AND profile_id = %s AND {} = TRUE
    """).format(sql.Identifier(permission_type))
    cursor.execute(query, [object_id, profile_id])
    result = cursor.fetchone() is not None
    if cache is not None:
        cache[cache_key] = result
    return result

def get_field_metadata(object_id, access_type, **kwargs):
    """Return permitted_fields + per-field metadata for the caller's profile.

    ``access_type`` is whitelisted against ``VALID_PERMISSION_TYPES`` so
    the column suffix interpolated into the SQL identifier
    (``<access_type>_access``) can never come from an attacker-controlled
    string.
    """
    schema = kwargs.get('schema')
    profile_id = kwargs.get('profile_id')
    request = kwargs.get('request')
    cache = _perm_cache(request)
    cache_key = ("field_metadata", schema, object_id, profile_id, access_type)
    if cache is not None and cache_key in cache:
        return cache[cache_key]
    if access_type not in VALID_PERMISSION_TYPES:
        raise ValueError(
            f"Invalid access_type {access_type!r}; "
            f"expected one of {sorted(VALID_PERMISSION_TYPES)}"
        )
    try:
        cursor = connection.cursor()

        cursor.execute("SET search_path TO %s", [schema])
        access_col = sql.Identifier(f"{access_type}_access")
        query = sql.SQL("""
            SELECT f.name, f.label, f.datatype, f.required, f.parent_object,
                    f.pickup_values, f.is_modifiable,
                    f.relationship_name, f.sort_alpha,
                    f.first_as_default, f.limit_predefined_values,
                    f.default_value_in_checkbox,
                    f.default_value,
                    f.send_mail,
                    f.no_skip,
                    f.no_rollback,
                    f.number_length,
                    f.formula_expression,
                    f.formula_return_type,
                    f.summarized_object,
                    f.rollup_type,
                    f.field_to_aggregate,
                    f.filter_criteria
            FROM field_permissions fp
            JOIN fields f ON fp.fields_id = f.id
            WHERE fp.object_id = %s AND fp.profile_id = %s AND fp.{} = TRUE
        """).format(access_col)
        cursor.execute(query, [object_id, kwargs.get('profile_id')])
        permitted_fields = []
        fields_metadata = []
        for row in cursor.fetchall():
            name, label, datatype, required, parent_object, pickup_values, is_modifiable, relationship_name, sort_alpha, first_as_default, limit_predefined_values, default_value_in_checkbox, default_value, send_mail, no_skip, no_rollback, number_length, formula_expression, formula_return_type, summarized_object, rollup_type, field_to_aggregate, filter_criteria = row
            field_data = {"name": name, "label": label, "datatype": datatype, "required": required, "is_modifiable": is_modifiable, "relationship_name": relationship_name}
            if datatype == 'lookup_relationship' and parent_object:
                field_data["parent_object"] = parent_object
                field_data["relationship_name"] = relationship_name
            elif datatype in ['picklist', 'picklist_multi']:
                field_data["values"] = pickup_values
                field_data["sort_alpha"] = sort_alpha
                field_data["first_as_default"] = first_as_default
                field_data["limit_predefined_values"] = limit_predefined_values
                field_data["no_skip"] = no_skip
                field_data["no_rollback"] = no_rollback
                if default_value not in (None, ""):
                    field_data["default"] = default_value
                else:
                    field_data["default"] = pickup_values[0] if first_as_default and pickup_values else None
            elif datatype == 'email':
                field_data["send_mail"] = send_mail  # Assuming send_mail is the last column in the SELECT statement
            elif datatype == 'checkbox':
                field_data["default"] = True if default_value_in_checkbox == 'checked' else False
            elif datatype == 'formula':
                field_data["formula_expression"] = formula_expression
                field_data["formula_return_type"] = formula_return_type
            elif datatype == 'rollup_summary':
                field_data["summarized_object"] = summarized_object
                field_data["rollup_type"] = rollup_type
                field_data["field_to_aggregate"] = field_to_aggregate
                field_data["filter_criteria"] = filter_criteria
            else:
                if number_length is not None:
                    field_data["number_length"] = number_length
                field_data["default"] = default_value if default_value else None
            # Formula and roll-up summary fields have no physical column — skip from SELECT
            if datatype not in ('formula', 'rollup_summary'):
                permitted_fields.append(name)
            fields_metadata.append(field_data)

        if cache is not None:
            cache[cache_key] = (permitted_fields, fields_metadata)
        return permitted_fields, fields_metadata
    except Exception as e:
        logger.error(f"Error fetching field metadata: {str(e)}")
        raise Exception(f"Error fetching field metadata: {str(e)}")


def _lock_record_for_update(table_name, record_id, schema):
    """Read a record with ``SELECT ... FOR UPDATE``, returning a dict.

    Locking the row inside the same transaction as the subsequent UPDATE
    closes the TOCTOU window where another writer could change ``owner_id``
    between our authorization check and our write.

    Caller MUST already be inside a ``transaction.atomic()`` block —
    otherwise ``FOR UPDATE`` has no effect because the lock is released
    immediately on autocommit.
    """
    validate_identifier(schema, "schema")
    validate_identifier(table_name, "table_name")
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL search_path TO %s", [schema])
        cursor.execute(
            sql.SQL("SELECT * FROM {} WHERE id = %s FOR UPDATE").format(
                sql.Identifier(table_name)
            ),
            [record_id],
        )
        row = cursor.fetchone()
        if not row:
            return None
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))


def apply_audit_fields(data, mode='create', **kwargs):
    """Stamp owner / created_by / last_modified_by from the authenticated user.

    These are server-set audit fields. The previous version used
    ``setdefault`` which honored caller-supplied values — meaning an
    attacker could POST a record with ``owner_id`` set to another user's
    id and silently take ownership. We now FORCE-OVERWRITE: any value the
    client tries to set for one of these fields is dropped and replaced
    with the authenticated user's id.

    Internal callers that legitimately need to reassign ownership (e.g.
    bulk owner-transfer admin endpoints) must build their own SQL paths
    that go through a dedicated permission check; they should not route
    through ``apply_audit_fields``.
    """
    user_id = kwargs.get('user_', {}).get('id')
    fields = (
        SERVER_SET_AUDIT_FIELDS_CREATE if mode == 'create'
        else SERVER_SET_AUDIT_FIELDS_UPDATE
    )

    def _stamp(entry):
        # If the client supplied any of these, drop a structured log line
        # so we can audit who tried.
        clobbered = [f for f in fields if f in entry and entry.get(f) != user_id]
        if clobbered:
            logger.warning(
                "apply_audit_fields: dropping client-supplied audit fields",
                extra={"clobbered": clobbered, "user_id": user_id, "mode": mode},
            )
        for f in fields:
            entry[f] = user_id

    if isinstance(data, list):
        for entry in data:
            _stamp(entry)
    elif isinstance(data, dict):
        _stamp(data)
    return data

# ------------------------
# CRUD Handlers
# ------------------------

def get_permissions(request, **kwargs):
    # Thread the request object into kwargs so nested helpers can reach the
    # per-request cache. Callers often pass `**kwargs` through to sub-calls;
    # the explicit `request=` keeps the cache key stable across them.
    kwargs.setdefault('request', request)
    try:
        # browser = kwargs.get('browser', True)
        browser = True
        table_name = kwargs.get('tableName')
        user_id = kwargs.get('user_', {}).get('id')
        schema = kwargs.get('schema')
        if not schema:
            raise Exception("schema is required for get_permissions")
        fields = kwargs.get('fields', None)
        if not fields:
            fields = get_all_fields_for_table(table_name, **kwargs)
            kwargs['fields'] = fields
        cursor = connection.cursor()
        object_row = get_object_details(table_name, **kwargs)

        if not object_row:
            kwargs.pop("request", None)
            return {"data": build_query(**kwargs)}

        object_id, object_label = object_row

        has_object_permission = check_permission(object_id, "read", **kwargs)

        # Step 2: Get access level from sharing_records
        cursor.execute("SET search_path TO %s", [schema])
        cursor.execute("""
            SELECT access_level
            FROM sharing_records
            WHERE object_id = %s
        """, [object_id])
        access_row = cursor.fetchone()
        # Default-deny: missing sharing_records row means PRIVATE, not Public RW.
        # Phase 2 changes this from the previous default-allow drift; tenants
        # that want world-readable objects must add an explicit row.
        access_level = access_row[0] if access_row else DEFAULT_OBJECT_ACCESS_LEVEL

        # Check if user has any shared records for this object
        shared_recs = fetch_shared_records(user_id, table_name, kwargs.get('schema'), type='read')

        if not has_object_permission and not shared_recs:
            raise Exception(f'Access to {object_label.lower()} is denied for this user.')

        if access_level == 'Private' or not has_object_permission:
            # Private → only owner, subordinates, and shared records
            # No object permission but has shared records → restrict to shared records only
            ids = get_all_subordinate_ids(user_id, kwargs.get('schema')) if has_object_permission else []
            existing_filters = kwargs.get('where')
            # For events, also expose records where the current user is the assignee (users_id),
            # so events created by others (e.g. admin) and assigned to this user are visible.
            assigned_to_field = 'users_id' if table_name == 'event' else None
            kwargs['where'] = add_private_owner_filter(existing_filters, ids, shared_recs, assigned_to_field=assigned_to_field, assigned_to_id=user_id)
        # Public Read Only  → no read filter (everyone can read)
        # Public Read Write → no read filter (everyone can read)
        permitted_fields, fields_metadata = get_field_metadata(object_id, "read", **kwargs)
        json_fields = []
        dot_fields = []
        new_permitted_fields = []
        if fields:
            for field in fields:
                if field is None:
                    continue
                if isinstance(field, dict):
                    json_fields.append(field)
                elif '.' in field:
                    dot_fields.append(field)
                elif field=='id':
                    new_permitted_fields.append('id')
                    continue
                else:
                    field_name = field
                for field_name in permitted_fields:
                    if field_name == field:
                        new_permitted_fields.append(field_name)

        relationship_fields = []
        if browser and not kwargs.get('report', False):
            for field in fields:
                if isinstance(field, dict):
                    continue
                else:
                    field_name = field  # If it's a string, use it directly
                if field_name not in new_permitted_fields:
                    continue
                for metadata in fields_metadata:
                    if metadata['name'] == field and metadata['datatype'] == 'lookup_relationship':
                        relationship_fields.append(f"{metadata['relationship_name']}.id")
                        relationship_fields.append(f"{metadata['relationship_name']}.name")        
        # Exclude formula/rollup_summary fields — no physical column
        computed_field_names = {
            m['name'] for m in fields_metadata
            if m.get('datatype') in ('formula', 'rollup_summary')
        }
        new_permitted_fields = [f for f in new_permitted_fields if f not in computed_field_names]
        json_fields = [f for f in json_fields if f.get('name') not in computed_field_names]
        dot_fields = [f for f in dot_fields if f.split('.')[0] not in computed_field_names]
        new_permitted_fields = new_permitted_fields + relationship_fields + json_fields + dot_fields
        kwargs.pop("fields", None)
        # Keep the heavy Django request object out of the deepcopy inside
        # build_query — it's only needed for permission meta caching which
        # already happened above.
        kwargs.pop("request", None)
        return {
            "data": build_query(fields=new_permitted_fields, **kwargs),
            "all_columns": fields_metadata
        }
    except Exception as e:
        print(f"Error in get_permissions: {str(e)}")
        raise Exception(f"Error in get_permissions: {str(e)}")

def post_permission(request, table_name, **kwargs):
    user = kwargs.get('user_', {})
    user_id = user.get('id')

    object_row = get_object_details(table_name, **kwargs)

    if not object_row:        
        log_audit(f'Created record in {table_name}', 'Create', **kwargs)
        if kwargs.get('setup_check', True):
            if profile_has_admin_access(kwargs.get('profile_id'), kwargs.get('schema')):
                if table_name == 'app':
                    return create_app(kwargs.get('create_data'), section='New app Created', **kwargs)
                elif table_name == 'profile':
                    return new_profile(kwargs.get('new_profile'), kwargs.get('name'), **kwargs)
                return post_data_sql(table_name, kwargs.get('create_data'), section=f"Create - {table_name}", **kwargs)
            else:
                raise Exception(f'Access Denied for the action. Please contact your administrator.')
        else:
            return post_data_sql(table_name, kwargs.get('create_data'), section=f"Create - {table_name}", **kwargs)
        

    object_id, object_label = object_row

    if not check_permission(object_id, "write", **kwargs):
        raise Exception(f'Access to {object_label} is denied for this user.')

    data = kwargs.get('create_data')
    modified_data = apply_audit_fields(data, mode='create', **kwargs)
    result = post_data_sql(table_name, modified_data, section=f"Create - {table_name}", enable_lookup_validation=True, **kwargs)
    created_rows = result.get('data') or []
    if created_rows:
        try:
            data = execute_workflows(created_rows[0], table_name, "create_records", **kwargs)
            if data and "authurl" in data:
                result["authurl"] = data["authurl"]
                result["verification"] = True
        except Exception as e:
            logger.error(f"Error executing workflows: {str(e)}")
    return result

def patch_permission(request, table_name, **kwargs):
    cursor = connection.cursor()
    user_id = kwargs.get('user_',{}).get('id')
    schema = kwargs.get('schema', 'public')
    object_row = get_object_details(table_name, **kwargs)
    if not object_row:
        log_audit(f'Updated record in {table_name}', 'Update', **kwargs)
        if kwargs.get('setup_check', True):
            if profile_has_admin_access(kwargs.get('profile_id'), kwargs.get('schema')):
                return updateRawSQL(table_name, **kwargs)
            else:
                raise Exception(f'Access Denied for the action. Please contact your administrator.')
        else:
            return updateRawSQL(table_name, **kwargs)

    object_id, object_label = object_row
    has_object_permission = check_permission(object_id, "edit", **kwargs)

    cursor.execute("SET search_path TO %s", [schema])
    # Step 3: Get sharing access level
    cursor.execute("""
        SELECT access_level
        FROM sharing_records
        WHERE object_id = %s
    """, [object_id])
    access_row = cursor.fetchone()
    # Default-deny: see DEFAULT_OBJECT_ACCESS_LEVEL.
    access_level = access_row[0] if access_row else DEFAULT_OBJECT_ACCESS_LEVEL

    shared_recs = fetch_shared_records(user_id, table_name, kwargs.get('schema'), type='write')

    if not has_object_permission and not shared_recs:
        raise Exception(f'Access to {object_label} is denied for this user.')

    # Step 4: If not Public Read Write, check if user is owner of the records
    update_data = kwargs.get('update_data')
    child_tables = []

    if isinstance(update_data, dict):
        child_tables = update_data.pop('child_tables', [])
    elif isinstance(update_data, list):
        for record in update_data:
            if isinstance(record, dict) and 'child_tables' in record:
                child_tables.extend(record.pop('child_tables'))

    records_to_check = update_data if isinstance(update_data, list) else [update_data]

    resolved_table = table_name.lower()
    if table_name == 'user':
        resolved_table = 'users'
    validate_identifier(resolved_table)

    def resolve_id_from_name(record):
        record_id = record.get("id")
        if record_id:
            return record_id

        name_value = record.get("name")
        if not name_value:
            return None

        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s AND column_name = 'name'
            """,
            [schema, resolved_table]
        )
        if not cursor.fetchone():
            return None

        cursor.execute(
            sql.SQL("SELECT id FROM {} WHERE name = %s").format(sql.Identifier(resolved_table)),
            [name_value]
        )
        rows = cursor.fetchall()
        if not rows:
            return None
        if len(rows) > 1:
            return "__multiple__"

        record["id"] = rows[0][0]
        return record["id"]

    # Build sets for per-record access checks
    ids = get_all_subordinate_ids(user_id, kwargs.get('schema')) if has_object_permission else []
    write_shared_ids = {str(r.get('record_id')) for r in shared_recs if r.get('record_id')}

    # Detect records explicitly shared as read-only (shared with READ but not WRITE)
    all_shared_recs = fetch_shared_records(user_id, table_name, kwargs.get('schema'), type='read')
    all_shared_ids = {str(r.get('record_id')) for r in all_shared_recs if r.get('record_id')}
    read_only_shared_ids = all_shared_ids - write_shared_ids

    # TOCTOU FIX: lock every target row for update inside a single
    # transaction so the ownership we check is the ownership we write
    # against. The lock is released when the outer transaction commits,
    # i.e. after updateRawSQL has finished applying changes below.
    with transaction.atomic():
        for record in records_to_check:
            record_id = resolve_id_from_name(record)
            if record_id == "__multiple__":
                raise Exception("Unable to resolve record by 'name' for update.")
            if not record_id:
                if record.get("name"):
                    continue
                raise Exception("Each record must have an 'id' or 'name' field for update.")

            db_record = _lock_record_for_update(
                table_name, record_id, kwargs.get('schema', 'public')
            )
            if not db_record:
                raise Exception(f"Record not found.")

            is_owner_or_superior = db_record.get('owner_id') in ids

            # Records explicitly shared as read-only → deny update regardless of OWD
            if str(record_id) in read_only_shared_ids and not is_owner_or_superior:
                raise Exception("Access denied. Record is shared as read-only.")

            # Private / Public Read Only / no object permission → must be
            # owner, subordinate, or write-shared.
            if access_level in ['Private', 'Public Read Only'] or not has_object_permission:
                if not is_owner_or_superior and str(record_id) not in write_shared_ids:
                    raise Exception(f"Access denied.")

        permitted_fields, fields_metadata = get_field_metadata(object_id, "edit", **kwargs)

        updated_data = kwargs.pop('update_data', None)
        modified_data = apply_audit_fields(updated_data, mode='update', **kwargs)

        kwargs.pop("fields", None)

        result = updateRawSQL(
            object_name=table_name,
            update_data=modified_data,
            fields_metadata=fields_metadata,
            section=f"Update - {table_name}",
            # Object-level update: enable lookup validation (name → id resolution)
            enable_lookup_validation=True,
            **kwargs
        )

            # 🔄 Handle child tables update
        for child in child_tables:
            child_table = child.get('table')
            child_records = child.get('records', [])

            for record in child_records:
                record = apply_audit_fields(record, mode='update', **kwargs)
                updateRawSQL(
                    object_name=child_table,
                    update_data=record,
                    section=f"Update - {child_table}",
                    enable_lookup_validation=True,
                    **kwargs
                )
    try:
        if result.get('updated_records'):
            for i in result.get('updated_records', []):  
                kwargs['app_id'] = i.get('updated_data', {}).get('app_id')  
                data = execute_workflows(i.get('updated_data'), table_name, "update_records", **kwargs)
                if data and "authurl" in data:
                    result["authurl"] = data["authurl"]
                    result["verification"] = True
        else:
            for i in result.get('updated', []):
                kwargs['app_id'] = i.get('updated_data', {}).get('app_id')  
                data = execute_workflows(i.get('updated_data'), table_name, "update_records", **kwargs)
                if data and "authurl" in data:
                    result["authurl"] = data["authurl"]
                    result["verification"] = True
    except Exception as e:
        logger.error(f"Error executing workflows: {str(e)}")
    return result


def delete_permission(request, table_name, **kwargs):
    object_row = get_object_details(table_name, **kwargs)
    cursor = connection.cursor()
    if not object_row:
        log_audit(f'Deleted record in {table_name}', 'Deleted', **kwargs)
        if kwargs.get('setup_check', True):
            if profile_has_admin_access(kwargs.get('profile_id'), kwargs.get('schema')):
                return delete_data_sql(table_name, kwargs.get('ids'), **kwargs)
            else:
                raise Exception(f'Access Denied for the action. Please contact your administrator.')
        else:
            return delete_data_sql(table_name, kwargs.get('ids'), **kwargs)

    object_id, object_label = object_row
    has_object_permission = check_permission(object_id, "delete", **kwargs)

    cursor.execute("SET search_path TO %s", [kwargs.get('schema')])
    # Step 1: Get access level from sharing_records
    cursor.execute("""
        SELECT access_level
        FROM sharing_records
        WHERE object_id = %s
    """, [object_id])
    access_row = cursor.fetchone()
    # Default-deny: see DEFAULT_OBJECT_ACCESS_LEVEL.
    access_level = access_row[0] if access_row else DEFAULT_OBJECT_ACCESS_LEVEL

    user_id = kwargs.get('user_', {}).get('id')
    shared_recs = fetch_shared_records(user_id, table_name, kwargs.get('schema'), type='delete')

    if not has_object_permission and not shared_recs:
        raise Exception(f"Access to {object_label} is denied for this user.")

    # Build sets for per-record access checks
    ids = get_all_subordinate_ids(user_id, kwargs.get('schema')) if has_object_permission else []
    delete_shared_ids = {str(r.get('record_id')) for r in shared_recs if r.get('record_id')}

    # Detect records explicitly shared without delete access
    all_shared_recs = fetch_shared_records(user_id, table_name, kwargs.get('schema'), type='read')
    all_shared_ids = {str(r.get('record_id')) for r in all_shared_recs if r.get('record_id')}
    no_delete_shared_ids = all_shared_ids - delete_shared_ids

    record_ids = kwargs.get('ids', [])
    data = {}
    # TOCTOU FIX: lock every target row, run authz, run delete inside ONE
    # transaction. Releases on commit (after delete_data_sql below).
    with transaction.atomic():
        for record_id in record_ids:
            record_data = _lock_record_for_update(
                table_name, record_id, kwargs.get('schema', 'public')
            )
            if not record_data:
                raise Exception(f"Record with id={record_id} not found in {table_name}.")

            is_owner_or_superior = record_data.get('owner_id') in ids

            # Records explicitly shared without delete access → deny regardless of OWD
            if str(record_id) in no_delete_shared_ids and not is_owner_or_superior:
                raise Exception(
                    f"You do not have permission to delete record {record_id} in '{object_label}'."
                )

            # Private / Public Read Only / no object permission → must be
            # owner, subordinate, or delete-shared.
            if access_level in ['Private', 'Public Read Only'] or not has_object_permission:
                if not is_owner_or_superior and str(record_id) not in delete_shared_ids:
                    raise Exception(
                        f"You do not have permission to delete record {record_id} in '{object_label}'."
                    )

        try:
            id = kwargs.get('ids')[0]
            query = sql.SQL("SELECT * FROM {} WHERE id = %s").format(sql.Identifier(table_name))
            cursor.execute(query, [id])
            result = cursor.fetchone()
            if result:
                column_names = [desc[0] for desc in cursor.description]
                result_dict = dict(zip(column_names, result))
                data = execute_workflows(result_dict, table_name, "delete_records", **kwargs)
        except Exception as e:
            logger.error(f"Error executing workflows: {str(e)}")

        if isinstance(kwargs.get('ids'), list):
            log_audit(
                f'Mass Deleted records in {table_name}',
                'Mass Delete',
                **kwargs
            )
        result = delete_data_sql(
            table_name,
            kwargs.get('ids'),
            section=f"Delete - {table_name}",
            **kwargs
        )
    if data and "authurl" in data:
        result["authurl"] = data["authurl"]
        result["verification"] = True
        return result
    return result


