"""Unit tests for ``api.ORM.dynamic`` gateway.

Phase 1: scaffold built, feature-flagged off via a self-gate that
raised ``DynamicGatewayDisabled``.

Phase 4.B wave 1: the self-gate is gone — routing happens via
``api.permissions._orm_dispatch`` with ``flag="USE_DYNAMIC_GATEWAY"``.
The gateway is now a regular library; callers reach it through the
dispatch primitive, not directly by env var.

Tests cover:
  - identifier validators (unchanged from Phase 1)
  - ``_resolve_schema`` accepts both request objects and strings
  - missing/empty schema still raises ``PermissionError``
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest


# api.ORM.dynamic re-exports dynamic_table at package import time, which
# imports django.db. Skip the whole module if Django isn't installed in
# this environment (matching the parity-test pattern).
pytest.importorskip("django")
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
try:
    import django
    django.setup()
except Exception:
    pytest.skip("Django not configured in this environment", allow_module_level=True)

from api.ORM.dynamic.identifier_validator import (  # noqa: E402
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


class TestResolveSchema:
    """The Phase 4.B helper accepts either a request or a schema string."""

    def test_accepts_pinned_request(self):
        from api.ORM.dynamic.dynamic_table import _resolve_schema
        req = SimpleNamespace(tenant_schema="tenant_alpha")
        assert _resolve_schema(req) == "tenant_alpha"

    def test_accepts_schema_string(self):
        from api.ORM.dynamic.dynamic_table import _resolve_schema
        assert _resolve_schema("tenant_alpha") == "tenant_alpha"

    def test_rejects_request_with_no_pinned_schema(self):
        from api.ORM.dynamic.dynamic_table import _resolve_schema
        req = SimpleNamespace()  # no tenant_schema attribute
        with pytest.raises(PermissionError, match="pinned tenant schema"):
            _resolve_schema(req)

    def test_rejects_empty_schema_string(self):
        from api.ORM.dynamic.dynamic_table import _resolve_schema
        with pytest.raises(PermissionError, match="empty schema string"):
            _resolve_schema("")
