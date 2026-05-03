"""Schema authority — multi-tenant boundary enforcement.

Single source of truth for ``which schema does this request operate in``.

The platform is multi-tenant via Postgres schemas: every tenant
(organization) gets its own schema name stored in
``public.organizations.database_schema``. Pre-Phase-1 the schema travelled
through every BL/ORM call as ``kwargs.get('schema')`` — caller-supplied,
trusted blindly. A forged JWT or a spoofed kwarg could route a query into
another tenant's data.

This module fixes that with two primitives:

  1. ``resolve_tenant`` — given an authenticated user + JWT-asserted
     org/profile, look up the canonical schema in the database and verify
     that the user actually belongs to that org. Raises ``TenantViolation``
     on any inconsistency.

  2. ``pin_request_tenant(request)`` — runs once per request as part of
     ``_init_request_context``. Sets ``request.tenant_schema`` (the only
     trusted source going forward), ``request.tenant_org_id``, and
     ``request.tenant_profile_id``. After this point, EVERY downstream
     layer reads from ``request.tenant_schema`` and ignores any
     ``schema`` value found in kwargs.

In a follow-up commit we'll add a guard that raises if any layer tries
to override the pinned schema. For now the contract is documented and
the middleware logs (but does not yet block) violations so the team can
audit the call-graph during the rollout window.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

from django.db import connection

from api.ORM.sqlFunctions.utils.helpers import validate_identifier

logger = logging.getLogger(__name__)


class TenantViolation(PermissionError):
    """Raised when the schema/org/profile triple cannot be reconciled."""


@dataclass(frozen=True)
class TenantContext:
    org_id: str
    schema: str
    profile_id: Optional[str]


_PUBLIC_SCHEMA = "public"


def _safe_log_extra(**fields):
    """Drop None values so structured-log backends don't choke on nulls."""
    return {k: v for k, v in fields.items() if v is not None}


def resolve_tenant(
    user_id: str,
    asserted_org_id: Optional[str],
    asserted_schema: Optional[str],
    asserted_profile_id: Optional[str],
) -> TenantContext:
    """Verify that the user's claimed org/schema/profile match the database.

    The JWT may carry the org id, the schema, and the profile id. None of
    those values are trusted on their own — we always reconcile against:
      - ``public.users.organization_id`` for the user
      - ``public.organizations.database_schema`` for the org
      - ``<schema>.profile`` for the profile

    Returns a frozen ``TenantContext`` carrying the canonical values.
    Raises ``TenantViolation`` on any mismatch.
    """
    if not user_id:
        raise TenantViolation("Authenticated user is required to resolve tenant.")

    with connection.cursor() as cur:
        cur.execute("SET search_path TO %s", [_PUBLIC_SCHEMA])
        cur.execute(
            "SELECT organization_id FROM users WHERE id = %s",
            [user_id],
        )
        row = cur.fetchone()
        if not row or not row[0]:
            raise TenantViolation("User has no associated organization.")
        canonical_org_id = row[0]

        # Cross-org JWT replay: someone swapped the org id in the token.
        if asserted_org_id and str(asserted_org_id) != str(canonical_org_id):
            logger.warning(
                "Tenant violation: org_id mismatch",
                extra=_safe_log_extra(
                    user_id=user_id,
                    asserted_org_id=asserted_org_id,
                    canonical_org_id=canonical_org_id,
                ),
            )
            raise TenantViolation("Authentication context does not match user.")

        cur.execute(
            "SELECT database_schema FROM organizations "
            "WHERE id = %s AND is_active = TRUE",
            [canonical_org_id],
        )
        row = cur.fetchone()
        if not row or not row[0]:
            raise TenantViolation("Organization is inactive or has no schema.")
        canonical_schema = row[0]

        # Format check: schema is going to be used as a SQL identifier.
        # Reject anything that isn't a valid identifier rather than
        # leaving the validation to ad-hoc callers.
        validate_identifier(canonical_schema, "schema")

        if asserted_schema and asserted_schema != canonical_schema:
            logger.warning(
                "Tenant violation: schema mismatch",
                extra=_safe_log_extra(
                    user_id=user_id,
                    asserted_schema=asserted_schema,
                    canonical_schema=canonical_schema,
                ),
            )
            raise TenantViolation("Authentication context does not match user.")

        # Profile check: profile_id (if asserted) must exist in this tenant's
        # schema. A forged JWT bearing another tenant's profile_id would slip
        # past authentication but fail this reconciliation.
        canonical_profile_id: Optional[str] = None
        if asserted_profile_id:
            cur.execute("SET search_path TO %s", [canonical_schema])
            cur.execute(
                "SELECT id FROM profile WHERE id = %s",
                [asserted_profile_id],
            )
            row = cur.fetchone()
            if not row:
                logger.warning(
                    "Tenant violation: profile_id not in tenant schema",
                    extra=_safe_log_extra(
                        user_id=user_id,
                        asserted_profile_id=asserted_profile_id,
                        canonical_schema=canonical_schema,
                    ),
                )
                raise TenantViolation("Profile is not part of this organization.")
            canonical_profile_id = row[0]

    return TenantContext(
        org_id=str(canonical_org_id),
        schema=canonical_schema,
        profile_id=canonical_profile_id,
    )


def pin_request_tenant(
    request,
    *,
    user_id: str,
    asserted_org_id: Optional[str],
    asserted_schema: Optional[str],
    asserted_profile_id: Optional[str],
) -> TenantContext:
    """Resolve and attach the tenant context to ``request``.

    After this returns successfully:
      - ``request.tenant_schema`` holds the canonical schema
      - ``request.tenant_org_id`` holds the canonical org id
      - ``request.tenant_profile_id`` holds the canonical profile id (or None)

    These attributes are the ONLY trusted source going forward. Layers that
    still read ``kwargs.get('schema')`` should be migrated to
    ``request.tenant_schema``.
    """
    ctx = resolve_tenant(
        user_id=user_id,
        asserted_org_id=asserted_org_id,
        asserted_schema=asserted_schema,
        asserted_profile_id=asserted_profile_id,
    )
    request.tenant_schema = ctx.schema
    request.tenant_org_id = ctx.org_id
    request.tenant_profile_id = ctx.profile_id

    # Make the canonical IDs visible to every log line emitted under this
    # request (and any background work spawned with the same contextvars).
    try:
        from api.security.correlation import set_tenant_id, set_user_id
        set_tenant_id(ctx.org_id)
        set_user_id(user_id)
    except Exception:
        # Logging context is best-effort — never let it break tenant pinning.
        pass

    return ctx


def assert_pinned_schema(request, schema: Optional[str]) -> str:
    """Raise if ``schema`` doesn't match the pinned tenant.

    Use this from any layer that still receives a ``schema`` kwarg as a
    transitional safety net during the migration window. In log-only mode
    (``SCHEMA_AUTHORITY_ENFORCE=0``) the mismatch is recorded but the
    request is allowed to proceed using the pinned value.
    """
    pinned = getattr(request, "tenant_schema", None)
    if pinned is None:
        # Request never went through pin_request_tenant — likely a code path
        # that doesn't authenticate (background task, system call). Don't
        # raise; just return whatever the caller asked for.
        return schema  # type: ignore[return-value]

    if schema and schema != pinned:
        msg = (
            f"Schema authority violation: caller passed schema={schema!r} "
            f"but tenant is pinned to {pinned!r}"
        )
        if os.getenv("SCHEMA_AUTHORITY_ENFORCE", "1") != "0":
            logger.error(msg, extra=_safe_log_extra(
                pinned=pinned,
                attempted=schema,
                user_id=getattr(request, "user_", {}).get("id")
                if isinstance(getattr(request, "user_", None), dict) else None,
            ))
            raise TenantViolation("Cross-tenant access is not permitted.")
        logger.warning(
            "%s (log-only mode; SCHEMA_AUTHORITY_ENFORCE=0)", msg,
            extra=_safe_log_extra(pinned=pinned, attempted=schema),
        )
    return pinned
