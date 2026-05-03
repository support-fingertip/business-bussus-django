"""Tests for the Phase 2.B feature-flag dispatch.

Two layers of testing:
  1. The `_orm_dispatch.is_orm_enabled / dispatch` helper — pure unit.
  2. The dual-path public functions in `permissions.py` — verify the
     flag routes to the right impl, and that each impl receives the
     same arguments. Regression-style: catches a future refactor that
     accidentally changes the contract on one path.

Both layers stub the actual DB calls (the raw cursor + ORM
querysets) so the suite stays no-DB.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Layer 1 — the dispatch primitive
# ---------------------------------------------------------------------------

class TestIsOrmEnabled:
    @pytest.mark.parametrize("v,expected", [
        ("0", False), ("", False), (None, False),
        ("1", True), ("true", True), ("True", True),
        ("yes", True), ("YES", True), ("on", True),
        ("garbage", False),
    ])
    def test_env_truthiness(self, monkeypatch, v, expected):
        from api.permissions._orm_dispatch import is_orm_enabled
        if v is None:
            monkeypatch.delenv("USE_ORM_FOR_PERMISSIONS", raising=False)
        else:
            monkeypatch.setenv("USE_ORM_FOR_PERMISSIONS", v)
        assert is_orm_enabled() is expected


class TestDispatch:
    def test_routes_to_raw_when_flag_off(self, monkeypatch):
        from api.permissions._orm_dispatch import dispatch
        monkeypatch.delenv("USE_ORM_FOR_PERMISSIONS", raising=False)
        raw = MagicMock(return_value="from_raw")
        orm = MagicMock(return_value="from_orm")
        assert dispatch("x", raw, orm) == "from_raw"
        raw.assert_called_once()
        orm.assert_not_called()

    def test_routes_to_orm_when_flag_on(self, monkeypatch):
        from api.permissions._orm_dispatch import dispatch
        monkeypatch.setenv("USE_ORM_FOR_PERMISSIONS", "1")
        raw = MagicMock(return_value="from_raw")
        orm = MagicMock(return_value="from_orm")
        assert dispatch("x", raw, orm) == "from_orm"
        orm.assert_called_once()
        raw.assert_not_called()


# ---------------------------------------------------------------------------
# Layer 2 — the dual-path public functions
# ---------------------------------------------------------------------------

class TestGetObjectDetailsDualPath:
    """Verify the wrapper invokes the right impl with the right args."""

    def test_raw_path_called_when_flag_off(self, monkeypatch):
        from api.permissions import permissions as perm
        monkeypatch.delenv("USE_ORM_FOR_PERMISSIONS", raising=False)
        raw = MagicMock(return_value=("oid_1", "Lead"))
        orm = MagicMock(return_value=("oid_X", "WrongCallback"))
        monkeypatch.setattr(perm, "_get_object_details_raw", raw)
        monkeypatch.setattr(perm, "_get_object_details_orm", orm)
        result = perm.get_object_details("leads", schema="tenant_alpha")
        assert result == ("oid_1", "Lead")
        raw.assert_called_once_with("leads", "tenant_alpha", False)
        orm.assert_not_called()

    def test_orm_path_called_when_flag_on(self, monkeypatch):
        from api.permissions import permissions as perm
        monkeypatch.setenv("USE_ORM_FOR_PERMISSIONS", "1")
        raw = MagicMock(return_value=("from_raw", "raw"))
        orm = MagicMock(return_value=("oid_orm", "Lead"))
        monkeypatch.setattr(perm, "_get_object_details_raw", raw)
        monkeypatch.setattr(perm, "_get_object_details_orm", orm)
        result = perm.get_object_details("leads", schema="tenant_alpha", include_setup=True)
        assert result == ("oid_orm", "Lead")
        orm.assert_called_once_with("leads", "tenant_alpha", True)
        raw.assert_not_called()


class TestProfileHasAdminAccessDualPath:
    def test_raw_default(self, monkeypatch):
        from api.permissions import permissions as perm
        monkeypatch.delenv("USE_ORM_FOR_PERMISSIONS", raising=False)
        raw = MagicMock(return_value=True)
        orm = MagicMock(return_value=False)
        monkeypatch.setattr(perm, "_profile_has_admin_access_raw", raw)
        monkeypatch.setattr(perm, "_profile_has_admin_access_orm", orm)
        assert perm.profile_has_admin_access("prf_1", "tenant_alpha") is True
        raw.assert_called_once_with("prf_1", "tenant_alpha")
        orm.assert_not_called()

    def test_orm_when_flag_on(self, monkeypatch):
        from api.permissions import permissions as perm
        monkeypatch.setenv("USE_ORM_FOR_PERMISSIONS", "1")
        raw = MagicMock(return_value=True)
        orm = MagicMock(return_value=True)
        monkeypatch.setattr(perm, "_profile_has_admin_access_raw", raw)
        monkeypatch.setattr(perm, "_profile_has_admin_access_orm", orm)
        perm.profile_has_admin_access("prf_1", "tenant_alpha")
        orm.assert_called_once_with("prf_1", "tenant_alpha")
        raw.assert_not_called()


class TestCheckPermissionDualPath:
    def test_invalid_type_rejected_before_dispatch(self, monkeypatch):
        from api.permissions import permissions as perm
        monkeypatch.setenv("USE_ORM_FOR_PERMISSIONS", "1")
        raw = MagicMock()
        orm = MagicMock()
        monkeypatch.setattr(perm, "_check_permission_raw", raw)
        monkeypatch.setattr(perm, "_check_permission_orm", orm)
        with pytest.raises(ValueError, match="Invalid permission_type"):
            perm.check_permission("oid_1", "DROP", schema="t", profile_id="p")
        raw.assert_not_called()
        orm.assert_not_called()

    def test_dispatch_args_match(self, monkeypatch):
        from api.permissions import permissions as perm
        monkeypatch.setenv("USE_ORM_FOR_PERMISSIONS", "1")
        raw = MagicMock(return_value=False)
        orm = MagicMock(return_value=True)
        monkeypatch.setattr(perm, "_check_permission_raw", raw)
        monkeypatch.setattr(perm, "_check_permission_orm", orm)
        result = perm.check_permission(
            "oid_1", "read", schema="tenant_alpha", profile_id="prf_1"
        )
        assert result is True
        orm.assert_called_once_with("oid_1", "read", "tenant_alpha", "prf_1")


class TestGetObjectAccessLevelDualPath:
    """Phase 2.B's new shared helper."""

    def test_returns_none_when_no_record(self, monkeypatch):
        from api.permissions import permissions as perm
        monkeypatch.delenv("USE_ORM_FOR_PERMISSIONS", raising=False)
        raw = MagicMock(return_value=None)
        orm = MagicMock(return_value=None)
        monkeypatch.setattr(perm, "_get_object_access_level_raw", raw)
        monkeypatch.setattr(perm, "_get_object_access_level_orm", orm)
        assert perm.get_object_access_level("oid_1", "tenant_alpha") is None

    def test_returns_access_level_string(self, monkeypatch):
        from api.permissions import permissions as perm
        monkeypatch.setenv("USE_ORM_FOR_PERMISSIONS", "1")
        raw = MagicMock(return_value="should_not_be_called")
        orm = MagicMock(return_value="Public Read Write")
        monkeypatch.setattr(perm, "_get_object_access_level_raw", raw)
        monkeypatch.setattr(perm, "_get_object_access_level_orm", orm)
        assert (
            perm.get_object_access_level("oid_1", "tenant_alpha")
            == "Public Read Write"
        )


class TestGetFieldMetadataDualPath:
    def test_invalid_access_type_rejected_before_dispatch(self, monkeypatch):
        from api.permissions import permissions as perm
        monkeypatch.setenv("USE_ORM_FOR_PERMISSIONS", "1")
        raw = MagicMock()
        orm = MagicMock()
        monkeypatch.setattr(perm, "_field_metadata_rows_raw", raw)
        monkeypatch.setattr(perm, "_field_metadata_rows_orm", orm)
        with pytest.raises(ValueError, match="Invalid access_type"):
            perm.get_field_metadata(
                "oid_1", "DROP", schema="t", profile_id="p"
            )
        raw.assert_not_called()
        orm.assert_not_called()

    def test_post_processing_works_for_both_paths(self, monkeypatch):
        """Verify the get_field_metadata loop builds identical output
        from a tuple — the row format is the contract, not the source."""
        from api.permissions import permissions as perm

        # Two simple field rows: one text, one picklist.
        sample_rows = [
            (
                "first_name", "First Name", "text", False, None,
                None, True, None, False, False, False, None, "John",
                False, False, False, 50, None, None, None, None, None, None,
            ),
            (
                "stage", "Stage", "picklist", True, None,
                ["A", "B"], True, None, False, True, False, None, "B",
                False, False, False, None, None, None, None, None, None, None,
            ),
        ]
        monkeypatch.setenv("USE_ORM_FOR_PERMISSIONS", "1")
        monkeypatch.setattr(
            perm, "_field_metadata_rows_orm",
            lambda *a, **k: sample_rows,
        )
        monkeypatch.setattr(perm, "_perm_cache", lambda r: None)

        permitted, fields_meta = perm.get_field_metadata(
            "oid_1", "read", schema="t", profile_id="p"
        )
        assert permitted == ["first_name", "stage"]
        assert fields_meta[0]["name"] == "first_name"
        assert fields_meta[0]["datatype"] == "text"
        assert fields_meta[1]["name"] == "stage"
        assert fields_meta[1]["values"] == ["A", "B"]
        assert fields_meta[1]["default"] == "B"
