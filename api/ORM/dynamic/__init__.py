"""Dynamic-object gateway.

Custom business objects (setup=FALSE rows in the ``object`` registry) have
schemas defined at runtime by the metadata layer (``object``, ``fields``).
Their physical tables can't be represented as static Django models, so
they need raw SQL — but every BL/permissions/cursor.execute callsite
that builds that SQL is a potential injection point.

This package consolidates that work behind one tight interface so:
  - identifier validation runs in exactly one place,
  - schema authority is enforced (the gateway always reads
    ``request.tenant_schema``, never a kwarg),
  - psycopg2.sql composables are the only SQL primitive used,
  - per-tenant metadata is cached with explicit invalidation hooks,
  - future hardening (statement timeouts, pagination caps, retries)
    drops in once instead of seventy times.

Usage (Phase 1 scaffold — wired into BL behind a feature flag in Phase 2):

    from api.ORM.dynamic import dynamic_table

    rows = dynamic_table.select(request, "leads",
                                fields=["id", "name", "phone"],
                                where=[("owner_id", "=", user_id)])
    dynamic_table.insert(request, "leads", {"name": "Acme", ...})
    dynamic_table.update(request, "leads", record_id="abc", patch={...})
    dynamic_table.delete(request, "leads", record_ids=["abc"])

The gateway is intentionally narrow. Anything that doesn't fit
(complex joins, aggregates, formula evaluation) lives at a higher layer
and uses the gateway for the leaf reads/writes.
"""

from api.ORM.dynamic import dynamic_table  # noqa: F401
from api.ORM.dynamic import metadata_loader  # noqa: F401
from api.ORM.dynamic.identifier_validator import (  # noqa: F401
    InvalidIdentifierError,
    validate_object_name,
    validate_field_name,
    validate_schema_name,
)
