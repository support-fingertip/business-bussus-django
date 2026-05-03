from django.db import connection
from psycopg2.sql import SQL, Identifier
# from django_redis import get_redis_connection
# from django.core.cache import cache

def get_all_subordinate_ids(manager_id: str, schema_name: str) -> list[str]:
    """
    Return all subordinate user IDs (direct & indirect) for manager_id
    from {schema_name}.users. Excludes the manager_id itself.
    """
    # version = _get_usergraph_version(schema_name)
    # cache_key = f"subordinates:{schema_name}:{manager_id}:v{version}"
    
    # cached = cache.get(cache_key)
    # if cached is not None:
    #     return cached
    
    query = SQL("""
        WITH RECURSIVE subordinates(id, path) AS (
            -- level 1: direct reports
            SELECT u.id, ARRAY[u.id]::text[]
            FROM {}.users u
            WHERE u.manager_id = %s

            UNION ALL

            -- descend indefinitely (cycle-safe)
            SELECT u2.id, s.path || u2.id::text
            FROM {}.users u2
            JOIN subordinates s ON u2.manager_id = s.id
            -- prevent cycles
            WHERE NOT (u2.id::text = ANY(s.path))
        )
        SELECT id FROM subordinates
    """).format(Identifier(schema_name), Identifier(schema_name))

    try:
        with connection.cursor() as cur:
            cur.execute(query, (manager_id,))
            results = [r[0] for r in cur.fetchall()]
            try:
                results.append(manager_id) 
            except Exception as e:
                print(f"Error adding manager_id to results: {e}")
            return results # include self        
    except Exception as e:
        # log as needed
        print(f"Error: {e}")
        return [manager_id]
    
    # cache.set(cache_key, results, timeout=600)  # cache for 10 minutes
    return results
    
    
# def _get_usergraph_version(schema_name: str) -> str:
#     r = get_redis_connection("default")
#     ver_key = f"usergraph:ver:{schema_name}"
#     ver = r.get(ver_key)
#     if ver is None:
#         # initialize to "1"
#         r.set(ver_key, 1)
#         return "1"
#     return ver.decode()

# def bump_usergraph_version(schema_name: str) -> None:
#     """Call this after any INSERT/UPDATE/DELETE that changes the users hierarchy."""
#     r = get_redis_connection("default")
#     r.incr(f"usergraph:ver:{schema_name}")
