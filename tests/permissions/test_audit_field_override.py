"""Tests for the Phase 2 ``allow_owner_override`` escape hatch on
``apply_audit_fields``.

The escape hatch lets trusted internal flows (data import, owner-
transfer admin, lead conversion handoff) reassign ownership while
keeping the rest of the audit-field guarantee. Three behaviours are
tested:

  1. With ``allow_owner_override=False`` (default), client-supplied
     ``owner_id`` is dropped — same as the Phase 2.A.4 base behaviour.

  2. With ``allow_owner_override=True``:
     - ``owner_id`` is preserved when the caller supplied it,
     - ``created_by_id`` and ``last_modified_by_id`` are still
       force-overwritten,
     - an INFO-level log line records the transfer.

  3. The override flag is keyword-only — can't be smuggled through a
     **kwargs spread that originated from request.data.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.unit


def _user(id_: str) -> dict:
    return {"id": id_}


class TestAllowOwnerOverrideOff:
    """Default behaviour — Phase 2.A.4."""

    def test_drops_caller_owner_id(self):
        from api.permissions.permissions import apply_audit_fields
        data = {"owner_id": "victim", "name": "Acme"}
        apply_audit_fields(data, mode="create", user_=_user("real"))
        assert data["owner_id"] == "real"


class TestAllowOwnerOverrideOn:
    def test_preserves_caller_owner_id(self):
        from api.permissions.permissions import apply_audit_fields
        data = {"owner_id": "transferred_to", "name": "Acme"}
        apply_audit_fields(
            data, mode="create",
            user_=_user("admin"),
            allow_owner_override=True,
        )
        assert data["owner_id"] == "transferred_to"

    def test_still_forces_created_by_and_last_modified(self):
        from api.permissions.permissions import apply_audit_fields
        data = {
            "owner_id": "transferred_to",
            "created_by_id": "fake_admin",
            "last_modified_by_id": "fake_admin",
        }
        apply_audit_fields(
            data, mode="create",
            user_=_user("admin"),
            allow_owner_override=True,
        )
        assert data["owner_id"] == "transferred_to"
        # Audit columns are still server-set.
        assert data["created_by_id"] == "admin"
        assert data["last_modified_by_id"] == "admin"

    def test_logs_info_on_override(self, caplog):
        from api.permissions.permissions import apply_audit_fields
        data = {"owner_id": "new_owner_user"}
        with caplog.at_level("INFO", logger="api.permissions.permissions"):
            apply_audit_fields(
                data, mode="create",
                user_=_user("admin"),
                allow_owner_override=True,
            )
        assert any(
            "admin owner override applied" in r.message
            for r in caplog.records
        )

    def test_no_override_when_owner_id_missing(self):
        from api.permissions.permissions import apply_audit_fields
        data = {"name": "Acme"}  # no owner_id supplied
        apply_audit_fields(
            data, mode="create",
            user_=_user("admin"),
            allow_owner_override=True,
        )
        # Default fills in admin's id.
        assert data["owner_id"] == "admin"


class TestKeywordOnly:
    def test_flag_must_be_kwarg(self):
        """``allow_owner_override`` is keyword-only — passing it as a
        positional arg is a TypeError. Prevents accidental smuggling
        through a generic ``**request_kwargs`` spread."""
        from api.permissions.permissions import apply_audit_fields
        with pytest.raises(TypeError):
            apply_audit_fields({"x": 1}, "create", True)  # type: ignore[arg-type]
