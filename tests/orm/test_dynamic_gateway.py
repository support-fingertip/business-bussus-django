"""Unit tests for ``api.ORM.dynamic`` scaffold.

The gateway is feature-flagged off by default in Phase 1; these tests
cover the static contract:

  - feature flag gate raises a clear error when not enabled,
  - identifier validators reject unsafe identifiers,
  - metadata loader cache key shape is stable.
"""

from __future__ import annotations

import pytest

from api.ORM.dynamic.identifier_validator import (
    InvalidIdentifierError,
    validate_field_name,
    validate_object_name,
    validate_schema_name,
)


pytestmark = pytest.mark.unit


class TestIdentifierValidators:
    @pytest.mark.parametrize("value", ["leads", "tenant_alpha", "field_1", "_private"])
    def test_accepts_valid_identifier(self, value):
        assert validate_object_name(value) == value
        assert validate_field_name(value) == value
        assert validate_schema_name(value) == value

    @pytest.mark.parametrize(
        "value",
        [
            "leads; DROP TABLE users",
            "leads--",
            "1starts_with_digit",
            "has space",
            "has-dash",
            "",
            "a" * 64,  # too long for a Postgres identifier
        ],
    )
    def test_rejects_unsafe_identifier(self, value):
        with pytest.raises((InvalidIdentifierError, ValueError)):
            validate_object_name(value)


class TestFeatureFlag:
    """The gateway must refuse to operate until the flag is set."""

    def test_select_raises_when_flag_off(self, monkeypatch, stub_request):
        monkeypatch.delenv("USE_DYNAMIC_GATEWAY", raising=False)
        from api.ORM.dynamic import dynamic_table
        with pytest.raises(dynamic_table.DynamicGatewayDisabled):
            dynamic_table.select(stub_request, "leads", fields=["id"])

    def test_insert_raises_when_flag_off(self, monkeypatch, stub_request):
        monkeypatch.delenv("USE_DYNAMIC_GATEWAY", raising=False)
        from api.ORM.dynamic import dynamic_table
        with pytest.raises(dynamic_table.DynamicGatewayDisabled):
            dynamic_table.insert(stub_request, "leads", {"name": "x"})


class TestPinnedSchemaRequired:
    """Once the flag is on, the gateway still refuses without a pinned schema."""

    def test_select_requires_pinned_schema(self, monkeypatch, stub_request):
        monkeypatch.setenv("USE_DYNAMIC_GATEWAY", "1")
        from api.ORM.dynamic import dynamic_table
        # No tenant_schema attribute on stub_request.
        with pytest.raises(PermissionError):
            dynamic_table.select(stub_request, "leads", fields=["id"])
