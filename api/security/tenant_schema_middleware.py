"""TenantSchemaMiddleware — make Django's ORM tenant-aware.

Phase 1's ``schema_authority.pin_request_tenant`` writes
``request.tenant_schema`` after reconciling the JWT-claimed org against
the database. That's enough for raw-SQL callers (which read the value
explicitly) but Django's ORM goes through the connection's current
``search_path`` — and Django doesn't change it on its own.

This middleware bridges the two: after schema_authority has run, it
issues ``SET search_path TO <tenant_schema>, public`` on the active
connection so that subsequent ``Profile.objects.get(...)`` / etc.
automatically scope to the right tenant's tables.

Ordering matters. The middleware MUST run AFTER any auth/middleware
that calls pin_request_tenant. Phase 2 wires schema_authority from the
DRF view, so this middleware runs at the start of view dispatch via
``process_view``.

A ``process_response`` hook resets the search_path to ``public`` so
the next caller picking up the same connection from the pool starts
clean.
"""

from __future__ import annotations

import logging

from django.db import connection
from django.utils.deprecation import MiddlewareMixin

from api.ORM.sqlFunctions.utils.helpers import validate_identifier

logger = logging.getLogger(__name__)


class TenantSchemaMiddleware(MiddlewareMixin):
    """Apply ``SET search_path`` per request after schema_authority pins."""

    def process_view(self, request, view_func, view_args, view_kwargs):
        schema = getattr(request, "tenant_schema", None)
        if not schema:
            # Either an unauthenticated route (health probes), a public
            # endpoint, or schema_authority hasn't run yet for this view.
            # Either way, don't change the search_path.
            return None
        try:
            # Defence in depth — schema_authority already validates, but
            # this middleware can be triggered from other call paths.
            validate_identifier(schema, "schema")
        except ValueError:
            logger.error(
                "TenantSchemaMiddleware: refusing invalid schema name",
                extra={"schema": schema, "path": request.path},
            )
            return None
        try:
            with connection.cursor() as cur:
                # Always include `public` as a fallback so any cross-tenant
                # references (e.g. shared lookup tables) keep working.
                cur.execute("SET search_path TO %s, public", [schema])
            request._tenant_search_path_set = True
        except Exception as exc:
            logger.warning(
                "TenantSchemaMiddleware: SET search_path failed: %s", exc
            )
        return None

    def process_response(self, request, response):
        # Reset to a known-clean default so the next request that picks
        # up this connection from the pool doesn't inherit our schema.
        if getattr(request, "_tenant_search_path_set", False):
            try:
                with connection.cursor() as cur:
                    cur.execute("SET search_path TO public")
            except Exception:
                pass
        return response
