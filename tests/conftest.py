"""Shared pytest fixtures for the stabilization-phase test suite.

Phase 1 introduces the ground floor: a tenant-isolation fixture pair
(two distinct schemas with two distinct users), a stub-request factory
that exercises the schema-authority pinning, and a way to run unit
tests that don't need the full Django test database.

Subsequent phases extend this with permission-matrix factories and
fixtures that boot the dynamic-object gateway end-to-end.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# Make the repo importable when invoking pytest from the repo root.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Sane defaults for env-loaded settings; tests must never depend on a
# live Sentry/Voxbay/Voxbay-Webhook configuration.
os.environ.setdefault("DJANGO_ENV", "test")
os.environ.setdefault("DEBUG", "False")
os.environ.setdefault("OAUTH_TOKEN_ENC_KEY", "")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


@pytest.fixture
def stub_request():
    """A bare object that quacks like a Django HttpRequest enough for
    the security/correlation/dispatcher helpers we test in isolation."""
    req = SimpleNamespace()
    req.META = {}
    req.headers = {}
    req.path = "/v2/api/test"
    req.user_ = None
    req.trace_id = None
    return req


@pytest.fixture
def tenant_alpha():
    """First tenant in two-tenant isolation tests."""
    return SimpleNamespace(
        org_id="org_alpha_0000",
        schema="tenant_alpha",
        user_id="usr_alpha_0001",
        profile_id="prf_alpha_0001",
    )


@pytest.fixture
def tenant_beta():
    """Second tenant — used to assert no leakage from alpha → beta."""
    return SimpleNamespace(
        org_id="org_beta_0000",
        schema="tenant_beta",
        user_id="usr_beta_0001",
        profile_id="prf_beta_0001",
    )


@pytest.fixture
def patch_resolve_tenant(monkeypatch):
    """Replace ``schema_authority.resolve_tenant`` with a mock that
    returns whatever the test asks for, so unit tests don't need a real
    database. Returns the mock so the caller can configure return value
    or side effects.
    """
    from api.security import schema_authority

    mock = MagicMock(name="resolve_tenant")
    monkeypatch.setattr(schema_authority, "resolve_tenant", mock)
    return mock
