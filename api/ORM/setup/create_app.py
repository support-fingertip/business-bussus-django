import json
import uuid
from django.db import connection, transaction

from api.ORM.AuditLogs.audit_trail_logs import log_audit

def create_app(data, section=None, **kwargs):
    app_data = data.get("app")
    user = kwargs.get('user_',{})
    tabs = app_data.get('tabs')
    app_data['tabs'] = json.dumps(tabs)
    profiles = data.get("profiles", [])

    if not app_data:
        raise ValueError("Please provide app details.")

    if not isinstance(profiles, list):
        raise ValueError("Profiles should be a list.")

    try:
        with connection.cursor() as cursor, transaction.atomic():
            # ✅ Insert App
            app_fields = ", ".join(app_data.keys())
            placeholders = ", ".join(["%s"] * len(app_data))
            values = list(app_data.values())

            insert_app_sql = f"INSERT INTO app ({app_fields}) VALUES ({placeholders}) RETURNING id, name, description"
            cursor.execute(insert_app_sql, values)
            app_row = cursor.fetchone()

            if not app_row:
                raise Exception("App creation failed.")

            app_id, app_name, app_description = app_row

            # ✅ Fetch valid profiles
            profile_ids = [p.get('id') for p in profiles if p.get('id')]
            cursor.execute(
                "SELECT id FROM profile WHERE id IN %s",
                [tuple(profile_ids)] if profile_ids else [tuple()]
            )
            valid_profile_ids = {str(row[0]) for row in cursor.fetchall()}

            # ✅ Create AppPermission records
            permission_values = []
            for profile in profiles:
                profile_id = profile.get('id')
                access = profile.get('access')

                if not profile_id or profile_id not in valid_profile_ids:
                    continue

                permission_id = f"019ApR{uuid.uuid4().hex[:9]}p"
                permission_values.append((permission_id, profile_id, app_id, access))

            if permission_values:
                cursor.executemany(
                    "INSERT INTO app_permissions (id, profile_id, app_id, access) VALUES (%s, %s, %s, %s)",
                    permission_values
                )                
            
            log_audit(
                f"Created App: {app_name}",
                "App Creation",
                **kwargs,
            )

        # ✅ Return result
        return {
            "message": "App created successfully",
            "app": {
                "id": app_id,
                "name": app_name,
                "description": app_description,
            }
        }

    except Exception as e:
        raise Exception(str(e))
