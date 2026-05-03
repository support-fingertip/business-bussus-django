
from psycopg2 import sql
from django.db import connection, transaction
from django.db import DatabaseError
from api.ORM.sqlFunctions.utils.error_handlers import explain_db_error

def create_task_sql(data, object_name, user=None, section=None):
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                subject = data.get("subject")
                status = data.get("status")
                due_date = data.get("due_date")
                assigned_to_id = data.get("assigned_to")
                related_object_id = data.get("related_object_id")

                # Step 1: Verify assigned user exists and fetch username
                cursor.execute("SELECT id, username FROM users WHERE id = %s", (assigned_to_id,))
                user_row = cursor.fetchone()
                if not user_row:
                    raise ValueError("Assigned user not found.")
                assigned_user_id, assigned_username = user_row

                # Step 2: Get content_type_id for the related object
                cursor.execute(
                    "SELECT id FROM django_content_type WHERE app_label = %s AND model = %s",
                    ('custom_models', object_name.lower())
                )
                ct_row = cursor.fetchone()
                if not ct_row:
                    raise ValueError(f"ContentType for model '{object_name}' not found.")
                content_type_id = ct_row[0]

                # Step 3: Insert task record - Fixed placeholder count to match values
                insert_query = sql.SQL("""
                    INSERT INTO task (
                        subject, status, due_date, assigned_to_id,
                        content_type_id, related_to_object_id
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id, subject, status, due_date, assigned_to_id, related_to_object_id
                """)
                cursor.execute(insert_query, (
                    subject, status, due_date, assigned_user_id,
                    content_type_id, related_object_id
                ))
                task_row = cursor.fetchone()

                return {
                    "success": True,
                    "data": {
                        "id": task_row[0],
                        "subject": task_row[1],
                        "status": task_row[2],
                        "due_date": task_row[3],
                        "assigned_to": assigned_username,
                        "related_to": related_object_id
                    }
                }

    except (ValueError, DatabaseError) as e:
        return {
            "success": False,
            "error": explain_db_error(e) if isinstance(e, DatabaseError) else str(e)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
