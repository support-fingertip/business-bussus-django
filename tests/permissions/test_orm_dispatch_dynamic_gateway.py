"""Phase 4.B wave 1 — dispatch wiring for the dynamic-object gateway.

Wave 1 converts the DELETE primitive (``deleteSQLFunction.delete_data_sql``)
to dual-path behind the new ``USE_DYNAMIC_GATEWAY`` flag. UPDATE /
INSERT / SELECT come in later waves (4.B.2-4).

These tests verify:

  * the dispatch primitive's ``flag`` keyword accepts the new flag
    name with the same independence guarantees as Phase 2.B and
    Phase 3.C
  * the public ``delete_data_sql`` routes to the legacy raw impl
    when ``USE_DYNAMIC_GATEWAY`` is unset, and to the gateway-backed
    impl when set
  * arguments are forwarded unchanged to the chosen impl
  * the public function preserves its return shape across both paths

Pure unit tests — the underlying ``_delete_data_raw`` and
``_delete_data_orm`` helpers are monkey-patched. Behavioural parity
(both paths producing identical effects against a real schema)
belongs in the staging soak — see ``docs/PHASE4_B_OPERATOR_NOTES.md``.
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
# Dispatch primitive — USE_DYNAMIC_GATEWAY independence
# ---------------------------------------------------------------------------


class TestDispatchHonoursDynamicGatewayFlag:
    def test_named_flag_routes_to_orm(self, monkeypatch):
        from api.permissions._orm_dispatch import dispatch
        monkeypatch.setenv("USE_DYNAMIC_GATEWAY", "1")
        monkeypatch.delenv("USE_ORM_FOR_PERMISSIONS", raising=False)
        monkeypatch.delenv("USE_ORM_FOR_BL", raising=False)
        raw = MagicMock(return_value="raw")
        orm = MagicMock(return_value="orm")
        result = dispatch("test", raw, orm, flag="USE_DYNAMIC_GATEWAY")
        assert result == "orm"
        orm.assert_called_once()
        raw.assert_not_called()

    def test_named_flag_routes_to_raw_when_only_other_flags_set(self, monkeypatch):
        """Setting USE_ORM_FOR_BL=1 must NOT enable USE_DYNAMIC_GATEWAY."""
        from api.permissions._orm_dispatch import dispatch
        monkeypatch.setenv("USE_ORM_FOR_BL", "1")
        monkeypatch.setenv("USE_ORM_FOR_PERMISSIONS", "1")
        monkeypatch.delenv("USE_DYNAMIC_GATEWAY", raising=False)
        raw = MagicMock(return_value="raw")
        orm = MagicMock(return_value="orm")
        result = dispatch("test", raw, orm, flag="USE_DYNAMIC_GATEWAY")
        assert result == "raw"
        raw.assert_called_once()
        orm.assert_not_called()

    def test_is_orm_enabled_with_dynamic_gateway_flag(self, monkeypatch):
        from api.permissions._orm_dispatch import is_orm_enabled
        monkeypatch.setenv("USE_DYNAMIC_GATEWAY", "1")
        monkeypatch.delenv("USE_ORM_FOR_PERMISSIONS", raising=False)
        monkeypatch.delenv("USE_ORM_FOR_BL", raising=False)
        assert is_orm_enabled("USE_DYNAMIC_GATEWAY") is True
        assert is_orm_enabled() is False  # default flag unaffected
        assert is_orm_enabled("USE_ORM_FOR_BL") is False


# ---------------------------------------------------------------------------
# delete_data_sql — public function dispatch wiring
# ---------------------------------------------------------------------------


class TestDeleteDataSqlDispatch:
    def test_raw_path_when_flag_off(self, monkeypatch):
        _ensure_django()
        from api.ORM.sqlFunctions import deleteSQLFunction as mod

        captured = {}

        def fake_raw(object_name, id_list, section, permanent, schema, user):
            captured["impl"] = "raw"
            captured["args"] = (object_name, list(id_list), section, permanent, schema, user)
            return {"success": True, "message": "Deleted 1 record(s)."}

        def fake_orm(*args, **kwargs):
            captured["impl"] = "orm"
            return {"success": True, "message": "should not run"}

        monkeypatch.setattr(mod, "_delete_data_raw", fake_raw)
        monkeypatch.setattr(mod, "_delete_data_orm", fake_orm)
        monkeypatch.delenv("USE_DYNAMIC_GATEWAY", raising=False)
        monkeypatch.setattr(mod, "validate_identifier", lambda *a, **kw: None)
        monkeypatch.setattr(mod, "get_validated_schema", lambda kw: "tenant_alpha")

        result = mod.delete_data_sql(
            "leads", ["lead_001"], section=None, permanent=False,
            user_={"id": "usr_001"},
        )

        assert captured["impl"] == "raw"
        assert captured["args"] == (
            "leads", ["lead_001"], None, False, "tenant_alpha", {"id": "usr_001"},
        )
        assert result == {"success": True, "message": "Deleted 1 record(s)."}

    def test_orm_path_when_flag_on(self, monkeypatch):
        _ensure_django()
        from api.ORM.sqlFunctions import deleteSQLFunction as mod

        captured = {}

        def fake_raw(*args, **kwargs):
            captured["impl"] = "raw"
            return {"success": True, "message": "should not run"}

        def fake_orm(object_name, id_list, section, permanent, schema, user):
            captured["impl"] = "orm"
            captured["args"] = (object_name, list(id_list), section, permanent, schema, user)
            return {"success": True, "message": "Deleted 2 record(s)."}

        monkeypatch.setattr(mod, "_delete_data_raw", fake_raw)
        monkeypatch.setattr(mod, "_delete_data_orm", fake_orm)
        monkeypatch.setenv("USE_DYNAMIC_GATEWAY", "1")
        monkeypatch.setattr(mod, "validate_identifier", lambda *a, **kw: None)
        monkeypatch.setattr(mod, "get_validated_schema", lambda kw: "tenant_alpha")

        result = mod.delete_data_sql(
            "leads", ["lead_001", "lead_002"],
            permanent=True, user_={"id": "usr_001"},
        )

        assert captured["impl"] == "orm"
        assert captured["args"] == (
            "leads", ["lead_001", "lead_002"], None, True, "tenant_alpha", {"id": "usr_001"},
        )
        assert result == {"success": True, "message": "Deleted 2 record(s)."}

    def test_missing_schema_raises_before_dispatch(self, monkeypatch):
        _ensure_django()
        from api.ORM.sqlFunctions import deleteSQLFunction as mod

        called = {"raw": 0, "orm": 0}
        monkeypatch.setattr(mod, "_delete_data_raw",
                            lambda *a, **kw: called.__setitem__("raw", called["raw"] + 1))
        monkeypatch.setattr(mod, "_delete_data_orm",
                            lambda *a, **kw: called.__setitem__("orm", called["orm"] + 1))
        monkeypatch.setattr(mod, "get_validated_schema", lambda kw: "")

        with pytest.raises(Exception, match="schema"):
            mod.delete_data_sql("leads", ["lead_001"])

        assert called == {"raw": 0, "orm": 0}


# ---------------------------------------------------------------------------
# _resolve_actor_id — input shape adapter
# ---------------------------------------------------------------------------


class TestResolveActorId:
    def test_dict_user(self):
        _ensure_django()
        from api.ORM.sqlFunctions.deleteSQLFunction import _resolve_actor_id
        assert _resolve_actor_id({"id": "usr_001"}) == "usr_001"

    def test_object_user(self):
        _ensure_django()
        from types import SimpleNamespace
        from api.ORM.sqlFunctions.deleteSQLFunction import _resolve_actor_id
        assert _resolve_actor_id(SimpleNamespace(id="usr_002")) == "usr_002"

    def test_none_user(self):
        _ensure_django()
        from api.ORM.sqlFunctions.deleteSQLFunction import _resolve_actor_id
        assert _resolve_actor_id(None) is None

    def test_dict_without_id_key(self):
        _ensure_django()
        from api.ORM.sqlFunctions.deleteSQLFunction import _resolve_actor_id
        assert _resolve_actor_id({}) is None
