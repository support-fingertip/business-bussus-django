"""Unit tests for ``api.security.schema_authority``.

These tests stub the database layer (via ``patch_resolve_tenant``) and
focus on the contract the dispatcher relies on:

  - ``pin_request_tenant`` writes ``tenant_schema`` / ``tenant_org_id``
    / ``tenant_profile_id`` onto the request.
  - ``assert_pinned_schema`` raises when a downstream caller passes a
    schema that doesn't match the pinned one (enforce mode), and only
    logs in soak mode.
  - ``TenantViolation`` propagates as a ``PermissionError``.
"""

from __future__ import annotations

import pytest

from api.security.schema_authority import (
    TenantContext,
    TenantViolation,
    assert_pinned_schema,
    pin_request_tenant,
)


pytestmark = pytest.mark.unit


def _make_ctx(schema: str = "tenant_alpha") -> TenantContext:
    return TenantContext(
        org_id="org_alpha_0000",
        schema=schema,
        profile_id="prf_alpha_0001",
    )


class TestPinRequestTenant:
    def test_writes_canonical_attributes(self, stub_request, patch_resolve_tenant):
        patch_resolve_tenant.return_value = _make_ctx()
        ctx = pin_request_tenant(
            stub_request,
            user_id="usr_alpha_0001",
            asserted_org_id="org_alpha_0000",
            asserted_schema="tenant_alpha",
            asserted_profile_id="prf_alpha_0001",
        )
        assert ctx.schema == "tenant_alpha"
        assert stub_request.tenant_schema == "tenant_alpha"
        assert stub_request.tenant_org_id == "org_alpha_0000"
        assert stub_request.tenant_profile_id == "prf_alpha_0001"

    def test_propagates_violation_as_permission_error(
        self, stub_request, patch_resolve_tenant
    ):
        patch_resolve_tenant.side_effect = TenantViolation("schema mismatch")
        with pytest.raises(PermissionError):
            pin_request_tenant(
                stub_request,
                user_id="usr_alpha_0001",
                asserted_org_id="org_beta_0000",
                asserted_schema="tenant_beta",
                asserted_profile_id="prf_beta_0001",
            )


class TestAssertPinnedSchema:
    def test_returns_pinned_when_kwarg_matches(self, stub_request):
        stub_request.tenant_schema = "tenant_alpha"
        out = assert_pinned_schema(stub_request, "tenant_alpha")
        assert out == "tenant_alpha"

    def test_raises_in_enforce_mode_on_mismatch(self, stub_request, monkeypatch):
        monkeypatch.setenv("SCHEMA_AUTHORITY_ENFORCE", "1")
        stub_request.tenant_schema = "tenant_alpha"
        with pytest.raises(TenantViolation):
            assert_pinned_schema(stub_request, "tenant_beta")

    def test_logs_only_in_soak_mode(self, stub_request, monkeypatch, caplog):
        monkeypatch.setenv("SCHEMA_AUTHORITY_ENFORCE", "0")
        stub_request.tenant_schema = "tenant_alpha"
        with caplog.at_level("WARNING", logger="api.security.schema_authority"):
            out = assert_pinned_schema(stub_request, "tenant_beta")
        assert out == "tenant_alpha"
        assert any("log-only mode" in r.message for r in caplog.records)

    def test_no_pinned_schema_passes_through(self, stub_request):
        # Background task / system call: nothing pinned, return whatever
        # caller passed.
        assert assert_pinned_schema(stub_request, "tenant_alpha") == "tenant_alpha"
        assert assert_pinned_schema(stub_request, None) is None
