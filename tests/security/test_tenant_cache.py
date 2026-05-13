"""Tests for CacheService.tenant_cache — Phase 7.

The wrapper enforces:
  1. Every operation requires a TenantContext with org_id.
  2. Keys are namespaced ``tenant:<org_id>:<key>``.
  3. Operations on tenant A's namespace can't touch tenant B's.
"""

from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import patch

import pytest


pytestmark = pytest.mark.unit


def _ensure_django():
    pytest.importorskip("django")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    try:
        import django
        django.setup()
    except Exception:
        pytest.skip("Django not configured in this environment")


def _ctx(org_id="org_acme"):
    _ensure_django()
    from api.security.schema_authority import TenantContext
    return TenantContext(org_id=org_id, schema=f"tenant_{org_id}", profile_id=None)


class TestRequiresContext:
    """Every operation refuses to run without a usable TenantContext."""

    def test_get_without_ctx_raises(self):
        _ensure_django()
        from CacheService.tenant_cache import tenant_get, TenantContextMissing
        with pytest.raises(TenantContextMissing):
            tenant_get(None, "anykey")

    def test_set_without_ctx_raises(self):
        _ensure_django()
        from CacheService.tenant_cache import tenant_set, TenantContextMissing
        with pytest.raises(TenantContextMissing):
            tenant_set(None, "anykey", "value")

    def test_set_with_ctx_missing_org_id_raises(self):
        _ensure_django()
        from CacheService.tenant_cache import tenant_set, TenantContextMissing
        ctx = SimpleNamespace(org_id="", schema="tenant_x", profile_id=None)
        with pytest.raises(TenantContextMissing):
            tenant_set(ctx, "k", "v")

    def test_empty_key_raises(self):
        _ensure_django()
        from CacheService.tenant_cache import tenant_set
        with pytest.raises(ValueError):
            tenant_set(_ctx(), "", "value")


class TestKeyNamespacing:
    """Verify the wrapper builds the expected ``tenant:<org>:<key>`` keys."""

    def test_namespaced_key_format(self):
        _ensure_django()
        from CacheService.tenant_cache import tenant_set
        ctx = _ctx(org_id="acme")

        with patch("CacheService.tenant_cache.cache") as fake_cache:
            tenant_set(ctx, "user_perms", {"foo": 1}, timeout=60)
            fake_cache.set.assert_called_once_with(
                "tenant:acme:user_perms", {"foo": 1}, timeout=60
            )

    def test_two_tenants_cannot_collide(self):
        _ensure_django()
        from CacheService.tenant_cache import tenant_set, tenant_get
        ctx_a = _ctx(org_id="acme")
        ctx_b = _ctx(org_id="beta")

        with patch("CacheService.tenant_cache.cache") as fake_cache:
            tenant_set(ctx_a, "key", "A")
            tenant_set(ctx_b, "key", "B")

            calls = [c.args[0] for c in fake_cache.set.call_args_list]
            assert calls == ["tenant:acme:key", "tenant:beta:key"]

            # Now verify A's get path produces A's key, not B's.
            tenant_get(ctx_a, "key")
            assert fake_cache.get.call_args.args[0] == "tenant:acme:key"

    def test_get_default_passed_through(self):
        _ensure_django()
        from CacheService.tenant_cache import tenant_get
        with patch("CacheService.tenant_cache.cache") as fake_cache:
            fake_cache.get.return_value = "stub"
            tenant_get(_ctx("acme"), "k", default="dflt")
            fake_cache.get.assert_called_once_with("tenant:acme:k", "dflt")


class TestPurgeTenant:
    """Offboarding wipes the tenant's namespace."""

    def test_purge_uses_delete_pattern_when_available(self):
        _ensure_django()
        from CacheService.tenant_cache import purge_tenant

        with patch("CacheService.tenant_cache.cache") as fake_cache:
            fake_cache.delete_pattern.return_value = 7
            count = purge_tenant(_ctx("acme"))
            assert count == 7
            fake_cache.delete_pattern.assert_called_once_with("tenant:acme:*")
