"""Phase 3.C wave 2 — dispatch wiring for the BL files unblocked by Phase 3.B.

Three new conversion sites land in this branch, each gated behind the
``USE_ORM_FOR_BL`` flag:

  * ``api/permissions/FetchUsers/fetch_shared_records.py``
        → ``SharedRecord`` (Phase 3.B Wave 8)
  * ``api/emailsend/views.py``
        → ``EmailTemplate`` (Phase 3 Wave 5) +
          ``EmailProviderSetup`` (Phase 3.B Wave 6)
  * ``api/telephony/views.py`` (the bare ``FROM landing_numbers`` query)
        → ``LandingNumber`` (Phase 3.B Wave 6)

These tests verify the *dispatch wiring* — that the public function picks
the correct underlying impl based on the flag and forwards arguments
without mutation. They are pure unit tests (no DB) — the underlying
``_*_raw`` and ``_*_orm`` helpers are monkey-patched.

Behavioural parity (raw vs ORM returning the same data against a real
schema) belongs in the staging soak — see
``docs/PHASE3_C_WAVE2_OPERATOR_NOTES.md``.

Each test calls ``pytest.importorskip('django')`` and ``django.setup()``
because the converted modules import Django at module top — without that
the tests fail to import in stripped CI environments.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

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


# ---------------------------------------------------------------------------
# fetch_shared_records — SharedRecord ORM
# ---------------------------------------------------------------------------


class TestFetchSharedRecordsDispatch:
    def test_raw_path_when_bl_flag_off(self, monkeypatch):
        _ensure_django()
        from api.permissions.FetchUsers import fetch_shared_records as mod

        raw = MagicMock(return_value=[{"record_id": "r1", "owner_id": "o1", "access_type": "read"}])
        orm = MagicMock(return_value=[])
        monkeypatch.setattr(mod, "_fetch_shared_records_raw", raw)
        monkeypatch.setattr(mod, "_fetch_shared_records_orm", orm)
        monkeypatch.delenv("USE_ORM_FOR_BL", raising=False)

        result = mod.fetch_shared_records("u1", "Account", "tenant_alpha", type="read")

        assert result == [{"record_id": "r1", "owner_id": "o1", "access_type": "read"}]
        raw.assert_called_once()
        orm.assert_not_called()

    def test_orm_path_when_bl_flag_on(self, monkeypatch):
        _ensure_django()
        from api.permissions.FetchUsers import fetch_shared_records as mod

        raw = MagicMock(return_value=[])
        orm = MagicMock(return_value=[{"record_id": "r2", "owner_id": "o2", "access_type": "read/write"}])
        monkeypatch.setattr(mod, "_fetch_shared_records_raw", raw)
        monkeypatch.setattr(mod, "_fetch_shared_records_orm", orm)
        monkeypatch.setenv("USE_ORM_FOR_BL", "1")

        result = mod.fetch_shared_records("u1", "Account", "tenant_alpha", type="read")

        assert result == [{"record_id": "r2", "owner_id": "o2", "access_type": "read/write"}]
        orm.assert_called_once()
        raw.assert_not_called()

    def test_combined_mask_built_from_type_string(self):
        """``read/write`` should compute mask=3 (1 read | 2 write)."""
        _ensure_django()
        from api.permissions.FetchUsers.fetch_shared_records import _build_combined_mask
        assert _build_combined_mask("read") == 1
        assert _build_combined_mask("write") == 2
        assert _build_combined_mask("delete") == 4
        assert _build_combined_mask("share") == 8
        assert _build_combined_mask("read/write") == 3
        assert _build_combined_mask("read/write/delete/share") == 15
        # Unknown -> default to read.
        assert _build_combined_mask("unknown") == 1
        assert _build_combined_mask("") == 1


# ---------------------------------------------------------------------------
# emailsend/views.py — EmailTemplate + EmailProviderSetup ORM
# ---------------------------------------------------------------------------


class TestEmailsendDispatch:
    def test_get_sendgrid_template_id_routes_via_flag(self, monkeypatch):
        _ensure_django()
        from api.emailsend import views as mod

        raw = MagicMock(return_value="raw_id")
        orm = MagicMock(return_value="orm_id")
        monkeypatch.setattr(mod, "_sendgrid_template_id_raw", raw)
        monkeypatch.setattr(mod, "_sendgrid_template_id_orm", orm)

        monkeypatch.delenv("USE_ORM_FOR_BL", raising=False)
        assert mod.get_sendgrid_template_id_from_db("hash1") == "raw_id"

        monkeypatch.setenv("USE_ORM_FOR_BL", "1")
        assert mod.get_sendgrid_template_id_from_db("hash1") == "orm_id"

    def test_save_sendgrid_template_id_routes_via_flag(self, monkeypatch):
        _ensure_django()
        from api.emailsend import views as mod

        raw = MagicMock()
        orm = MagicMock()
        monkeypatch.setattr(mod, "_save_sendgrid_template_id_raw", raw)
        monkeypatch.setattr(mod, "_save_sendgrid_template_id_orm", orm)

        monkeypatch.delenv("USE_ORM_FOR_BL", raising=False)
        mod.save_sendgrid_template_id_to_db("hash1", "tpl_1")
        raw.assert_called_once_with("hash1", "tpl_1")
        orm.assert_not_called()

        raw.reset_mock(); orm.reset_mock()

        monkeypatch.setenv("USE_ORM_FOR_BL", "1")
        mod.save_sendgrid_template_id_to_db("hash1", "tpl_1")
        orm.assert_called_once_with("hash1", "tpl_1")
        raw.assert_not_called()

    def test_get_user_email_provider_routes_via_flag(self, monkeypatch):
        _ensure_django()
        from api.emailsend import views as mod

        raw = MagicMock(return_value="gmail")
        orm = MagicMock(return_value="outlook")
        monkeypatch.setattr(mod, "_user_email_provider_raw", raw)
        monkeypatch.setattr(mod, "_user_email_provider_orm", orm)

        monkeypatch.delenv("USE_ORM_FOR_BL", raising=False)
        assert mod.get_user_email_provider("user1") == "gmail"

        monkeypatch.setenv("USE_ORM_FOR_BL", "1")
        assert mod.get_user_email_provider("user1") == "outlook"

    def test_get_user_email_provider_raises_when_unset(self, monkeypatch):
        """If neither path returns a provider the function must raise — the
        original behaviour callers depend on for fallback handling."""
        _ensure_django()
        from api.emailsend import views as mod

        monkeypatch.setattr(mod, "_user_email_provider_raw", lambda u: None)
        monkeypatch.setattr(mod, "_user_email_provider_orm", lambda u: None)

        monkeypatch.delenv("USE_ORM_FOR_BL", raising=False)
        with pytest.raises(Exception, match="Email provider not configured"):
            mod.get_user_email_provider("user1")

        monkeypatch.setenv("USE_ORM_FOR_BL", "1")
        with pytest.raises(Exception, match="Email provider not configured"):
            mod.get_user_email_provider("user1")


# ---------------------------------------------------------------------------
# telephony/views.py — LandingNumber ORM
# ---------------------------------------------------------------------------


class TestTelephonyLandingNumberLookup:
    def test_raw_path_returns_run_query_shape(self, monkeypatch):
        """Raw helper must return ``run_query``'s list-of-dicts shape so
        ``result[0]['group_id']`` keeps working in ``telephony_route``."""
        _ensure_django()
        from api.telephony import views as mod

        captured = {}

        def fake_run_query(sql, params):
            captured["sql"] = sql
            captured["params"] = params
            return [{"group_id": "g1", "routing_logic": "round_robin"}]

        monkeypatch.setattr(mod, "run_query", fake_run_query)

        result = mod._landing_number_lookup_raw("tel_1", "+15551234567")
        assert result == [{"group_id": "g1", "routing_logic": "round_robin"}]
        assert captured["params"] == ["tel_1", "+15551234567"]
        assert "FROM landing_numbers" in captured["sql"]
        assert "telephony_id=%s" in captured["sql"]
        assert "landing_number=%s" in captured["sql"]

    def test_orm_path_returns_list_of_one_dict_when_match(self, monkeypatch):
        """ORM helper must wrap the .first() row in a list to match
        ``run_query``'s shape (the legacy callsite indexes ``result[0]``)."""
        _ensure_django()
        from api.telephony import views as mod
        from api.tenant_models import LandingNumber

        fake_qs = MagicMock()
        fake_qs.filter.return_value = fake_qs
        fake_qs.values.return_value = fake_qs
        fake_qs.first.return_value = {"group_id": "g1", "routing_logic": "round_robin"}
        monkeypatch.setattr(LandingNumber, "objects", fake_qs)

        result = mod._landing_number_lookup_orm("tel_1", "+15551234567")
        assert result == [{"group_id": "g1", "routing_logic": "round_robin"}]
        fake_qs.filter.assert_called_once_with(
            telephony_id="tel_1", landing_number="+15551234567"
        )
        fake_qs.values.assert_called_once_with("group_id", "routing_logic")

    def test_orm_path_returns_empty_list_when_no_match(self, monkeypatch):
        _ensure_django()
        from api.telephony import views as mod
        from api.tenant_models import LandingNumber

        fake_qs = MagicMock()
        fake_qs.filter.return_value = fake_qs
        fake_qs.values.return_value = fake_qs
        fake_qs.first.return_value = None
        monkeypatch.setattr(LandingNumber, "objects", fake_qs)

        assert mod._landing_number_lookup_orm("tel_1", "+15551234567") == []
