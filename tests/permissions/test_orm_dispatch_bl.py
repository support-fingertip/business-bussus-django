"""Tests for the Phase 3.C BL dispatch flag.

The dispatch primitive (api.permissions._orm_dispatch) was extended to
accept a per-feature ``flag`` keyword. Phase 2.B uses
``USE_ORM_FOR_PERMISSIONS`` (the default); Phase 3.C BL callers pass
``USE_ORM_FOR_BL``. Each flag is independently togglable so operators
roll out separately.

Tests cover:
  - is_orm_enabled honours the named flag (not just the default).
  - dispatch routes through the named flag exclusively (the other flag
    being on/off has no effect).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


pytestmark = pytest.mark.unit


class TestIsOrmEnabledWithFlag:
    def test_named_flag_only(self, monkeypatch):
        from api.permissions._orm_dispatch import is_orm_enabled
        monkeypatch.setenv("USE_ORM_FOR_BL", "1")
        monkeypatch.delenv("USE_ORM_FOR_PERMISSIONS", raising=False)
        assert is_orm_enabled("USE_ORM_FOR_BL") is True
        # Default flag is unaffected.
        assert is_orm_enabled() is False
        assert is_orm_enabled("USE_ORM_FOR_PERMISSIONS") is False

    def test_default_flag_back_compat(self, monkeypatch):
        """Phase 2.B callers that don't pass `flag` still hit USE_ORM_FOR_PERMISSIONS."""
        from api.permissions._orm_dispatch import is_orm_enabled
        monkeypatch.setenv("USE_ORM_FOR_PERMISSIONS", "1")
        monkeypatch.delenv("USE_ORM_FOR_BL", raising=False)
        assert is_orm_enabled() is True


class TestDispatchPerFlag:
    def test_bl_flag_routes_to_orm_when_only_bl_set(self, monkeypatch):
        from api.permissions._orm_dispatch import dispatch
        monkeypatch.setenv("USE_ORM_FOR_BL", "1")
        monkeypatch.delenv("USE_ORM_FOR_PERMISSIONS", raising=False)
        raw = MagicMock(return_value="raw")
        orm = MagicMock(return_value="orm")
        result = dispatch("x", raw, orm, flag="USE_ORM_FOR_BL")
        assert result == "orm"
        orm.assert_called_once()
        raw.assert_not_called()

    def test_bl_flag_off_routes_to_raw_even_if_perms_on(self, monkeypatch):
        """Flags are independent — turning USE_ORM_FOR_PERMISSIONS on
        does NOT enable USE_ORM_FOR_BL."""
        from api.permissions._orm_dispatch import dispatch
        monkeypatch.setenv("USE_ORM_FOR_PERMISSIONS", "1")
        monkeypatch.delenv("USE_ORM_FOR_BL", raising=False)
        raw = MagicMock(return_value="raw")
        orm = MagicMock(return_value="orm")
        result = dispatch("x", raw, orm, flag="USE_ORM_FOR_BL")
        assert result == "raw"
        raw.assert_called_once()
        orm.assert_not_called()


class TestPageLayoutsUserResolution:
    def test_resolves_to_dict(self, monkeypatch):
        """The PageLayouts user-name resolver should return a {id: name}
        mapping regardless of which path is taken."""
        from api.BL.PageLayouts import page_layout

        sample = {"u1": "Alice", "u2": "Bob"}
        monkeypatch.setattr(
            page_layout, "_resolve_user_names_raw",
            lambda ids, schema: {i: sample[i] for i in ids if i in sample},
        )
        monkeypatch.setattr(
            page_layout, "_resolve_user_names_orm",
            lambda ids, schema: {i: sample[i] for i in ids if i in sample},
        )

        # Both paths should produce the same shape
        monkeypatch.delenv("USE_ORM_FOR_BL", raising=False)
        result = page_layout._resolve_user_names(["u1", "u2"], "tenant_alpha")
        assert result == {"u1": "Alice", "u2": "Bob"}

        monkeypatch.setenv("USE_ORM_FOR_BL", "1")
        result = page_layout._resolve_user_names(["u1", "u2"], "tenant_alpha")
        assert result == {"u1": "Alice", "u2": "Bob"}

    def test_empty_ids_returns_empty_dict(self):
        from api.BL.PageLayouts import page_layout
        assert page_layout._resolve_user_names_raw([], "tenant_alpha") == {}
