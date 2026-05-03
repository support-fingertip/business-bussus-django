from django.db import connection, transaction, DatabaseError
import json

from CacheService.cache import CacheService
from api.ORM.AuditLogs.audit_trail_logs import log_audit
from api.security.schema_authority import get_validated_schema

def update_page_builder(data, **kwargs):
    try:
        page_builder = data.get('page_builder')
        components = data.get('components')
        shared_profiles = data.get('shared_profiles')
        # Validation
        if not page_builder or not isinstance(page_builder, dict):
            raise ValueError("Invalid or missing 'page_builder' data.")
        if 'id' not in page_builder:
            raise ValueError("Missing 'id' in 'page_builder'.")
        if 'name' not in page_builder:
            raise ValueError("Missing 'name' in 'page_builder'.")
        if 'description' not in page_builder:
            raise ValueError("Missing 'description' in 'page_builder'.")
        if 'layout' not in page_builder:
            raise ValueError("Missing 'layout' in 'page_builder'.")

        page_id = page_builder.get('id')
        CacheService().invalidate_by_id(page_id, "page_builder", get_validated_schema(kwargs))
        with connection.cursor() as cursor, transaction.atomic():
            cursor.execute("SET search_path TO %s;", [get_validated_schema(kwargs)])
            cursor.execute(
                """
                UPDATE page_builder SET
                    name = %s,
                    description = %s,
                    layout = %s,
                    last_modified_date = CURRENT_TIMESTAMP
                WHERE id = %s;
                """,
                [
                    page_builder.get('name'),
                    page_builder.get('description'),
                    json.dumps(page_builder.get('layout')),
                    page_id
                ]
            )

            # Replace shared profiles: delete old assignments, insert new ones
            cursor.execute(
                "DELETE FROM page_builder_assignment WHERE page_builder_id=%s;", [page_id]
            )

            if shared_profiles and isinstance(shared_profiles, list):
                user_id = kwargs.get('user_id')
                for profile in shared_profiles:
                    profile_id = profile.get('profile_id')
                    if not profile_id:
                        raise ValueError("Missing 'profile_id' in shared profile.")
                    cursor.execute(
                        """
                        INSERT INTO page_builder_assignment
                            (page_builder_id, profile_id, created_date, last_modified_date, created_by_id, last_modified_by_id)
                        VALUES
                            (%s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, %s, %s);
                        """,
                        [page_id, profile_id, user_id, user_id]
                    )

            cursor.execute(
                "DELETE FROM page_component WHERE page_builder_id=%s;", [page_id]
            )

            if components and isinstance(components, list):
                for component in components:
                    # Validate component fields
                    required_fields = ['name', 'type', 'data_source', 'listview_id', 'geometry']
                    for field in required_fields:
                        if field not in component:
                            raise ValueError(f"Missing '{field}' in component.")

                    cursor.execute(
                        """
                        INSERT INTO page_component
                            (page_builder_id, name, type, data_source, listview_id, dashboard_component_id, geometry, created_date, last_modified_date)
                        VALUES
                            (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
                        """,
                        [
                            page_id,
                            component.get('name'),
                            component.get('type'),
                            component.get('data_source'),
                            component.get('listview_id', None),
                            component.get('dashboard_component_id', None),
                            json.dumps(component.get('geometry')),
                        ]
                    )
        log_audit(
            f"Updated Page Builder: {page_builder.get('name')}",
            "Page Builder Update",
            **kwargs,
        )
        return {"success": True, "message": "Page builder updated successfully."}
    except (ValueError, DatabaseError) as e:
        raise Exception(str(e))
    except Exception as e:
        raise Exception(str(e))