"""Per-object allowed-write field lists + payload sanitiser — Phase 8.A8.

In plain English
----------------

When a user POSTs to ``/api/leads`` with a JSON body, the BL layer
historically built the insert payload as::

    create_data = {**user_payload, 'created_by_id': user_id, 'created_date': now}

This pattern *spreads* every key the user sent into the database
insert. The four system fields layered on top correctly override
their named keys (`created_by_id` etc.) — but ANY OTHER key the
user invents goes straight to the DB. SECURITY_AUDIT_REPORT
graded this HIGH because it lets a user:

  * Set ``id`` to a chosen value (collide with an existing row, take
    over its place in the audit log).
  * Set ``owner_id`` to claim ownership.
  * Set ``organization_id`` to another tenant (RLS catches this now,
    but defense in depth).
  * Toggle ``is_deleted`` to undelete a soft-deleted row of their own.

This module provides:

  1. :func:`get_allowed_create_fields(schema, object_name)` —
     authoritative list of fields a user MAY submit for a new row,
     pulled from the per-tenant ``fields`` metadata table.

  2. :func:`sanitize_create_payload(payload, schema, object_name, user_id)` —
     strips disallowed keys, then layers system fields on top so they
     can't be user-supplied. Returns the safe dict to pass to
     ``post_permission`` / ``post_data_sql``.

  3. :data:`SYSTEM_FIELDS_DENYLIST` — the hardcoded list of fields the
     application owns and the user MUST NOT be allowed to set or
     modify directly via the public API. Even if a tenant's fields
     metadata says they're modifiable, this denylist wins.

How the allow-list works
------------------------

Per-tenant CRMs define their own field set per object (the platform
lets admins add custom fields). The ``fields`` table records each
field with ``is_modifiable``. The allow-list = every modifiable field
on the object MINUS the system denylist.

Cached in-process with a 5-minute TTL, plus an invalidate() hook
for the DDL paths that mutate the ``fields`` table (add_field /
drop_field). The TTL is a safety net for when the hook is forgotten.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Optional

from django.db import connection

logger = logging.getLogger(__name__)


# System fields the user cannot supply. Even if the per-tenant
# metadata flags one of these as modifiable, this list wins.
# Layered on top of every payload BY the application.
SYSTEM_FIELDS_DENYLIST: frozenset[str] = frozenset({
    "id",                            # server-generated
    "created_by_id",
    "created_date",
    "last_modified_by_id",
    "last_modified_date",
    "deleted_by_id",
    "deleted_date",
    "is_deleted",                    # soft-delete flag
    "organization_id",               # tenant pinning — never user-controlled
    "tenant_id",                     # alias for organization_id in some tables
    "owner_id",                      # only the platform's ownership flow can set this
})


# Cache: {(schema, object_name): (frozenset[str], fetched_at_unix_ts)}
_cache: dict[tuple[str, str], tuple[frozenset[str], float]] = {}
_cache_lock = threading.RLock()


# Default TTL — 5 minutes. Per-DDL-path invalidation is the primary
# freshness mechanism; this bounds staleness if invalidate() is forgotten.
DEFAULT_TTL_SECONDS = 300


def get_allowed_create_fields(
    schema: str,
    object_name: str,
    *,
    ttl: int = DEFAULT_TTL_SECONDS,
) -> frozenset[str]:
    """Return the set of field names a user MAY supply on a POST for ``object_name``.

    Pulls from the per-tenant ``fields`` table — every row where
    ``object_name`` matches and ``is_modifiable = TRUE``, minus the
    hardcoded system-fields denylist.

    Cached per (schema, object_name) with a 5-minute TTL.

    Returns
    -------
    A frozenset of allowed field names. An empty set means EITHER
    the object has no modifiable fields (unlikely) OR the metadata
    query failed (we fail closed — caller rejects everything).
    """
    if not schema or not object_name:
        return frozenset()

    key = (schema, object_name)
    now = time.time()

    with _cache_lock:
        entry = _cache.get(key)
        if entry is not None:
            fields, fetched_at = entry
            if now - fetched_at < ttl:
                return fields

    try:
        with connection.cursor() as cur:
            # Pin search_path to the tenant schema for this lookup.
            # We don't change role / app.current_org_id here — they're
            # already set by middleware before BL code runs.
            from api.ORM.sqlFunctions.utils.helpers import validate_identifier
            validate_identifier(schema, "schema")
            cur.execute(
                "SET LOCAL search_path TO %s, public", [schema],
            )
            cur.execute(
                "SELECT name FROM fields "
                "WHERE object_name = %s "
                "  AND (is_modifiable IS NULL OR is_modifiable = TRUE)",
                [object_name],
            )
            rows = cur.fetchall()
    except Exception:
        logger.exception(
            "get_allowed_create_fields: metadata lookup failed",
            extra={"schema": schema, "object_name": object_name},
        )
        return frozenset()

    fields = frozenset(
        row[0] for row in rows
        if row[0] and row[0] not in SYSTEM_FIELDS_DENYLIST
    )
    with _cache_lock:
        _cache[key] = (fields, now)
    return fields


def invalidate(schema: str, object_name: Optional[str] = None) -> None:
    """Drop the cached field list. Call from add_field / drop_field paths."""
    with _cache_lock:
        if object_name is None:
            stale = [k for k in _cache if k[0] == schema]
            for k in stale:
                del _cache[k]
        else:
            _cache.pop((schema, object_name), None)


def invalidate_all() -> None:
    """Clear the entire cache. Useful in tests."""
    with _cache_lock:
        _cache.clear()


def sanitize_create_payload(
    payload: dict,
    *,
    schema: str,
    object_name: str,
    user_id: Optional[str] = None,
    extra_system_fields: Optional[dict] = None,
    now: Optional[Any] = None,
) -> tuple[dict, list[str]]:
    """Build a safe create payload from ``payload`` for ``object_name``.

    Steps:
      1. Filter ``payload`` down to keys on the allow-list for this
         object. Disallowed keys are dropped + logged.
      2. Strip any system-fields from what remains (defence in depth —
         even if a system field somehow ended up on the allow-list, the
         user's supplied value never wins).
      3. Layer system fields on top:
           * created_by_id        = user_id
           * last_modified_by_id  = user_id
           * created_date         = now (or datetime.now())
           * last_modified_date   = now

    Returns
    -------
    (safe_payload, dropped_keys)
        ``safe_payload`` is the dict to pass to post_permission /
        post_data_sql. ``dropped_keys`` is the list of keys removed
        for callers that want to log / alert / 400 on the dropped
        keys (some call sites should treat dropped keys as a hard
        client error rather than silent removal).

    Notes
    -----
    * ``id`` is intentionally NOT layered here — the platform
      generates object-prefixed IDs via the BL's own id-generator;
      this helper just makes sure the user's `id` is dropped if they
      supplied one.

    * ``owner_id``, ``organization_id`` are denylisted — the caller
      that has a legitimate reason to set them (e.g. an ownership
      transfer endpoint) should supply them in ``extra_system_fields``,
      which bypasses the denylist on purpose.
    """
    from datetime import datetime

    if not isinstance(payload, dict):
        # Defensive — some callers pass JSON strings or None.
        return {}, []

    allowed = get_allowed_create_fields(schema, object_name)
    if not allowed:
        # No metadata → reject everything except system fields. Better
        # to send back a 400 than silently insert nothing.
        logger.warning(
            "sanitize_create_payload: empty allow-list",
            extra={"schema": schema, "object_name": object_name},
        )

    dropped: list[str] = []
    safe: dict = {}
    for k, v in payload.items():
        if k in SYSTEM_FIELDS_DENYLIST:
            dropped.append(k)
            continue
        if k not in allowed:
            dropped.append(k)
            continue
        safe[k] = v

    # Layer system fields. These MUST go last so they win over anything
    # a user-controlled spread might have placed in safe earlier.
    when = now or datetime.now()
    safe["created_by_id"] = user_id
    safe["last_modified_by_id"] = user_id
    safe["created_date"] = when
    safe["last_modified_date"] = when

    if extra_system_fields:
        # The caller knows what it's doing — typically a legitimate
        # ownership transfer that needs to set owner_id.
        safe.update(extra_system_fields)

    if dropped:
        # Log so monitoring catches probing — repeated drops on the
        # same endpoint indicate an attacker exploring the schema.
        logger.info(
            "sanitize_create_payload: dropped %d disallowed key(s)",
            len(dropped),
            extra={
                "schema": schema,
                "object_name": object_name,
                "dropped_keys": sorted(dropped)[:20],
            },
        )

    return safe, dropped


def sanitize_update_payload(
    payload: dict,
    *,
    schema: str,
    object_name: str,
    user_id: Optional[str] = None,
    extra_system_fields: Optional[dict] = None,
    now: Optional[Any] = None,
) -> tuple[dict, list[str]]:
    """Like :func:`sanitize_create_payload` but for PATCH/UPDATE flows.

    Differences from create:
      * Doesn't set ``created_*`` system fields.
      * ``last_modified_by_id`` / ``last_modified_date`` are layered
        with the current user / timestamp.
    """
    from datetime import datetime

    if not isinstance(payload, dict):
        return {}, []

    allowed = get_allowed_create_fields(schema, object_name)

    dropped: list[str] = []
    safe: dict = {}
    for k, v in payload.items():
        if k in SYSTEM_FIELDS_DENYLIST:
            dropped.append(k)
            continue
        if k not in allowed:
            dropped.append(k)
            continue
        safe[k] = v

    when = now or datetime.now()
    safe["last_modified_by_id"] = user_id
    safe["last_modified_date"] = when

    if extra_system_fields:
        safe.update(extra_system_fields)

    if dropped:
        logger.info(
            "sanitize_update_payload: dropped %d disallowed key(s)",
            len(dropped),
            extra={
                "schema": schema,
                "object_name": object_name,
                "dropped_keys": sorted(dropped)[:20],
            },
        )

    return safe, dropped
