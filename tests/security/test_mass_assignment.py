"""Mass-assignment whitelist tests — Phase 8.A8.

The audit graded the ``{**create_data, ...}`` pattern HIGH because it
let a user inject ``id``, ``owner_id``, ``organization_id``,
``is_deleted`` and other system fields into a model insert. This
branch adds :mod:`api.BL.allowed_fields` to filter every payload to
the per-tenant allow-list and layer system fields on top so a user
can't supply them.

These tests pin the fix in place. Every classic mass-assignment
payload below MUST be filtered before any SQL is built.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

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


def _fake_cursor(rows):
    """Mock the information_schema/fields-table fetch result."""
    cur = MagicMock()
    cur.fetchall.return_value = [(r,) for r in rows]
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=cur)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


@pytest.fixture(autouse=True)
def _clear_cache():
    _ensure_django()
    from api.BL.allowed_fields import invalidate_all
    invalidate_all()
    yield
    invalidate_all()


class TestSystemDenylist:
    """System fields are never user-supplyable, regardless of metadata."""

    @pytest.mark.parametrize("denied", [
        "id",
        "created_by_id",
        "created_date",
        "last_modified_by_id",
        "last_modified_date",
        "deleted_by_id",
        "deleted_date",
        "is_deleted",
        "organization_id",
        "tenant_id",
        "owner_id",
    ])
    def test_denied_fields_dropped_even_if_in_metadata(self, denied):
        from api.BL.allowed_fields import sanitize_create_payload

        # Mock the metadata fetch to (incorrectly) report the denied
        # field as modifiable. The denylist should win anyway.
        with patch("api.BL.allowed_fields.connection") as fake_conn:
            fake_conn.cursor.return_value = _fake_cursor(
                ["name", "status", denied]
            )

            payload = {"name": "X", "status": "Open", denied: "ATTACKER"}
            safe, dropped = sanitize_create_payload(
                payload,
                schema="tenant_alpha",
                object_name="task",
                user_id="user_legit",
            )

            assert denied in dropped, (
                f"{denied} should have been dropped, but wasn't"
            )
            # If denied is one of the system fields the sanitiser layers on
            # top (created_by_id, etc.), the value in `safe` must be the
            # platform's value, not the attacker's.
            if denied == "created_by_id":
                assert safe["created_by_id"] == "user_legit"
            elif denied == "last_modified_by_id":
                assert safe["last_modified_by_id"] == "user_legit"
            else:
                # For non-layered denials (id, owner_id, etc.) the key
                # must be ABSENT from the safe payload entirely.
                assert denied not in safe or safe[denied] != "ATTACKER"


class TestAllowList:
    """Only fields present in the per-tenant metadata pass through."""

    def test_allowed_fields_survive(self):
        from api.BL.allowed_fields import sanitize_create_payload

        with patch("api.BL.allowed_fields.connection") as fake_conn:
            fake_conn.cursor.return_value = _fake_cursor(
                ["subject", "due_date", "status", "assigned_to_id"]
            )
            payload = {
                "subject": "Follow up",
                "due_date": "2026-06-01",
                "status": "Open",
                "assigned_to_id": "user_alice",
            }
            safe, dropped = sanitize_create_payload(
                payload, schema="tenant_alpha", object_name="task",
                user_id="user_legit",
            )

            for k, v in payload.items():
                assert safe[k] == v, f"{k} should have survived"
            assert dropped == []

    def test_unknown_keys_dropped(self):
        from api.BL.allowed_fields import sanitize_create_payload

        with patch("api.BL.allowed_fields.connection") as fake_conn:
            fake_conn.cursor.return_value = _fake_cursor(["subject", "status"])

            payload = {
                "subject": "OK",
                "status": "Open",
                "secret_admin_flag": True,         # not on allow-list
                "internal_priority": 9001,         # not on allow-list
            }
            safe, dropped = sanitize_create_payload(
                payload, schema="tenant_alpha", object_name="task",
                user_id="user_legit",
            )

            assert "secret_admin_flag" in dropped
            assert "internal_priority" in dropped
            assert "secret_admin_flag" not in safe
            assert "internal_priority" not in safe

    def test_empty_allowlist_drops_everything(self):
        """If metadata can't be loaded (DB blip), every user-supplied
        field is dropped. System fields are still layered on. Better
        to insert an empty record than to let unverified data through."""
        from api.BL.allowed_fields import sanitize_create_payload

        with patch("api.BL.allowed_fields.connection") as fake_conn:
            fake_conn.cursor.side_effect = RuntimeError("DB down")

            payload = {"subject": "X", "status": "Open"}
            safe, dropped = sanitize_create_payload(
                payload, schema="tenant_alpha", object_name="task",
                user_id="user_legit",
            )

            assert "subject" in dropped
            assert "status" in dropped


class TestSystemFieldLayering:
    """The platform's system fields must win over anything the user supplied."""

    def test_created_by_id_always_from_platform(self):
        from api.BL.allowed_fields import sanitize_create_payload

        with patch("api.BL.allowed_fields.connection") as fake_conn:
            fake_conn.cursor.return_value = _fake_cursor(["subject"])

            payload = {
                "subject": "Hi",
                "created_by_id": "user_attacker",   # attacker tries to spoof
            }
            safe, dropped = sanitize_create_payload(
                payload, schema="tenant_alpha", object_name="task",
                user_id="user_legit",
            )

            assert safe["created_by_id"] == "user_legit"
            assert "created_by_id" in dropped

    def test_extra_system_fields_can_be_set_by_caller(self):
        """A caller with a legitimate reason (ownership transfer) can
        supply system fields via extra_system_fields — bypasses the
        denylist intentionally."""
        from api.BL.allowed_fields import sanitize_create_payload

        with patch("api.BL.allowed_fields.connection") as fake_conn:
            fake_conn.cursor.return_value = _fake_cursor(["subject"])

            payload = {"subject": "Hi"}
            safe, _ = sanitize_create_payload(
                payload, schema="tenant_alpha", object_name="task",
                user_id="user_legit",
                extra_system_fields={"owner_id": "user_assigned_owner"},
            )

            assert safe["owner_id"] == "user_assigned_owner"


class TestClassicAttackPayloads:
    """End-to-end with classic mass-assignment payloads from the OWASP cheat sheet."""

    @pytest.mark.parametrize("attack_key,attack_value", [
        ("id", "rec_takeover_001"),                      # collision with existing row
        ("owner_id", "user_attacker"),                   # ownership grab
        ("organization_id", "org_victim"),               # cross-tenant
        ("is_deleted", False),                           # undelete
        ("is_staff", True),                              # privilege escalation
        ("is_superuser", True),                          # same
        ("created_by_id", "user_attacker"),              # audit-log spoof
    ])
    def test_attack_payload_neutralised(self, attack_key, attack_value):
        from api.BL.allowed_fields import sanitize_create_payload

        with patch("api.BL.allowed_fields.connection") as fake_conn:
            fake_conn.cursor.return_value = _fake_cursor(
                ["subject", "status", "assigned_to_id"]
            )

            payload = {
                "subject": "Looks legit",
                "status": "Open",
                attack_key: attack_value,
            }
            safe, dropped = sanitize_create_payload(
                payload, schema="tenant_alpha", object_name="task",
                user_id="user_legit",
            )

            # The attack key was dropped (either because it's on the
            # denylist or because it's not on the allow-list).
            assert attack_key in dropped, (
                f"{attack_key}={attack_value!r} not dropped: safe={safe!r}"
            )
            # If the attack key has a system-field equivalent, the safe
            # payload has the platform's value, not the attacker's.
            if attack_key in ("created_by_id", "last_modified_by_id"):
                assert safe[attack_key] == "user_legit"


class TestUpdatePayloadSanitiser:
    def test_update_doesnt_set_created_fields(self):
        from api.BL.allowed_fields import sanitize_update_payload

        with patch("api.BL.allowed_fields.connection") as fake_conn:
            fake_conn.cursor.return_value = _fake_cursor(["subject", "status"])

            payload = {"subject": "Edited", "status": "Closed"}
            safe, _ = sanitize_update_payload(
                payload, schema="tenant_alpha", object_name="task",
                user_id="user_legit",
            )

            # Update should NOT touch created_* fields.
            assert "created_by_id" not in safe
            assert "created_date" not in safe
            # But should set last_modified_*.
            assert safe["last_modified_by_id"] == "user_legit"
            assert "last_modified_date" in safe

    def test_update_drops_attempt_to_change_id(self):
        from api.BL.allowed_fields import sanitize_update_payload

        with patch("api.BL.allowed_fields.connection") as fake_conn:
            fake_conn.cursor.return_value = _fake_cursor(["subject"])

            payload = {"subject": "Edited", "id": "rec_takeover"}
            safe, dropped = sanitize_update_payload(
                payload, schema="tenant_alpha", object_name="task",
                user_id="user_legit",
            )

            assert "id" in dropped
            assert "id" not in safe
