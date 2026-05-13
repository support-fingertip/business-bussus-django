"""Shared base class for tenant-scoped models.

Every Wave 2 model:
  - is unmanaged (Django doesn't run DDL),
  - lives in the per-tenant schema (set by TenantSchemaMiddleware),
  - belongs to the ``api`` Django app (per ADR-0001 we don't split apps).

The abstract base centralises ``Meta`` defaults so each model file
stays focused on the table-specific fields.

Tenant-aware manager (Phase 5 foundation)
-----------------------------------------

``TenantModel.objects`` is a :class:`TenantManager` that exposes the
new ``for_tenant(ctx)`` entrypoint. The standard pattern going
forward is::

    Lead.objects.for_tenant(ctx).filter(status="open")

instead of the naked ``Lead.objects.filter(...)`` which relies on
the connection's ``search_path`` being set correctly by middleware.
``for_tenant`` re-verifies that the connection is pinned to the
expected tenant before returning the queryset — exactly the same
guarantee :class:`api.db.tenant_cursor.tenant_cursor` provides for
raw SQL.

Backward compatibility (Phase 5 migration window)
-------------------------------------------------

During the migration window, the legacy ``.objects.filter()`` /
``.objects.all()`` / etc. calls keep working — the manager is a
straight subclass of ``models.Manager`` with no behaviour override
for those methods. ``for_tenant`` is purely additive.

Phase 5 ramps up enforcement in two stages:

  1. **Today (this commit)**: ``for_tenant`` exists and is safe to
     adopt. Semgrep warns on naked ``.objects.*`` calls. Existing
     code keeps working.

  2. **Phase 5 final**: Semgrep escalates to ERROR. Naked manager
     calls fail CI. Every remaining call site has been converted.

This lets us migrate incrementally without breaking the runtime.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import models, connection

if TYPE_CHECKING:
    from api.security.schema_authority import TenantContext

logger = logging.getLogger(__name__)


class TenantContextMissing(RuntimeError):
    """``for_tenant`` was called without a TenantContext."""


class TenantContextMismatch(PermissionError):
    """``for_tenant`` was called against a connection pointing at the wrong tenant."""


class TenantManager(models.Manager):
    """Manager that adds ``for_tenant(ctx)`` — the safe entrypoint.

    Inherits all standard manager methods (``filter``, ``get``,
    ``create``, ``all``, ``count`` …) so existing call sites work
    unchanged. Phase 5 enforces migration via Semgrep, not by
    breaking the manager at runtime.
    """

    def for_tenant(self, ctx: "TenantContext | None"):
        """Return a queryset after verifying the connection is pinned to ``ctx``.

        Raises
        ------
        TenantContextMissing
            ``ctx`` is None or has no schema.
        TenantContextMismatch
            The DB connection's ``search_path`` does not include
            ``ctx.schema`` — middleware did not pin, or the connection
            was returned from a pool with stale state.
        """
        if ctx is None or not getattr(ctx, "schema", None):
            raise TenantContextMissing(
                "Model.objects.for_tenant(ctx) requires a TenantContext with "
                "a non-empty schema. From request handlers, use the context "
                "attached to the request; from background tasks, build one "
                "after with_tenant_schema()."
            )

        # Verify the connection state matches the asserted tenant.
        # Cheap to do here — one round-trip — and catches forgotten
        # middleware OR connection-pool reuse with stale search_path.
        with connection.cursor() as cur:
            cur.execute("SHOW search_path")
            row = cur.fetchone()
            search_path = (row[0] if row else "") or ""

        if ctx.schema not in search_path:
            logger.error(
                "TenantManager.for_tenant: search_path mismatch",
                extra={
                    "expected_schema": ctx.schema,
                    "actual_search_path": search_path,
                    "org_id": getattr(ctx, "org_id", None),
                    "model": self.model.__name__,
                },
            )
            raise TenantContextMismatch(
                f"DB connection not pinned to tenant {ctx.schema!r}. "
                f"Refusing to query {self.model.__name__}."
            )

        return self.get_queryset()


class TenantModel(models.Model):
    """Abstract base — sets ``managed = False`` and ``app_label = 'api'``.

    Subclasses inherit ``TenantManager`` so ``Model.objects.for_tenant(ctx)``
    is available everywhere. Override ``objects`` in a subclass only if
    you need a custom manager — and then make it inherit from
    ``TenantManager`` so ``for_tenant`` remains available.
    """

    objects = TenantManager()

    class Meta:
        abstract = True
        managed = False
        app_label = "api"
