
from django.db import connection
def get_instance_label(instance):
    return (
        getattr(instance, 'name', None)
        or getattr(instance, 'title', None)
        or getattr(instance, 'full_name', None)
        or getattr(instance, 'first_name', None)
        or getattr(instance, 'email', None)
        or str(instance)
    )

def check_object_exists_raw(object_name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM object WHERE name = %s LIMIT 1", [object_name])
        return cursor.fetchone() is not None

from datetime import datetime

def log_audit_sql(cursor, user_id, action, section, prefix=None, is_delegate=False):
    now = datetime.utcnow()

    # Check if a similar audit entry already exists
    check_query = """
        SELECT 1 FROM audit_trail_track
        WHERE user_id = %s AND action = %s AND section = %s AND changed_at = %s
    """
    cursor.execute(check_query, [user_id, action, section, now])

    # Insert only if not already present
    if not cursor.fetchone():
        insert_query = """
            INSERT INTO audit_trail_track (user_id, action, section, source_namespace_prefix, is_delegate_user, changed_at)
            VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(insert_query, [user_id, action, section, prefix, is_delegate, now])
        
def log_audit(action, section, is_delegate=False, prefix=None, **kwargs):
    user_id = kwargs.get('user_',{}).get('id')
    with connection.cursor() as cursor:
        cursor.execute("""SET search_path TO %s""", [kwargs.get('schema', 'public')])
        try:
            insert_query = """
                INSERT INTO audit_trail_track (user_id, action, section, source_namespace_prefix, is_delegate_user, changed_at)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_query, [user_id, action, section, prefix, is_delegate, datetime.utcnow()])
        except Exception as e:
            pass
            
