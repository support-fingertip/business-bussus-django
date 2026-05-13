"""Tests for api.celery_tasks.base — Phase 6.

Verify the TenantRequiredTask base:
  1. Refuses to run without _tenant_ctx.
  2. Refuses to run with a malformed _tenant_ctx.
  3. Reconstructs the TenantContext from the dict form.
  4. Wraps the body in with_tenant_schema.
  5. Drops _tenant_ctx from kwargs before calling the body so
     downstream code doesn't get it as a foreign kwarg.
"""

from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pytest


pytestmark = pytest.mark.unit


def _ensure_django():
    pytest.importorskip("django")
    pytest.importorskip("celery")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    try:
        import django
        django.setup()
    except Exception:
        pytest.skip("Django not configured in this environment")


def _make_task_with_run(run_fn):
    """Build a TenantRequiredTask subclass with a stubbed run()."""
    _ensure_django()
    from api.celery_tasks.base import TenantRequiredTask

    class _Stub(TenantRequiredTask):
        name = "tests.stub_task"
        abstract = False

    inst = _Stub()
    inst.run = run_fn  # type: ignore[method-assign]
    return inst


class TestRefusesWithoutContext:
    def test_no_kwarg_raises(self):
        _ensure_django()
        task = _make_task_with_run(lambda ctx, **kw: "ran")
        with pytest.raises(RuntimeError, match="_tenant_ctx"):
            task()

    def test_empty_kwarg_raises(self):
        _ensure_django()
        task = _make_task_with_run(lambda ctx, **kw: "ran")
        with pytest.raises(RuntimeError, match="_tenant_ctx"):
            task(_tenant_ctx=None)

    def test_malformed_kwarg_raises(self):
        _ensure_django()
        task = _make_task_with_run(lambda ctx, **kw: "ran")
        with pytest.raises(RuntimeError, match="dict|TenantContext"):
            task(_tenant_ctx="not_a_dict")


class TestPinsAndDelegates:
    def test_reconstructs_context_and_pins(self):
        _ensure_django()

        captured = {}

        def fake_run(ctx, **kwargs):
            captured["ctx"] = ctx
            captured["kwargs"] = kwargs
            return "task_result"

        task = _make_task_with_run(fake_run)

        with patch("api.security.tenant_context.with_tenant_schema") as fake_with:
            fake_cm = MagicMock()
            fake_cm.__enter__ = MagicMock(return_value=None)
            fake_cm.__exit__ = MagicMock(return_value=False)
            fake_with.return_value = fake_cm

            result = task(
                _tenant_ctx={
                    "org_id": "acme",
                    "schema": "tenant_acme",
                    "profile_id": "p1",
                },
                some_other_kwarg="x",
            )

            assert result == "task_result"
            assert captured["ctx"].schema == "tenant_acme"
            assert captured["ctx"].org_id == "acme"
            # _tenant_ctx must be removed from kwargs before run is called
            assert "_tenant_ctx" not in captured["kwargs"]
            assert captured["kwargs"]["some_other_kwarg"] == "x"
            # with_tenant_schema was opened with the right schema
            assert fake_with.call_args.args[0] == "tenant_acme"


class TestSerializeCtx:
    """The wire format used to ship a context across the Celery boundary."""

    def test_round_trip_shape(self):
        _ensure_django()
        from api.celery_tasks.base import serialize_ctx
        from api.security.schema_authority import TenantContext

        ctx = TenantContext(org_id="acme", schema="tenant_acme", profile_id="p1")
        d = serialize_ctx(ctx)
        assert d == {"org_id": "acme", "schema": "tenant_acme", "profile_id": "p1"}
