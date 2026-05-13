"""Tests for the per-domain handler registry — wave 1 of god-file split.

The registry is the chokepoint that lets blcontroller.py delegate
to per-domain handlers instead of the legacy 5,000-line inline
dispatch. These tests verify:

  * ``register`` decorator wires a class into ``HANDLER_REGISTRY``
    keyed by every name in ``OBJECT_NAMES``
  * ``get_handler`` returns the registered class or ``None``
  * Duplicate registration on the same name raises (so two
    handlers can't silently fight over a domain)
  * ``DomainHandler`` base class returns ``NotImplementedForVerb``
    for every unimplemented verb — the sentinel is recognisable so
    BusinessLogicHandler can fall back to legacy

Pure unit tests — no Django, no DB. The registry import path
chain involves Django (because TaskHandler imports
api.permissions.permissions which imports django.db), so these
tests use ``pytest.importorskip`` and skip cleanly in stripped
environments.
"""

from __future__ import annotations

import os
from types import SimpleNamespace

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


class TestNotImplementedForVerbSentinel:
    """The sentinel must be falsy (so ``if result:`` short-circuits
    naturally) AND identity-comparable to itself — the only way
    callers should ever check for it."""

    def test_is_falsy(self):
        _ensure_django()
        from api.BL.handlers._base import NotImplementedForVerb
        assert not NotImplementedForVerb
        assert bool(NotImplementedForVerb) is False

    def test_repr_is_diagnostic(self):
        _ensure_django()
        from api.BL.handlers._base import NotImplementedForVerb
        assert "NotImplementedForVerb" in repr(NotImplementedForVerb)

    def test_singleton_identity(self):
        """The module-level constant is the only instance callers
        compare against. A second instance compares False to it."""
        _ensure_django()
        from api.BL.handlers._base import NotImplementedForVerb, _NotImplementedForVerb
        other = _NotImplementedForVerb()
        assert NotImplementedForVerb is not other  # different object
        assert other is not NotImplementedForVerb


class TestDomainHandlerBaseReturnsSentinel:
    """Every verb on the base class returns NotImplementedForVerb so
    subclasses inherit that default for verbs they don't override."""

    def test_get_returns_sentinel(self):
        _ensure_django()
        from api.BL.handlers._base import DomainHandler, NotImplementedForVerb
        h = DomainHandler(request=None, object_name="x")
        assert h.get() is NotImplementedForVerb

    def test_post_returns_sentinel(self):
        _ensure_django()
        from api.BL.handlers._base import DomainHandler, NotImplementedForVerb
        h = DomainHandler(request=None, object_name="x")
        assert h.post(data={}) is NotImplementedForVerb

    def test_patch_returns_sentinel(self):
        _ensure_django()
        from api.BL.handlers._base import DomainHandler, NotImplementedForVerb
        h = DomainHandler(request=None, object_name="x")
        assert h.patch(data={}) is NotImplementedForVerb

    def test_delete_returns_sentinel(self):
        _ensure_django()
        from api.BL.handlers._base import DomainHandler, NotImplementedForVerb
        h = DomainHandler(request=None, object_name="x")
        assert h.delete(data={}) is NotImplementedForVerb


class TestRegisterDecorator:
    """``register`` wires the class into the global HANDLER_REGISTRY."""

    def _isolated_registry(self, monkeypatch):
        """Patch HANDLER_REGISTRY to an empty dict for a single test
        so we don't pollute the shared registry."""
        from api.BL.handlers import _base
        empty: dict = {}
        monkeypatch.setattr(_base, "HANDLER_REGISTRY", empty)
        return empty

    def test_decorator_registers_each_object_name(self, monkeypatch):
        _ensure_django()
        registry = self._isolated_registry(monkeypatch)
        from api.BL.handlers._base import DomainHandler, register, get_handler

        @register
        class FooHandler(DomainHandler):
            OBJECT_NAMES = ("foo", "foo_alias")

        assert registry["foo"] is FooHandler
        assert registry["foo_alias"] is FooHandler
        assert get_handler("foo") is FooHandler
        assert get_handler("foo_alias") is FooHandler
        assert get_handler("not-registered") is None

    def test_class_without_object_names_is_rejected(self, monkeypatch):
        _ensure_django()
        self._isolated_registry(monkeypatch)
        from api.BL.handlers._base import DomainHandler, register

        with pytest.raises(TypeError, match="OBJECT_NAMES"):
            @register
            class BadHandler(DomainHandler):
                pass  # no OBJECT_NAMES

    def test_class_with_empty_object_names_is_rejected(self, monkeypatch):
        _ensure_django()
        self._isolated_registry(monkeypatch)
        from api.BL.handlers._base import DomainHandler, register

        with pytest.raises(TypeError, match="OBJECT_NAMES"):
            @register
            class BadHandler(DomainHandler):
                OBJECT_NAMES = ()

    def test_duplicate_registration_raises(self, monkeypatch):
        _ensure_django()
        self._isolated_registry(monkeypatch)
        from api.BL.handlers._base import DomainHandler, register

        @register
        class FirstHandler(DomainHandler):
            OBJECT_NAMES = ("widget",)

        with pytest.raises(RuntimeError, match="Two handlers registered"):
            @register
            class SecondHandler(DomainHandler):
                OBJECT_NAMES = ("widget",)

    def test_re_registering_same_class_is_idempotent(self, monkeypatch):
        _ensure_django()
        self._isolated_registry(monkeypatch)
        from api.BL.handlers._base import DomainHandler, register, get_handler

        @register
        class IdemHandler(DomainHandler):
            OBJECT_NAMES = ("idem",)

        # Re-applying the decorator shouldn't raise — same class.
        register(IdemHandler)
        assert get_handler("idem") is IdemHandler


class TestTaskHandlerRegisteredAtImport:
    """The package __init__ imports task.py, which triggers the
    @register decorator. After importing the package, the registry
    must have ``task`` mapped to TaskHandler."""

    def test_task_is_registered(self):
        _ensure_django()
        from api.BL.handlers import get_handler
        from api.BL.handlers.task import TaskHandler
        assert get_handler("task") is TaskHandler

    def test_task_handler_declares_correct_object_names(self):
        _ensure_django()
        from api.BL.handlers.task import TaskHandler
        assert TaskHandler.OBJECT_NAMES == ("task",)

    def test_task_handler_implements_get_and_patch_not_post_or_delete(self):
        """Wave 1 deliberately doesn't extract Task POST (it's in an
        another_object context) or DELETE (no legacy branch). Verify
        the handler matches that intent — POST/DELETE return the
        sentinel so blcontroller falls back to legacy."""
        _ensure_django()
        from api.BL.handlers._base import NotImplementedForVerb
        from api.BL.handlers.task import TaskHandler

        h = TaskHandler(request=SimpleNamespace(), object_name="task")
        # POST and DELETE come from the base class.
        assert h.post(data={}) is NotImplementedForVerb
        assert h.delete(data={}) is NotImplementedForVerb

        # GET and PATCH are overridden — they don't return the sentinel
        # for normal calls (we verify by checking the methods are
        # overridden, not by calling them, since the GET/PATCH bodies
        # touch the DB).
        from api.BL.handlers._base import DomainHandler
        assert TaskHandler.get is not DomainHandler.get
        assert TaskHandler.patch is not DomainHandler.patch
