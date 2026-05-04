"""Unit tests for the Phase 2 permission constants and helpers.

These tests don't touch the database — they validate the pure-Python
contract of constants and helpers introduced/changed in Phase 2:

  - ADMIN_ROLES is a deduped frozenset.
  - VALID_PERMISSION_TYPES rejects everything outside the canonical four.
  - DEFAULT_OBJECT_ACCESS_LEVEL defaults to Private (default-deny).
  - apply_audit_fields force-overwrites client-supplied owner/created_by.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.unit


def test_admin_roles_is_deduped_frozenset():
    from api.permissions.permissions import ADMIN_ROLES
    # frozenset, not a list with the duplicate-superadmin bug
    assert isinstance(ADMIN_ROLES, frozenset)
    # No way to have duplicates in a frozenset, but the canonical members
    # should all be present.
    assert {"admin", "superadmin", "manager",
            "system", "system_administrator"} == set(ADMIN_ROLES)


def test_valid_permission_types_only_canonical_four():
    from api.permissions.permissions import VALID_PERMISSION_TYPES
    assert isinstance(VALID_PERMISSION_TYPES, frozenset)
    assert VALID_PERMISSION_TYPES == frozenset({"read", "write", "edit", "delete"})


def test_default_access_level_is_private():
    from api.permissions.permissions import DEFAULT_OBJECT_ACCESS_LEVEL
    assert DEFAULT_OBJECT_ACCESS_LEVEL == "Private"


class TestApplyAuditFields:
    """Force-overwrite behaviour: caller cannot impersonate another user."""

    def test_create_overwrites_client_owner_id(self):
        from api.permissions.permissions import apply_audit_fields
        data = {
            "name": "Acme",
            # Attacker tries to assign ownership to someone else.
            "owner_id": "victim_user",
            "created_by_id": "victim_user",
            "last_modified_by_id": "victim_user",
        }
        apply_audit_fields(data, mode="create", user_={"id": "real_user"})
        assert data["owner_id"] == "real_user"
        assert data["created_by_id"] == "real_user"
        assert data["last_modified_by_id"] == "real_user"

    def test_update_overwrites_client_last_modified(self):
        from api.permissions.permissions import apply_audit_fields
        data = {"id": "abc", "last_modified_by_id": "victim_user"}
        apply_audit_fields(data, mode="update", user_={"id": "real_user"})
        assert data["last_modified_by_id"] == "real_user"

    def test_create_handles_list_payload(self):
        from api.permissions.permissions import apply_audit_fields
        data = [
            {"name": "A", "owner_id": "victim"},
            {"name": "B"},
        ]
        apply_audit_fields(data, mode="create", user_={"id": "real_user"})
        assert all(row["owner_id"] == "real_user" for row in data)
        assert all(row["created_by_id"] == "real_user" for row in data)

    def test_create_logs_when_clobbering(self, caplog):
        from api.permissions.permissions import apply_audit_fields
        with caplog.at_level("WARNING", logger="api.permissions.permissions"):
            apply_audit_fields(
                {"owner_id": "victim_user"},
                mode="create",
                user_={"id": "real_user"},
            )
        # We log when client-supplied audit fields are dropped.
        assert any(
            "dropping client-supplied audit fields" in r.message
            for r in caplog.records
        )


class TestPermissionTypeWhitelist:
    @pytest.mark.parametrize(
        "bad_type",
        ["", "select", "READ", "drop", "; DROP TABLE", "edit_access"],
    )
    def test_check_permission_rejects_invalid_type(self, monkeypatch, bad_type):
        # We don't need a DB — the whitelist check happens before any
        # cursor work.
        from api.permissions import permissions as perm
        with pytest.raises(ValueError):
            perm.check_permission(
                object_id="oid_1",
                permission_type=bad_type,
                schema="tenant_alpha",
                profile_id="prf_1",
            )

    def test_get_field_metadata_rejects_invalid_access_type(self):
        from api.permissions import permissions as perm
        with pytest.raises(ValueError):
            perm.get_field_metadata(
                object_id="oid_1",
                access_type="HACK",
                schema="tenant_alpha",
                profile_id="prf_1",
            )
