"""Tests for ``api.security.schema_authority.get_validated_schema``.

The helper is a thin wrapper over ``assert_pinned_schema`` that pulls
``request`` and ``schema`` out of a kwargs dict — the legacy pattern
used everywhere in BL/permissions/ORM. The wrapper is the migration
seam for the ~140 ``schema = kwargs.get('schema')`` sites the audit
flagged.

Tests cover the four branches the wrapper has to handle:

  1. No request in kwargs (background task, mgmt command) → return
     the kwarg as-is.
  2. Request without ``tenant_schema`` (auth bypassed) → return the
     kwarg as-is.
  3. Request with ``tenant_schema`` and matching kwarg → return the
     pinned value.
  4. Request with ``tenant_schema`` and MISMATCHED kwarg →
     - enforce mode: raise ``TenantViolation``
     - soak mode: log a WARNING, return the pinned value
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


pytestmark = pytest.mark.unit


def _stub_request(tenant_schema=None):
    return SimpleNamespace(tenant_schema=tenant_schema)


class TestGetValidatedSchema:
    def test_no_request_returns_kwarg(self):
        from api.security.schema_authority import get_validated_schema
        assert get_validated_schema({"schema": "tenant_alpha"}) == "tenant_alpha"

    def test_no_kwarg_no_pinned_returns_none(self):
        from api.security.schema_authority import get_validated_schema
        assert get_validated_schema({}) is None

    def test_request_without_pin_returns_kwarg(self):
        from api.security.schema_authority import get_validated_schema
        kwargs = {"request": _stub_request(tenant_schema=None), "schema": "tenant_alpha"}
        assert get_validated_schema(kwargs) == "tenant_alpha"

    def test_kwarg_matches_pinned(self):
        from api.security.schema_authority import get_validated_schema
        kwargs = {
            "request": _stub_request(tenant_schema="tenant_alpha"),
            "schema": "tenant_alpha",
        }
        assert get_validated_schema(kwargs) == "tenant_alpha"

    def test_kwarg_missing_falls_back_to_pinned(self):
        from api.security.schema_authority import get_validated_schema
        kwargs = {"request": _stub_request(tenant_schema="tenant_alpha")}
        assert get_validated_schema(kwargs) == "tenant_alpha"

    def test_mismatch_in_enforce_mode_raises(self, monkeypatch):
        from api.security.schema_authority import (
            TenantViolation,
            get_validated_schema,
        )
        monkeypatch.setenv("SCHEMA_AUTHORITY_ENFORCE", "1")
        kwargs = {
            "request": _stub_request(tenant_schema="tenant_alpha"),
            "schema": "tenant_beta",
        }
        with pytest.raises(TenantViolation):
            get_validated_schema(kwargs)

    def test_mismatch_in_soak_mode_logs(self, monkeypatch, caplog):
        from api.security.schema_authority import get_validated_schema
        monkeypatch.setenv("SCHEMA_AUTHORITY_ENFORCE", "0")
        kwargs = {
            "request": _stub_request(tenant_schema="tenant_alpha"),
            "schema": "tenant_beta",
        }
        with caplog.at_level("WARNING", logger="api.security.schema_authority"):
            result = get_validated_schema(kwargs)
        assert result == "tenant_alpha"
        assert any("log-only mode" in r.message for r in caplog.records)
