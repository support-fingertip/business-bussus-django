"""Per-tenant whitelist of acceptable object/route names.

The dispatcher accepts arbitrary `<str:object_name>` / `<str:another_object>`
URL captures. Without validation, any authenticated caller can hit
``/v2/api/leads/profile`` or ``/v2/api/anything/object_permissions`` and
probe the metadata tables. The permission layer correctly rejects
unauthorized access, but reaching that layer at all (a) burns DB cycles
and (b) leaks shape information through timing / error messages.

This module provides a small allowlist sourced from two places:

  1. **Static reserved routes** — fixed strings the dispatcher routes on
     for reasons that have nothing to do with the per-tenant object
     registry (``home``, ``listview``, ``report``, ``dashboard``, …).
     These are hard-coded here.

  2. **Per-tenant business objects** — the live ``object`` registry,
     looked up via ``api.ORM.dynamic.metadata_loader.list_business_objects``
     and cached for the request.

Anything that doesn't match one of those buckets is rejected up front
with ``ObjectNotAllowed``, which the dispatcher converts to a 404
(deliberately not 403 — we don't want to confirm whether the table
exists).
"""

from __future__ import annotations

import logging
from typing import Optional

from api.ORM.dynamic.metadata_loader import list_business_objects

logger = logging.getLogger(__name__)


class ObjectNotAllowed(LookupError):
    """Raised when ``object_name`` is not on the per-tenant allowlist."""


# Static dispatcher route names (not real DB tables; the BL layer routes
# on them as commands). Keep this list narrow — every entry is a
# permission-gated entry point.
RESERVED_ROUTES: frozenset[str] = frozenset({
    "home",
    "listview",
    "report",
    "dashboard",
    "setup",
    "preview",
    "page_layout",
    "search_layout",
    "page_builder",
    "object_manager",
    "profile",
    "user",
    "user_group",
    "recycle_bin",
    "global_search",
    "task",
    "whatsapp",
    "send_email",
    "merge_field",
    "field_history",
    "audit_logs",
    "notification",
    "field_tracking",
    "lookup",
    "import",
    "export",
    "field",
    "computed_fields",
    "encrypt",
    "rollup",
    "metadata",
    "tab",
    "app",
    "permissions",
    "role",
    "sharing",
    "owd",
    "workflow",
    "formula",
    "validate_formula",
    "page_component",
    "page_assignment",
    "telephony",
    "call",
})


def is_allowed(name: Optional[str], schema: str) -> bool:
    """Return True iff ``name`` is a known route or business object."""
    if not name:
        return False
    if name in RESERVED_ROUTES:
        return True
    try:
        registered = list_business_objects(schema)
    except Exception as exc:
        # If the metadata loader is broken we'd rather fail open here than
        # 404 every request — log loudly and let the permissions layer
        # reject inappropriate access.
        logger.error(
            "object_whitelist: metadata lookup failed for schema=%s: %s",
            schema, exc,
        )
        return True
    return name in registered


def assert_allowed(name: Optional[str], schema: str, *, kind: str = "object_name") -> None:
    """Raise ``ObjectNotAllowed`` if ``name`` isn't on the allowlist."""
    if not is_allowed(name, schema):
        logger.info(
            "object_whitelist: rejecting unknown name",
            extra={"name": name, "schema": schema, "kind": kind},
        )
        raise ObjectNotAllowed(name)
