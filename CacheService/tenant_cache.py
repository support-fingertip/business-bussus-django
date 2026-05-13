"""Tenant-aware Redis cache wrapper — Phase 7 foundation.

Why this exists
---------------

Redis is shared across all tenants in this deployment. The existing
``CacheService.cache.build_key`` helper already prefixes keys with a
``schema`` segment when callers remember to pass it — but that's a
politeness, not a guarantee. Forgetting the schema produces a key
in the global namespace; two tenants can then collide.

``tenant_cache`` enforces tenant scoping at the API:

  * Every operation requires an explicit :class:`TenantContext`.
  * Keys are always prefixed ``tenant:<org_id>:<key>``.
  * There is no way to read/write outside the tenant namespace from
    this module — callers that need cross-tenant cache use the raw
    cache directly (rare, and code-reviewable).

Phase 7 makes :func:`tenant_get` / :func:`tenant_set` / :func:`tenant_delete`
the only sanctioned cache API for tenant-scoped code paths. The
Semgrep rule ``forbid-untenanted-cache`` (added separately, Phase 5
infrastructure) flags raw ``cache.get`` / ``cache.set`` usage in
tenant-aware files so the migration is mechanical.

Usage
-----

    from CacheService.tenant_cache import tenant_get, tenant_set, tenant_delete

    tenant_set(ctx, "user_perms", perms_dict, timeout=300)
    perms = tenant_get(ctx, "user_perms")
    tenant_delete(ctx, "user_perms")

Tenant offboarding
------------------

When a tenant is offboarded, :func:`purge_tenant` wipes every key
under their namespace in one shot. Hooked into the offboarding
runbook (``docs/runbooks/tenant_offboard.md``).
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional, TYPE_CHECKING

from django.core.cache import cache

if TYPE_CHECKING:
    from api.security.schema_authority import TenantContext

logger = logging.getLogger(__name__)


NAMESPACE_PREFIX = "tenant"  # Final key: ``tenant:<org_id>:<key>``


class TenantContextMissing(RuntimeError):
    """A tenant_cache operation was called without a TenantContext."""


def _require_ctx(ctx: "TenantContext | None") -> str:
    """Return the org_id from ``ctx`` or raise.

    Centralised guard so every public function fails consistently.
    """
    if ctx is None or not getattr(ctx, "org_id", None):
        raise TenantContextMissing(
            "tenant_cache operations require a TenantContext with a non-empty "
            "org_id. From request handlers, use request.tenant_ctx; from "
            "background tasks, the TenantRequiredTask base injects one."
        )
    return ctx.org_id


def _build_key(org_id: str, key: str) -> str:
    """Build the namespaced cache key.

    Format: ``tenant:<org_id>:<key>``.

    Never include arbitrary user input in ``key`` without sanitisation
    — Redis-compatible keys forbid newlines, but a malicious key
    could still inject delimiters. Callers building keys from user
    input should hash or sanitize first.
    """
    if not key:
        raise ValueError("tenant_cache: key must be non-empty")
    return f"{NAMESPACE_PREFIX}:{org_id}:{key}"


def tenant_get(ctx: "TenantContext | None", key: str, default: Any = None) -> Any:
    """Tenant-scoped ``cache.get`` — namespaces key under the org."""
    org_id = _require_ctx(ctx)
    return cache.get(_build_key(org_id, key), default)


def tenant_set(
    ctx: "TenantContext | None",
    key: str,
    value: Any,
    timeout: Optional[int] = None,
) -> None:
    """Tenant-scoped ``cache.set`` — namespaces key under the org."""
    org_id = _require_ctx(ctx)
    cache.set(_build_key(org_id, key), value, timeout=timeout)


def tenant_delete(ctx: "TenantContext | None", key: str) -> None:
    """Tenant-scoped ``cache.delete`` — namespaces key under the org."""
    org_id = _require_ctx(ctx)
    cache.delete(_build_key(org_id, key))


def tenant_get_many(
    ctx: "TenantContext | None", keys: Iterable[str]
) -> dict[str, Any]:
    """Tenant-scoped multi-get — returns a dict keyed by the original (un-namespaced) keys."""
    org_id = _require_ctx(ctx)
    namespaced = {k: _build_key(org_id, k) for k in keys}
    raw = cache.get_many(list(namespaced.values()))
    return {orig: raw[ns_key] for orig, ns_key in namespaced.items() if ns_key in raw}


def purge_tenant(ctx: "TenantContext | None") -> int:
    """Wipe every cache key in this tenant's namespace.

    Returns the number of keys deleted (best-effort — the underlying
    backend may not support exact counts).

    Used by the tenant-offboarding runbook. Requires a Redis backend
    that supports key scanning (``django-redis`` does by default).
    """
    org_id = _require_ctx(ctx)
    pattern = f"{NAMESPACE_PREFIX}:{org_id}:*"
    try:
        # django-redis exposes delete_pattern; other backends do not.
        # If your backend doesn't support it, fall back to scanning.
        delete_pattern = getattr(cache, "delete_pattern", None)
        if delete_pattern is not None:
            return int(delete_pattern(pattern) or 0)
        # Fallback: iter_keys + delete one-by-one (slow, but correct).
        iter_keys = getattr(cache, "iter_keys", None)
        if iter_keys is None:
            logger.warning(
                "purge_tenant: cache backend supports neither delete_pattern "
                "nor iter_keys; cannot purge org_id=%s",
                org_id,
            )
            return 0
        count = 0
        for k in iter_keys(pattern):
            cache.delete(k)
            count += 1
        return count
    except Exception:
        logger.exception("purge_tenant failed for org_id=%s", org_id)
        raise
