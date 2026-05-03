from django.db import connection



from django.db import connection

def get_record_from_sql(table_name, record_id):
    with connection.cursor() as cursor:
        query = f'SELECT * FROM "{table_name}" WHERE id = %s'
        cursor.execute(query, [record_id])
        desc = [col[0] for col in cursor.description]
        row = cursor.fetchone()

        if not row:
            raise Exception(f"Record with ID {record_id} not found in {table_name}.")

        return dict(zip(desc, row))



def get_user_app_password(user_id):
    with connection.cursor() as cursor:
        cursor.execute("SELECT app_password FROM users WHERE id = %s", [user_id])
        row = cursor.fetchone()
    return row[0] if row else None

def update_user_app_password(user_id, new_password):
    with connection.cursor() as cursor:
        cursor.execute("UPDATE users SET app_password = %s WHERE id = %s", [new_password, user_id])