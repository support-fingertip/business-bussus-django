"""Tests for the object-name allowlist used by the dispatcher."""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.unit


class TestIsAllowed:
    def test_reserved_route_passes(self, monkeypatch):
        from api.security import object_whitelist as ow
        # Stub the metadata loader so this test stays pure-unit.
        monkeypatch.setattr(ow, "list_business_objects", lambda schema: ())
        assert ow.is_allowed("home", "tenant_alpha")
        assert ow.is_allowed("listview", "tenant_alpha")
        assert ow.is_allowed("report", "tenant_alpha")

    def test_registered_business_object_passes(self, monkeypatch):
        from api.security import object_whitelist as ow
        monkeypatch.setattr(
            ow, "list_business_objects", lambda schema: ("leads", "accounts")
        )
        assert ow.is_allowed("leads", "tenant_alpha")
        assert ow.is_allowed("accounts", "tenant_alpha")

    def test_unknown_name_rejected(self, monkeypatch):
        from api.security import object_whitelist as ow
        monkeypatch.setattr(ow, "list_business_objects", lambda schema: ("leads",))
        assert not ow.is_allowed("nonexistent", "tenant_alpha")
        assert not ow.is_allowed("", "tenant_alpha")
        assert not ow.is_allowed(None, "tenant_alpha")

    def test_metadata_failure_fails_open_with_log(self, monkeypatch, caplog):
        from api.security import object_whitelist as ow

        def boom(schema):
            raise RuntimeError("loader explodes")

        monkeypatch.setattr(ow, "list_business_objects", boom)
        with caplog.at_level("ERROR", logger="api.security.object_whitelist"):
            # Must fail open so a metadata blip doesn't 404 the world.
            assert ow.is_allowed("anything", "tenant_alpha") is True
        assert any("metadata lookup failed" in r.message for r in caplog.records)


class TestAssertAllowed:
    def test_raises_for_unknown(self, monkeypatch):
        from api.security import object_whitelist as ow
        monkeypatch.setattr(ow, "list_business_objects", lambda schema: ("leads",))
        with pytest.raises(ow.ObjectNotAllowed):
            ow.assert_allowed("evil", "tenant_alpha")

    def test_silent_for_known(self, monkeypatch):
        from api.security import object_whitelist as ow
        monkeypatch.setattr(ow, "list_business_objects", lambda schema: ("leads",))
        ow.assert_allowed("leads", "tenant_alpha")
        ow.assert_allowed("home", "tenant_alpha")  # reserved route
