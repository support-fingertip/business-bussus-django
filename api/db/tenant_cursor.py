"""Tenant-aware raw-SQL cursor — the ONLY sanctioned way to execute raw
SQL in tenant-scoped code paths.

Why this exists
---------------

`docs/security/isolation_contract.md` (L3) requires that every raw-SQL
call site verify, at the moment it runs, that the connection is pinned
to the expected tenant. The plain `django.db.connection.cursor()`
returns whatever state the connection happens to be in — usually fine,
occasionally not (a missed `with_tenant_schema()` in a Celery task, a
forgotten `RESET ROLE` in middleware, a connection-pool reuse). One
slip and a raw query lands in `public` or the wrong tenant.

`tenant_cursor(ctx)` closes that gap by re-asserting the contract on
every call:

  1. The caller must pass an explicit :class:`TenantContext`.
  2. Before yielding the cursor, the helper verifies that the
     connection's ``search_path`` includes the expected schema.
  3. (Future, Phase 4) it will also verify ``current_role`` and
     ``app.current_org_id``.

If any assertion fails, the helper raises ``TenantContextMismatch``
*before* any SQL leaves the app. The query never executes against the
wrong tenant.

This module is **append-only** for now: it adds the safe primitive,
without removing access to the raw `connection.cursor()`. The Semgrep
rule in `.semgrep/tenant_isolation.yml` is what gradually deprecates
the direct usage as Phase 5 migrates call sites over.

Usage
-----

    from api.db.tenant_cursor import tenant_cursor
    from api.security.schema_authority import TenantContext

    ctx = TenantContext(org_id="acme", schema="tenant_acme", profile_id=None)
    with tenant_cursor(ctx) as cur:
        cur.execute("SELECT id, name FROM leads WHERE owner_id = %s", [user_id])
        rows = cur.fetchall()

Background tasks: the standard pattern is to open `with_tenant_schema(ctx.schema)`
first (which pins the search_path) and then use `tenant_cursor(ctx)`
to re-verify before any raw SQL.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Iterator, TYPE_CHECKING

from django.db import connection

if TYPE_CHECKING:
    from api.security.schema_authority import TenantContext

logger = logging.getLogger(__name__)


class TenantContextMissing(RuntimeError):
    """Raised when tenant_cursor is called without a TenantContext."""


class TenantContextMismatch(PermissionError):
    """Raised when the DB connection state doesn't match the asserted tenant.

    Subclasses PermissionError so the dispatcher's existing 403 handler
    converts it to a refusal at the HTTP layer.
    """


@contextlib.contextmanager
def tenant_cursor(ctx: "TenantContext | None") -> Iterator:
    """Yield a raw cursor after verifying it points at ``ctx``'s tenant.

    Raises
    ------
    TenantContextMissing
        If ``ctx`` is ``None`` or missing a schema.
    TenantContextMismatch
        If the connection's ``search_path`` does not contain
        ``ctx.schema``. This catches both (a) a missed
        ``with_tenant_schema`` call earlier in the call chain and
        (b) a pool-reuse case where the connection still carries
        another tenant's state.
    """
    if ctx is None or not getattr(ctx, "schema", None):
        raise TenantContextMissing(
            "tenant_cursor requires a TenantContext with a non-empty schema. "
            "Call this from a request handler after pin_request_tenant has "
            "run, or from a background task wrapped in with_tenant_schema()."
        )

    with connection.cursor() as cur:
        # Verify the connection is pinned where the caller expects.
        # `current_setting('search_path')` returns the comma-separated
        # list; we just need the tenant schema to appear in it.
        cur.execute("SHOW search_path")
        row = cur.fetchone()
        search_path = (row[0] if row else "") or ""
        if ctx.schema not in search_path:
            logger.error(
                "tenant_cursor: search_path mismatch",
                extra={
                    "expected_schema": ctx.schema,
                    "actual_search_path": search_path,
                    "org_id": getattr(ctx, "org_id", None),
                },
            )
            raise TenantContextMismatch(
                "Database connection is not pinned to the expected tenant. "
                "Refusing to execute raw SQL."
            )

        # All checks passed — yield the verified cursor. The caller
        # uses it like a normal Django cursor.
        yield cur
