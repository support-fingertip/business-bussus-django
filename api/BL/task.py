import re

from django.db import connection
from psycopg2 import sql

SAFE_SCHEMA_PATTERN = re.compile(r"^[A-Za-z0-9_]+$")


def _validate_schema(schema: str) -> str:
    """Ensure schema names are safe to interpolate as identifiers."""
    if not schema or not SAFE_SCHEMA_PATTERN.match(schema):
        raise ValueError("Invalid schema; only letters, numbers, and underscore are allowed")
    return schema

def run_query(query, params=None, fetch_one=False, commit=False, **kwargs):
    """Execute parameterized queries; supports psycopg2.sql composed objects."""
    params = params or []
    with connection.cursor() as cursor:
        cursor.execute(query, params)

        if commit:
            return {"status": "success"}

        if cursor.description:
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            if fetch_one:
                return dict(zip(columns, rows[0])) if rows else None
            return [dict(zip(columns, row)) for row in rows]
        return []



def get_related_tasks(**kwargs):
    """
    Fetch tasks using raw SQL based on task ID or related object ID.
    """
    object_id = kwargs.get('object_id')
    id = kwargs.get('id')

    base_query = """
        SELECT
            t.id,
            t.subject,
            t.description,
            t.status,
            t.due_date,
            t.created_date,
            t.last_modified_date,
            u.name AS assigned_to,
            t.assigned_to_id AS user_id,
            t.related_to_object_id AS related_to_id
        FROM task t
        LEFT JOIN users u ON t.assigned_to_id = u.id
    """
    params = []
    if id:
        base_query += " WHERE t.id = %s AND t.is_deleted = FALSE"
        params.append(id)
    elif object_id:
        base_query += " WHERE t.related_to_object_id = %s AND t.is_deleted = FALSE"
        params.append(object_id)
    else:
        return []
    schema = _validate_schema(kwargs.get('schema', 'public'))
    with connection.cursor() as cursor:
        cursor.execute(sql.SQL("SET search_path TO {schema}").format(schema=sql.Identifier(schema)))
        cursor.execute(base_query, params)
        rows = cursor.fetchall()

    # Define column names
    columns = [
        "id", "subject", "description", "status", "due_date",
        "created_date", "last_modified_date",
        "assigned_to", "assigned_to_id", "related_to_object_id"
    ]
    # Convert to list of dicts
    task_details = [dict(zip(columns, row)) for row in rows]
    # related_to name: Not resolvable via SQL, handled in Python if needed
    for task in task_details:
        task["related_to"] = None  # Placeholder since we can't determine the name from a dynamic model

    return task_details





def find_user_group_ids(user_id, schema: str):
    safe_schema = _validate_schema(schema)
    query = sql.SQL("SELECT user_group_id FROM {schema}.user_group_users WHERE user_id = %s").format(
        schema=sql.Identifier(safe_schema)
    )
    rows = run_query(query, [user_id])  # list of dicts
    return [r["user_group_id"] for r in rows] if rows else []


def group_has_ancestor(group_id: int, target_group_id: int, schema: str, visited=None) -> bool:
    if visited is None:
        visited = set()
    if group_id in visited:
        return False
    visited.add(group_id)
    if group_id == target_group_id:
        return True
    safe_schema = _validate_schema(schema)
    query = sql.SQL(
        """
        SELECT user_group_id
        FROM {schema}.user_group_public_groups
        WHERE public_group_id = %s
        """
    ).format(schema=sql.Identifier(safe_schema))
    parents = run_query(query, [group_id])
    if not parents:
        return False
    for row in parents:
        parent_id = row["user_group_id"]
        if group_has_ancestor(parent_id, target_group_id, schema, visited):
            return True
    return False


def user_belongs_to_group(user_id, group_id, schema, profile_id=None, _visited=None):
    """
    Check if a user belongs to a given user_group through any of:
      1. Direct membership (user_group_users)
      2. Profile membership (user_group_profiles)
      3. Nested public group membership (user_group_public_groups) — recursive
    Returns True if the user belongs, False otherwise.
    """
    if _visited is None:
        _visited = set()
    if group_id in _visited:
        return False
    _visited.add(group_id)

    safe_schema = _validate_schema(schema)

    # 1. Direct user membership
    direct_query = sql.SQL(
        "SELECT 1 FROM {schema}.user_group_users WHERE user_id = %s AND user_group_id = %s LIMIT 1"
    ).format(schema=sql.Identifier(safe_schema))
    if run_query(direct_query, [user_id, group_id], fetch_one=True):
        return True

    # 2. Profile membership
    if profile_id:
        profile_query = sql.SQL(
            "SELECT 1 FROM {schema}.user_group_profiles WHERE profile_id = %s AND user_group_id = %s LIMIT 1"
        ).format(schema=sql.Identifier(safe_schema))
        if run_query(profile_query, [profile_id, group_id], fetch_one=True):
            return True

    # 3. Nested group membership — check child groups linked under the target group
    child_groups_query = sql.SQL(
        "SELECT public_group_id FROM {schema}.user_group_public_groups WHERE user_group_id = %s"
    ).format(schema=sql.Identifier(safe_schema))
    child_groups = run_query(child_groups_query, [group_id])

    for child in child_groups or []:
        if user_belongs_to_group(user_id, child["public_group_id"], schema, profile_id, _visited):
            return True

    return False


def user_can_make_call(**kwargs):
    try:
        user_id = kwargs.get("user_", {}).get("id")
        profile = kwargs.get("profile_id")
        schema = _validate_schema(kwargs.get("schema", "public"))
        telephony_grp = kwargs.get("telephony_grp")

        if not user_id or not telephony_grp:
            return False
        telephone_exists = sql.SQL("SELECT id FROM {schema}.user_group WHERE id = %s").format(
            schema=sql.Identifier(schema)
        )
        exists = run_query(telephone_exists, [telephony_grp], fetch_one=True)
        if not exists:
            return False

        user_group_ids = find_user_group_ids(user_id, schema)
        if not user_group_ids:
            return False
        direct_sql = sql.SQL(
            """
            SELECT 1
            FROM {schema}.user_group_users
            WHERE user_id = %s AND user_group_id = %s
            LIMIT 1
            """
        ).format(schema=sql.Identifier(schema))
        direct = run_query(direct_sql, [user_id, telephony_grp], fetch_one=True)
        if direct:
            return True
        for gid in user_group_ids:
            if group_has_ancestor(gid, telephony_grp, schema):
                return True
    except Exception as er:
        print(er)
    return False






# def find_user_group(user_id,schema):
#     get_user = """SELECT * FROM {}.user_group_users WHERE user_id=%s""".format(schema)
#     user_grp = run_query(get_user,[user_id])
#     return user_grp




# def user_can_make_call(**kwargs):
#     user_id = kwargs.get("user_").get("id")
#     profile = kwargs.get("profile_id")
#     schema = kwargs.get("schema","pubic")
#     telephony_grp = kwargs.get("telephony_grp")


#     #Identify if group exists or not
#     telephone_exists = """SELECT id FROM {}.user_group WHERE id=%s""".format(schema)
#     exists = run_query(telephone_exists,[telephony_grp],fetch_one=True)
#     if not exists:
#         return False
    
#     #Identify the 
#     userGroup = find_user_group(user_id,schema)
#     if not userGroup:
#         return False

#     #Match with user and profile if exists return True or go to next 
#     user_query = """SELECT id,user_group_id FROM {}.user_group_users WHERE user_id=%s AND user_group_id=%s""".format(schema)
#     user_row = run_query(user_query,[user_id,exists['id']])
#     if user_row:
#         return True
    
#     #Recursively find the user group
#     def recursive_group(usergroup): 
#         print("User group----->",usergroup) 
#         for user in usergroup:     
#             get_user = """SELECT * FROM {}.user_group_public_groups WHERE public_group_id=%s""".format(schema)
#             data = run_query(get_user,[user.get('user_group_id','user_group_id')])
#             for grp in data:
#                 if grp['user_group_id'] == telephony_grp:
#                     return True
#             recursive_group(data)
    
#     return recursive_group(userGroup)




 # get_profile = f"""SELECT id,user_group_id FROM {schema}.user_group_profiles WHERE profile_id=%s"""
        # profile_grp = run_query(get_profile,[profile_id])

    # profile_query = f"""SELECT * FROM {schema}.user_group_profiles WHERE profile_id = %s AND user_group_id=%s"""
    # profile_row = run_query(profile_query,[profile,exists['id']],fetch_one=True)
    # if profile_row:
    #     return True