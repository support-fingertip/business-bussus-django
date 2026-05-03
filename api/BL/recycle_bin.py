# recycle_bin.py

from django.db import connection

def permanently_delete_records(records, **kwargs):
    if not records:
        raise Exception("No records provided for permanent delete.")

    delete_summary = {}
    schema = kwargs.get('schema', 'public')

    for rec in records:
        object_name = rec.get("object_name")
        record_id = rec.get("record_id")

        if not object_name or not record_id:
            continue

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = %s AND column_name = 'is_deleted' AND table_schema = %s
            """, [object_name, schema])
            column_exists = cursor.fetchone()

            if column_exists:
                cursor.execute("SET search_path TO %s", [schema])
                cursor.execute(f"""
                    SELECT id, is_deleted
                    FROM {object_name}
                    WHERE id = %s
                """, [record_id])
                record = cursor.fetchone()

                if record and record[1]:
                    cursor.execute(f"""
                        DELETE FROM {object_name}
                        WHERE id = %s AND is_deleted = TRUE
                    """, [record_id])

                    if cursor.rowcount > 0:
                        delete_summary.setdefault(object_name, []).append(record_id)
                else:
                    print(f"Record {record_id} not found or not soft-deleted in {object_name}.")

    return {
        "success": True,
        "message": f"Permanently deleted records from {len(delete_summary)} object(s).",
        "details": delete_summary
    }



def empty_recycle_bin(**kwargs):
    delete_summary = {}
    schema = kwargs.get('schema', 'public')

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.columns 
            WHERE column_name = 'is_deleted'
            AND table_schema = %s
        """, [schema])
        tables = [row[0] for row in cursor.fetchall()]

        for table in tables:
            try:
                cursor.execute("SET search_path TO %s", [schema])
                cursor.execute(f"""
                    SELECT id FROM {table} WHERE is_deleted = TRUE
                """)
                record_ids = [row[0] for row in cursor.fetchall()]

                if record_ids:
                    cursor.execute(f"""
                        DELETE FROM {table} WHERE is_deleted = TRUE
                    """)
                    delete_summary[table] = record_ids

            except Exception as e:
                continue

    return {
        "success": True,
        "message": f"Recycle bin emptied. Deleted records from {len(delete_summary)} table(s).",
        "details": delete_summary
    }


# def get_deleted_records():
#     deleted_data = {}

#     with connection.cursor() as cursor:
#         cursor.execute("""
#             SELECT table_name 
#             FROM information_schema.tables 
#             WHERE table_schema = 'public'
#         """)
#         tables = cursor.fetchall()

#     for table in tables:
#         table_name = table[0]

#         with connection.cursor() as cursor:
#             cursor.execute("""
#                 SELECT column_name
#                 FROM information_schema.columns
#                 WHERE table_name = %s
#             """, [table_name])
#             columns = [col[0] for col in cursor.fetchall()]

#             has_is_deleted = 'is_deleted' in columns
#             has_name = 'name' in columns

#         if has_is_deleted:
#             select_columns = "id"
#             if has_name:
#                 select_columns += ", name"

#             try:
#                 with connection.cursor() as cursor:
#                     cursor.execute(f"""
#                         SELECT {select_columns}
#                         FROM "{table_name}"
#                         WHERE is_deleted = TRUE
#                     """)
#                     records = cursor.fetchall()

#                 if records:
#                     deleted_data[table_name] = []
#                     for record in records:
#                         item = {'id': record[0]}
#                         if has_name:
#                             item['name'] = record[1]
#                         deleted_data[table_name].append(item)
#             except Exception as e:
#                 print(f"Error reading from {table_name}: {str(e)}")
#     return deleted_data



def get_deleted_records(**kwargs):
    schema = kwargs.get('schema', 'public')
    deleted_data = {}

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = %s
        """, [schema])
        tables = cursor.fetchall()

    for table in tables:
        table_name = table[0]

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s AND table_schema = %s
            """, [table_name, schema])
            columns = [col[0] for col in cursor.fetchall()]

            has_is_deleted = 'is_deleted' in columns
            has_name = 'name' in columns
            has_deleted_by = 'deleted_by' in columns
            has_deleted_by_id = 'deleted_by_id' in columns
            has_deleted_date = 'deleted_date' in columns

        if has_is_deleted:
            select_columns = [f"{table_name}.id AS id"]
            mapedcolumns = ["id"]
            if has_name:
                select_columns.append(f"{table_name}.name AS name")
                mapedcolumns.append("name")
            if has_deleted_by:
                select_columns.append(f"{table_name}.deleted_by AS deleted")
            if has_deleted_by_id:
                select_columns.append("u.name AS deleted_by_username")
                mapedcolumns.append("deleted_by")
            if has_deleted_date:
                select_columns.append(f"{table_name}.deleted_date AS deleted_date")
                mapedcolumns.append("deleted_date")
            select_columns_str = ", ".join(select_columns)
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET search_path TO %s", [schema])
                    try:
                        cursor.execute(f"""
                            SELECT 
                            {select_columns_str}
                            FROM "{table_name}"
                            LEFT JOIN public.users u ON "{table_name}".deleted_by_id = u.id
                            WHERE {table_name}.is_deleted = TRUE 
                            LIMIT 25
                        """)
                        records = cursor.fetchall()
                    except Exception as e:
                        cursor.execute(f"""
                            SELECT {select_columns_str}
                            FROM "{table_name}"
                            WHERE is_deleted = TRUE LIMIT 25
                        """)
                        records = cursor.fetchall()
                if records:
                    deleted_data[table_name] = []
                    for record in records:
                        item = dict(zip(mapedcolumns, record))
                        deleted_data[table_name].append(item)
            except Exception as e:
                ...
            print(f"Deleted records from {table_name}: {deleted_data.get(table_name, [])}")
    return deleted_data



def restore_soft_deleted_records(records, **kwargs):
    if not records:
        raise Exception("No records provided for restore.")

    restored_summary = {}

    for rec in records:
        table_name = rec.get("table_name") or rec.get("object_name")
        record_id = rec.get("record_id")

        if not table_name or not record_id:
            continue  # Optionally log this

        with connection.cursor() as cursor:
            # Ensure table exists in schema and is_deleted column exists
            cursor.execute("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name = %s AND column_name = 'is_deleted' AND table_schema = %s
            """, [table_name, kwargs.get('schema', 'public')])
            column_exists = cursor.fetchone()

        if column_exists:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET search_path TO %s", [kwargs.get('schema', 'public')])
                    cursor.execute(f"""
                        UPDATE "{table_name}"
                        SET is_deleted = FALSE
                        WHERE id = %s AND is_deleted = TRUE
                    """, [record_id])

                    if cursor.rowcount > 0:
                        restored_summary.setdefault(table_name, []).append(record_id)
            except Exception as e:
                print(f"Failed to restore {table_name} ID {record_id}: {e}")
                continue

    return {
        "success": True,
        "message": f"Restored records from {len(restored_summary)} object(s).",
        "details": restored_summary,
    }

