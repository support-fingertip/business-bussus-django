from django.db import connection, transaction



from datetime import datetime
from psycopg2 import sql
from pprint import pprint

def sync_child_tables(
    cursor,
    parent_table: str,
    parent_id,
    child_tables: list,
    child_link_key_map: dict,   # {"user_group_public_groups": "public_group_id", ...}
    user=None,
    schema="public",
    org=None
):
    """
    Sync join/child tables:
    - Insert records present in payload but missing in DB
    - Delete records present in DB but missing in payload
    - Set audit fields if the table has them

    Works best for join tables like:
      user_group_users(user_group_id, user_id)
      user_group_profiles(user_group_id, profile_id)
      user_group_public_groups(user_group_id, public_group_id)
    """
    parent_fk = f"{parent_table}_id"  # user_group_id, etc.
    now = datetime.utcnow()
    user_id = None

    # user can be dict or Django user object depending on your code
    if isinstance(user, dict):
        user_id = user.get("id")
    elif user is not None and hasattr(user, "id"):
        user_id = user.id

    for child_info in (child_tables or []):
        child_table = child_info.get("table")
        incoming_records = child_info.get("records", [])

        if not child_table:
            continue

        link_key = child_link_key_map.get(child_table)
        if not link_key:
            raise Exception(f"Missing link key mapping for child table: {child_table}")

        # Normalize payload to a set of link ids
        # supports: records=[ "id1","id2" ] OR records=[{"user_id":"id1"}, ...]
        incoming_ids = set()
        for r in incoming_records or []:
            if isinstance(r, (str, int)):
                incoming_ids.add(r)
            elif isinstance(r, dict) and r.get(link_key) is not None:
                incoming_ids.add(r.get(link_key))

        # If payload sends empty list, we should delete all existing
        # (so do NOT skip on empty)
        # Fetch table columns once
        cursor.execute("""
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
        """, [schema, child_table])
        table_columns = {row[0] for row in cursor.fetchall()}

        # Get current ids in DB
        cursor.execute(
            sql.SQL("SELECT {} FROM {}.{} WHERE {} = %s").format(
                sql.Identifier(link_key),
                sql.Identifier(schema),
                sql.Identifier(child_table),
                sql.Identifier(parent_fk),
            ),
            [parent_id],
        )
        current_ids = {row[0] for row in cursor.fetchall()}

        to_add = list(incoming_ids - current_ids)
        to_remove = list(current_ids - incoming_ids)

        # Build insert columns
        insert_cols = [parent_fk, link_key]
        insert_vals_template = [parent_id, None]  # link id will be set per row

        # Audit fields (only if exist)
        if "created_by_id" in table_columns and user_id:
            insert_cols.append("created_by_id")
            insert_vals_template.append(user_id)

        if "last_modified_by_id" in table_columns and user_id:
            insert_cols.append("last_modified_by_id")
            insert_vals_template.append(user_id)

        if "last_modified_date" in table_columns:
            insert_cols.append("last_modified_date")
            insert_vals_template.append(now)

        if "organization_id" in table_columns and org:
            insert_cols.append("organization_id")
            insert_vals_template.append(org.get("id"))

        # INSERT missing
        if to_add:
            for link_id in to_add:
                vals = insert_vals_template.copy()
                vals[1] = link_id  # set link id in second position
                q = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
                    sql.Identifier(schema),
                    sql.Identifier(child_table),
                    sql.SQL(", ").join(map(sql.Identifier, insert_cols)),
                    sql.SQL(", ").join(sql.Placeholder() * len(insert_cols)),
                )
                cursor.execute(q, vals)

        # DELETE removed
        if to_remove:
            q = sql.SQL("DELETE FROM {}.{} WHERE {} = %s AND {} = ANY(%s)").format(
                sql.Identifier(schema),
                sql.Identifier(child_table),
                sql.Identifier(parent_fk),
                sql.Identifier(link_key),
            )
            cursor.execute(q, [parent_id, to_remove])




def patch_user_group(update_data, **kwargs): 
    """
    Custom patch function to update user_group fields and sync users, profiles, and public groups.
    """
    group_id = update_data.get('id')
    schema = kwargs.get('schema')
    if not group_id:
        raise Exception("Missing 'id' in update data")

    if not update_data.get('child_tables'):
        selected_users = update_data.get('users', [])  # list of user IDs
        selected_profiles = update_data.get('profile', []) # list of profile IDs
        selected_public_groups = update_data.get('user_group', [])  # list of group IDs

    print("Patching user group:", group_id, update_data)

    try:
        with transaction.atomic():
            # === Update group name ===
            description = update_data.get('description', '')
            new_name = update_data.get('name')
            child_tables = update_data.get('child_tables', [])
            if new_name:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"UPDATE {schema}.user_group SET name = %s, description = %s, modified_at = CURRENT_TIMESTAMP WHERE id = %s",
                        [new_name, description, group_id]
                    )
                    if child_tables:
                        sync_child_tables(
                            cursor,
                            parent_table="user_group",
                            parent_id=group_id,
                            child_tables=child_tables,
                            child_link_key_map={
                                "user_group_users": "user_id",
                                "user_group_profiles": "profile_id",
                                "user_group_public_groups": "public_group_id"
                            },
                            schema=schema
                        )

            if not update_data.get('child_tables'):
            # === Sync Users ===
                with connection.cursor() as cursor:
                    cursor.execute(f"SELECT user_id FROM {schema}.user_group_users WHERE user_group_id = %s", [group_id])
                    current_users = [row[0] for row in cursor.fetchall()]

                selected_user_ids = set(selected_users)
                current_user_ids = set(current_users)

                users_to_add = list(selected_user_ids - current_user_ids)
                users_to_remove = list(current_user_ids - selected_user_ids)

                with connection.cursor() as cursor:
                    if users_to_add:
                        for user_id in users_to_add:
                            cursor.execute(f"""
                                INSERT INTO {schema}.user_group_users (user_group_id, user_id)
                                VALUES (%s, %s)
                                ON CONFLICT DO NOTHING
                            """, [group_id, user_id])
                    
                    if users_to_remove:
                        cursor.execute(f"""
                            DELETE FROM {schema}.user_group_users
                            WHERE user_group_id = %s AND user_id = ANY(%s)
                        """, [group_id, users_to_remove])

                # === Sync Profiles ===
                with connection.cursor() as cursor:
                    cursor.execute(f"SELECT profile_id FROM {schema}.user_group_profiles WHERE user_group_id = %s", [group_id])
                    current_profiles = [row[0] for row in cursor.fetchall()]

                selected_profile_ids = set(selected_profiles)
                current_profile_ids = set(current_profiles)

                profiles_to_add = list(selected_profile_ids - current_profile_ids)
                profiles_to_remove = list(current_profile_ids - selected_profile_ids)

                with connection.cursor() as cursor:
                    if profiles_to_add:
                        for profile_id in profiles_to_add:
                            cursor.execute(f"""
                                INSERT INTO {schema}.user_group_profiles (user_group_id, profile_id)
                                VALUES (%s, %s)
                                ON CONFLICT DO NOTHING
                            """, [group_id, profile_id])
                    
                    if profiles_to_remove:
                        cursor.execute(f"""
                            DELETE FROM {schema}.user_group_profiles
                            WHERE user_group_id = %s AND profile_id = ANY(%s)
                        """, [group_id, profiles_to_remove])

                # === Sync Public Groups ===
                with connection.cursor() as cursor:
                    cursor.execute(f"SELECT public_group_id FROM {schema}.user_group_public_groups WHERE user_group_id = %s", [group_id])
                    current_public_groups = [row[0] for row in cursor.fetchall()]

                selected_pg_ids = set(selected_public_groups)
                current_pg_ids = set(current_public_groups)

                pgs_to_add = list(selected_pg_ids - current_pg_ids)
                pgs_to_remove = list(current_pg_ids - selected_pg_ids)

                with connection.cursor() as cursor:
                    for pg_id in pgs_to_add:
                        cursor.execute(f"""
                            INSERT INTO {schema}.user_group_public_groups (user_group_id, public_group_id)
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                        """, [group_id, pg_id])
                    
                    if pgs_to_remove:
                        cursor.execute(f"""
                            DELETE FROM {schema}.user_group_public_groups
                            WHERE user_group_id = %s AND public_group_id = ANY(%s)
                        """, [group_id, pgs_to_remove])

        return {"success": True, "message": "User group updated successfully."}
    except Exception as e:
        print("Error updating user group:", e)
        return {"success": False, "error": str(e)}


from django.db import connection, DatabaseError
from api.permissions.permissions import get_permissions


def get_permissions_with_users(request, table_name, **kwargs):
    kwargs['tableName'] = table_name
    result = get_permissions(request, **kwargs)

    if table_name == "user_group":
        schema = kwargs.get('schema')

        for record in result.get("data", []):
            try:
                with connection.cursor() as cursor:
                    # Always set schema first
                    cursor.execute("SET search_path TO %s", [schema])

                    # --- Created By ---
                    created_by_id = record.get("created_by_id")
                    if created_by_id:
                        cursor.execute("SELECT name FROM users WHERE id = %s", [created_by_id])
                        row = cursor.fetchone()
                        record["created_by"] = row[0] if row else None

                    # --- Last Modified By ---
                    last_modified_by_id = record.get("last_modified_by_id")
                    if last_modified_by_id:
                        cursor.execute("SELECT name FROM users WHERE id = %s", [last_modified_by_id])
                        row = cursor.fetchone()
                        record["last_modified_by"] = row[0] if row else None

                    # --- User Group Relations ---
                    usergroup_id = record.get("id")
                    if usergroup_id:
                        # Users
                        cursor.execute("""
                            SELECT u.id, u.name, u.email
                            FROM user_group_users ug
                            JOIN users u ON ug.user_id = u.id
                            WHERE ug.user_group_id = %s
                        """, [usergroup_id])
                        record["users"] = [
                            {"id": row[0], "name": row[1], "email": row[2]}
                            for row in cursor.fetchall()
                        ]

                        # Profiles
                        cursor.execute("""
                            SELECT p.id, p.name
                            FROM user_group_profiles ugp
                            JOIN profile p ON ugp.profile_id = p.id
                            WHERE ugp.user_group_id = %s
                        """, [usergroup_id])
                        record["profile"] = [
                            {"id": row[0], "name": row[1]}
                            for row in cursor.fetchall()
                        ]

                        # Public Groups
                        cursor.execute("""
                            SELECT pg.id, pg.name
                            FROM user_group_public_groups ugpg
                            JOIN user_group pg ON ugpg.public_group_id = pg.id
                            WHERE ugpg.user_group_id = %s
                        """, [usergroup_id])
                        record["user_group"] = [
                            {"id": row[0], "name": row[1]}
                            for row in cursor.fetchall()
                        ]

            except DatabaseError as e:
                record["db_error"] = str(e)
    return result


def get_permissions_with_child_tables(request, table_name, **kwargs):
    kwargs['tableName'] = table_name
    result = get_permissions(request, **kwargs)

    if table_name == "target_plan":
        for record in result["data"]:
            plan_id = record.get("id")
            if not plan_id:
                continue

            with connection.cursor() as cursor:
                # Fetch child records from target_logic where is_deleted is false
                cursor.execute("""
                    SELECT * FROM target_logic
                    WHERE target_plan_id = %s AND is_deleted = false
                """, [plan_id])
                logic_columns = [col[0] for col in cursor.description]
                target_logic = [dict(zip(logic_columns, row)) for row in cursor.fetchall()]

                # Fetch child records from incentive_slab where is_deleted is false
                cursor.execute("""
                    SELECT * FROM incentive_slab
                    WHERE target_plan_id = %s AND is_deleted = false
                """, [plan_id])
                slab_columns = [col[0] for col in cursor.description]
                incentive_slab = [dict(zip(slab_columns, row)) for row in cursor.fetchall()]

                # Add both to the parent
                record["target_logic"] = target_logic
                record["incentive_slab"] = incentive_slab

    return result
