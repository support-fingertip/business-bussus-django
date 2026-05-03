"""Per-RECORD sharing grants — see ``shared_records`` table.

Naming caution:
  * ``shared_records``   ← THIS module. PER-RECORD ad-hoc grants
                            (record_id + user_id + access_mask +
                            expires_at). Used to share a single record
                            with one extra user temporarily.
  * ``sharing_records``  ← DIFFERENT TABLE. PER-OBJECT default access
                            level (Private / Public Read Only /
                            Public Read Write). One row per object.
                            See ``api/tenant_models/sharing.py``.

These two tables sound nearly identical and they are NOT the same.
Don't conflate them when writing queries or new code.
"""

from django.db import connection

def fetch_shared_records(user_id, object_name, schema, type='read'):
    """
    Fetch records shared with the user for a specific object.

    Reads from the ``shared_records`` table — the per-RECORD ad-hoc
    grants (record_id + user_id + access_mask + expires_at). NOT
    ``sharing_records`` (per-object default access level).

    type can be a single permission string ('read', 'write', 'delete', 'share')
    or a combined string like 'read/write' to match records with ANY of those permissions.
    """
    access_mask_map = {'read': 1, 'write': 2, 'delete': 4, 'share': 8}
    # Support combined types like 'read/write'
    types = [t.strip() for t in type.split('/')]
    combined_mask = 0
    for t in types:
        combined_mask |= access_mask_map.get(t, 0)
    if combined_mask == 0:
        combined_mask = 1  # default to read
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO %s", [schema])
            query = """
                select record_id, owner_id,
                  CASE
                    WHEN (access_mask & 2) != 0 THEN 'read/write'
                    ELSE 'read'
                  END AS access_type
                from shared_records
                where user_id = %s and object_name = %s
                  and (access_mask & %s) != 0
                  and (expires_at IS NULL OR expires_at > now());
            """
            cursor.execute(query, [user_id, object_name, combined_mask])
            columns = [col[0] for col in cursor.description]
            results = cursor.fetchall()
        
        return [dict(zip(columns, row)) for row in results]
    except Exception as e:
        raise Exception(f"Error fetching shared records: {str(e)}")