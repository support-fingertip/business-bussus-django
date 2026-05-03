from datetime import datetime
from psycopg2 import sql
from django.db import connection, transaction
from api.ORM.sqlFunctions.utils.helpers import validate_identifier
from django.utils import timezone


def delete_data_sql(object_name, id_list, section=None, permanent=False, **kwargs):
    user = kwargs.get('user_')
    schema = kwargs.get('schema')
    if not schema:
        raise ValueError("Invalid user request: 'schema' is required in kwargs")
    
    # Validate identifiers
    validate_identifier(schema)
    
    try:
        table_name = object_name.lower()
        validate_identifier(table_name)
        
        with transaction.atomic():
            with connection.cursor() as cursor:
                # Use SET LOCAL for search_path within transaction
                cursor.execute("SET LOCAL search_path TO %s", [schema])

                # Check if the table exists
                cursor.execute("SELECT to_regclass(%s)", [table_name])
                if cursor.fetchone()[0] is None:
                    raise Exception(f"Table '{table_name}' does not exist.")

                # Check if the 'is_deleted' column exists (for soft delete)
                cursor.execute("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = %s AND table_schema = %s
                """, [table_name, schema])
                columns = [row[0] for row in cursor.fetchall()]
                soft_delete_supported = 'is_deleted' in columns

                deleted_count_ = 0

                for record_id in id_list:
                    # Fetch the record to log before deletion
                    cursor.execute(
                        sql.SQL("SELECT * FROM {} WHERE id = %s").format(sql.Identifier(table_name)),
                        [record_id]
                    )
                    instance_data = cursor.fetchone()

                    if not instance_data:
                        raise Exception(f"No data found with ID {record_id} to delete.")

                    if soft_delete_supported and not permanent:
                        set_clauses = ["is_deleted = %s"]
                        values = [True]

                        # Add deleted_by and deleted_date if those columns exist
                        cursor.execute("""
                            SELECT column_name
                            FROM information_schema.columns
                            WHERE table_name = %s AND column_name IN ('deleted_by_id', 'deleted_date') AND table_schema = %s
                        """, [table_name, schema])
                        cols = [row[0] for row in cursor.fetchall()]

                        if 'deleted_by_id' in cols and user:
                            # If user is a dict
                            if isinstance(user, dict):
                                set_clauses.append("deleted_by_id = %s")
                                values.append(user.get('id'))
                            # If user is an object
                            elif hasattr(user, 'id'):
                                set_clauses.append("deleted_by_id = %s")
                                values.append(getattr(user, 'id', None))

                        if 'deleted_date' in cols:
                            set_clauses.append("deleted_date = %s")
                            values.append(timezone.now())

                        values.append(record_id)

                        cursor.execute(
                            sql.SQL("UPDATE {} SET " + ", ".join(set_clauses) + " WHERE id = %s").format(
                                sql.Identifier(table_name)
                            ),
                            values
                        )
                    else:
                        # Perform hard delete if soft delete is not supported
                        cursor.execute(
                            sql.SQL("DELETE FROM {} WHERE id = %s").format(sql.Identifier(table_name)),
                            [record_id]
                        )
                    deleted_count_ += 1

                return {"success": True, "message": f"Deleted {deleted_count_} record(s)."}

    except Exception as e:
        raise Exception(str(e))
