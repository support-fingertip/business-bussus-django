"""TenantSchemaMiddleware — make Django's ORM tenant-aware.

In plain English
----------------

Every authenticated request needs the database connection to know
which tenant it's serving. Two pieces:

  1. ``search_path`` tells Postgres where to look for unqualified
     table names (e.g. ``SELECT * FROM profile`` should resolve to
     ``tenant_acme.profile``, not ``public.profile``).

  2. ``SET LOCAL ROLE tenant_<schema>_role`` (Phase 4 part 1) makes
     the *database* enforce isolation. Even if a buggy view or
     forgotten Celery task tries to query another tenant's data,
     Postgres refuses with ``permission denied``.

Both run together in ``process_view`` after Phase 1's
``schema_authority.pin_request_tenant`` has reconciled the JWT against
the database and set ``request.tenant_schema``. On the way out, both
are reset in ``process_response`` so the next request that picks up
the same pooled connection starts clean.

Why ``SET LOCAL`` and not ``SET``
---------------------------------

``SET LOCAL`` is bounded to the current transaction. With
``ATOMIC_REQUESTS = True`` in settings, Django wraps each view in a
transaction, so ``SET LOCAL`` automatically resets when the request
ends. Even if our ``process_response`` reset is skipped (e.g. due to
an exception), the role and search_path revert to the connection's
defaults on transaction end.

Defence in depth — every layer matters
--------------------------------------

This middleware is layer 4 (database enforcement) in the five-layer
isolation contract documented in
``docs/security/isolation_contract.md``. Layer 4 is the *load-bearing*
layer: even if layers 1-3 (auth, application, ORM) have bugs, layer
4 still refuses cross-tenant queries at the database level.

Tolerating ungraduated tenants
------------------------------

During the Phase 4 rollout, not every tenant will have their role
provisioned yet. If ``SET LOCAL ROLE`` fails because the role doesn't
exist, we fall back to ``SET search_path`` only (the old behaviour)
and log a WARNING. The ``ENFORCE_TENANT_ROLE`` env var (default 0)
flips this to a hard failure once every tenant has been provisioned.
"""

from __future__ import annotations

import logging
import os

from django.db import connection
from django.utils.deprecation import MiddlewareMixin

from api.ORM.sqlFunctions.utils.helpers import validate_identifier

logger = logging.getLogger(__name__)


# When True, refuse to serve a request if SET LOCAL ROLE fails. Off by
# default during the rollout window so an un-provisioned tenant doesn't
# 500. Flip to True (``ENFORCE_TENANT_ROLE=1``) once every prod tenant
# has been provisioned via ``manage.py provision_tenant_role --all``.
ENFORCE_TENANT_ROLE = os.getenv("ENFORCE_TENANT_ROLE", "0") == "1"


class TenantSchemaMiddleware(MiddlewareMixin):
    """Apply ``SET search_path`` + ``SET LOCAL ROLE`` per request."""

    def process_view(self, request, view_func, view_args, view_kwargs):
        schema = getattr(request, "tenant_schema", None)
        if not schema:
            # Either an unauthenticated route (health probes), a public
            # endpoint, or schema_authority hasn't run yet for this view.
            # Either way, don't change the connection state.
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

        # The role name follows the convention from
        # ``scripts/per_tenant_ddl/provision_tenant_role.sql``. We
        # also validate_identifier the combined string so a downstream
        # bug in schema validation can't ride in.
        role_name = f"tenant_{schema}_role"
        try:
            validate_identifier(role_name, "role_name")
        except ValueError:
            logger.error(
                "TenantSchemaMiddleware: refusing invalid role name",
                extra={"role_name": role_name, "path": request.path},
            )
            return None

        try:
            with connection.cursor() as cur:
                # Always include `public` as a fallback so any cross-tenant
                # references (e.g. shared lookup tables) keep working.
                cur.execute("SET LOCAL search_path TO %s, public", [schema])
                request._tenant_search_path_set = True

                # Phase 4 part 2: pin the current org id as a session
                # variable so Row-Level Security policies on the shared
                # public tables (organizations, users, user_login_history,
                # session_log, lead_capture) can use it as the predicate:
                #
                #   USING (organization_id = current_setting('app.current_org_id'))
                #
                # The value comes from request.tenant_org_id which
                # schema_authority.pin_request_tenant set after
                # reconciling the JWT against the DB. Falls back to
                # the schema name if tenant_org_id isn't populated
                # (older code paths) — in that case the policy returns
                # 0 rows because no row will match a schema-name value
                # in the organization_id column. Fail-closed.
                org_id_for_rls = (
                    getattr(request, "tenant_org_id", None)
                    or schema
                )
                cur.execute(
                    "SET LOCAL app.current_org_id = %s",
                    [str(org_id_for_rls)],
                )
                request._tenant_org_id_set = True

                # Phase 4 part 1: also assume the per-tenant role. ``SET LOCAL
                # ROLE`` requires the application's main role to be
                # GRANTed membership in tenant_<schema>_role; that
                # grant lives in provision_tenant_role.sql.
                try:
                    cur.execute(
                        "SET LOCAL ROLE %s",
                        [role_name],
                    )
                    request._tenant_role_set = True
                except Exception as exc:
                    # The most common reason this fails during rollout:
                    # the tenant's role hasn't been provisioned yet.
                    # In log-only mode we proceed (with just the
                    # search_path set). In enforce mode we refuse.
                    if ENFORCE_TENANT_ROLE:
                        logger.error(
                            "TenantSchemaMiddleware: SET LOCAL ROLE failed; "
                            "refusing request (ENFORCE_TENANT_ROLE=1)",
                            extra={
                                "schema": schema,
                                "role_name": role_name,
                                "path": request.path,
                                "exc": str(exc),
                            },
                        )
                        from rest_framework.response import Response
                        return Response(
                            {"message": "Tenant not fully provisioned. Contact support."},
                            status=503,
                        )
                    logger.warning(
                        "TenantSchemaMiddleware: SET LOCAL ROLE failed; "
                        "proceeding with search_path-only enforcement",
                        extra={
                            "schema": schema,
                            "role_name": role_name,
                            "path": request.path,
                            "exc": str(exc),
                        },
                    )
        except Exception as exc:
            logger.warning(
                "TenantSchemaMiddleware: SET search_path failed: %s", exc
            )
        return None

    def process_response(self, request, response):
        """Reset connection state so the next pooled request starts clean.

        With ATOMIC_REQUESTS=True (recommended for Phase 4), the
        ``SET LOCAL`` statements automatically reset on transaction
        end. This reset is belt-and-suspenders for the case where
        the request didn't run in a transaction (e.g. some
        background-task entry points).
        """
        if (
            getattr(request, "_tenant_role_set", False)
            or getattr(request, "_tenant_org_id_set", False)
            or getattr(request, "_tenant_search_path_set", False)
        ):
            try:
                with connection.cursor() as cur:
                    # RESET ROLE returns to the connection's session role
                    # (the main application role).
                    cur.execute("RESET ROLE")
                    # Clear the RLS-keyed setting so a pooled connection
                    # picked up by the next request doesn't inherit an
                    # org id from us.
                    cur.execute("RESET app.current_org_id")
                    cur.execute("SET search_path TO public")
            except Exception:
                # Connection pool will close / recycle on its own if
                # the reset failed; don't fail the response over it.
                pass
        return response
