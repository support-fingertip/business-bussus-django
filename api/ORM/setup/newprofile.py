from django.db import connection, transaction

from api.ORM.AuditLogs.audit_trail_logs import log_audit

def new_profile(existing_profile_id, new_profile_name, **kwargs):
    created_by = kwargs.get('user_', {}).get('id')
    try:
        with connection.cursor() as cursor, transaction.atomic():
            # Fetch the existing profile details
            cursor.execute("""SET search_path TO %s""", [kwargs.get('schema')])
            cursor.execute("SELECT id, name, profile_type FROM profile WHERE id = %s", [existing_profile_id])
            existing_profile = cursor.fetchone()
            if not existing_profile:
                raise Exception("Profile not found!")

            existing_profile_name = existing_profile[1]
            existing_profile_type = existing_profile[2]

            # Create a new profile
            cursor.execute("""
                INSERT INTO profile (name, profile_type, created_by_id, last_modified_by_id)
                VALUES (%s, %s, %s, %s) RETURNING id
            """, [new_profile_name, existing_profile_type, created_by, created_by])
            
            row = cursor.fetchone()
            new_profile_id = row[0]

            # Copy Object Permissions
            cursor.execute("""
                SELECT object_id, read, write, edit, delete, view_all, modify_all 
                FROM object_permissions
                WHERE profile_id = %s
            """, [existing_profile_id])
            object_permissions = cursor.fetchall()
            for perm in object_permissions:
                cursor.execute("""
                    INSERT INTO object_permissions (object_id, profile_id, read, write, edit, delete, view_all, modify_all)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, [perm[0], new_profile_id, perm[1], perm[2], perm[3], perm[4], perm[5], perm[6]])

            # Copy Field Permissions
            cursor.execute("""
                SELECT object_id, fields_id, read_only, visible, edit_access, read_access
                FROM field_permissions
                WHERE profile_id = %s
            """, [existing_profile_id])
            field_permissions = cursor.fetchall()
            for perm in field_permissions:
                cursor.execute("""
                    INSERT INTO field_permissions (object_id, fields_id, profile_id, read_only, visible, edit_access, read_access)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, [perm[0], perm[1], new_profile_id, perm[2], perm[3], perm[4], perm[5]])

            # Copy Tab Permissions
            cursor.execute("""
                SELECT object_id, type FROM tab_permissions WHERE profile_id = %s
            """, [existing_profile_id])
            tab_permissions = cursor.fetchall()
            for perm in tab_permissions:
                cursor.execute("""
                    INSERT INTO tab_permissions (object_id, profile_id, type)
                    VALUES (%s, %s, %s)
                """, [perm[0], new_profile_id, perm[1]])
                
            # Copy Tab Permissions
            cursor.execute("""
                SELECT object_id, page_layouts_id, record_type FROM layout_assignment WHERE profile_id = %s
            """, [existing_profile_id])
            layout_assignment = cursor.fetchall()
            for layout in layout_assignment:
                cursor.execute("""
                    INSERT INTO layout_assignment (object_id, profile_id, page_layouts_id, record_type)
                    VALUES (%s, %s, %s, %s)
                """, [layout[0], new_profile_id, layout[1], layout[2]])

            # Copy App Permissions
            cursor.execute("""
                SELECT app_id, access FROM app_permissions WHERE profile_id = %s
            """, [existing_profile_id])
            app_permissions = cursor.fetchall()
            for perm in app_permissions:
                cursor.execute("""
                    INSERT INTO app_permissions (profile_id, access, app_id)
                    VALUES (%s, %s, %s)
                """, [new_profile_id, perm[1], perm[0]])
            
            # Copy Homepage Assignments
            cursor.execute("""
                SELECT page_id FROM homepage_assignment WHERE profile_id = %s
            """, [existing_profile_id])
            homepage_assignments = cursor.fetchall()
            for assignment in homepage_assignments:
                cursor.execute("""
                    INSERT INTO homepage_assignment (profile_id, page_id)
                    VALUES (%s, %s)
                """, [new_profile_id, assignment[0]])
        
            # Audit log
            log_audit(
                f"Created new profile {new_profile_name} based on {existing_profile_name}",
                "Profile Creation",
                **kwargs
            )
        return {
            "message": "Profile created successfully",
            "profile": {
                "id": new_profile_id,
                "name": new_profile_name,
                "based_on": existing_profile_name
            },
            "status": "ok",
            "success": True
        }

    except Exception as e:
        raise Exception(str(e))
