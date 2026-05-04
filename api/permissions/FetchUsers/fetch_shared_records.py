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
from django.utils import timezone

from api.permissions._orm_dispatch import dispatch as _dispatch_path


# Bitmask values — match ``api/tenant_models/misc.SharedRecord.ACCESS_*``.
_ACCESS_MASK_MAP = {"read": 1, "write": 2, "delete": 4, "share": 8}


def _build_combined_mask(type_str: str) -> int:
    """Convert a combined type string like 'read/write' to a bitmask."""
    types = [t.strip() for t in type_str.split("/")]
    combined = 0
    for t in types:
        combined |= _ACCESS_MASK_MAP.get(t, 0)
    return combined or 1  # default to read


def _fetch_shared_records_raw(user_id, object_name, schema, combined_mask):
    """Legacy raw-SQL path — same query as before, byte-identical shape."""
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


def _fetch_shared_records_orm(user_id, object_name, schema, combined_mask):
    """ORM path against the Phase 3.B SharedRecord model.

    Returns the same shape as the raw path:
      [{'record_id': ..., 'owner_id': ..., 'access_type': 'read'/'read/write'}, ...]
    """
    from api.tenant_models import SharedRecord

    with connection.cursor() as cur:
        cur.execute("SET search_path TO %s", [schema])

    # SharedRecord.access_mask is a Postgres int. Django ORM doesn't have
    # a native bitwise-AND filter, so we use F() expressions with the
    # `BitAnd` operator via the .extra-equivalent: a raw-SQL annotation
    # via a custom Q. The cleanest portable approach: read all rows
    # for the (user, object) pair, then post-filter in Python on the
    # bitmask. Fan-in is small (per-(user, object), and the index on
    # (user_id, object_name) means it's cheap).
    now = timezone.now()
    rows = (
        SharedRecord.objects
        .filter(user_id=user_id, object_name=object_name)
        .filter(models_q_expires_or_null(now))
        .values_list("record_id", "owner_id", "access_mask")
    )

    out = []
    for record_id, owner_id, mask in rows:
        if (mask & combined_mask) == 0:
            continue
        out.append({
            "record_id": record_id,
            "owner_id": owner_id,
            "access_type": "read/write" if (mask & 2) != 0 else "read",
        })
    return out


def models_q_expires_or_null(now):
    """``expires_at IS NULL OR expires_at > now`` as a Django Q."""
    from django.db.models import Q
    return Q(expires_at__isnull=True) | Q(expires_at__gt=now)


def fetch_shared_records(user_id, object_name, schema, type="read"):
    """
    Fetch records shared with the user for a specific object.

    Reads from the ``shared_records`` table — the per-RECORD ad-hoc
    grants (record_id + user_id + access_mask + expires_at). NOT
    ``sharing_records`` (per-object default access level).

    ``type`` can be a single permission string ('read', 'write',
    'delete', 'share') or a combined string like 'read/write' to
    match records with ANY of those permissions.

    Phase 3.C wave 2: dual-path behind ``USE_ORM_FOR_BL`` flag.
    Both paths return the same list-of-dicts shape.
    """
    combined_mask = _build_combined_mask(type)
    try:
        return _dispatch_path(
            "fetch_shared_records",
            raw_impl=lambda: _fetch_shared_records_raw(
                user_id, object_name, schema, combined_mask
            ),
            orm_impl=lambda: _fetch_shared_records_orm(
                user_id, object_name, schema, combined_mask
            ),
            flag="USE_ORM_FOR_BL",
        )
    except Exception as e:
        raise Exception(f"Error fetching shared records: {str(e)}")
