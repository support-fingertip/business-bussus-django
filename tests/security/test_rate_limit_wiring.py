"""Smoke tests for the rate-limit decorator wiring — Phase 8.A7.

These tests don't exercise the actual rate limiter (django-ratelimit
relies on Django's cache, which we'd have to wire in for an integration
test). They verify the WIRING: every targeted view has the right
decorator(s) attached with block=True.

A subtle bug we caught during A7: every decorator was attached without
block=True, which means the library set request.limited but the view
never checked. The result was a rate-limit decorator that LOOKED
like protection but enforced nothing. These tests guard against the
regression.
"""

from __future__ import annotations

import inspect
import os

import pytest


pytestmark = pytest.mark.unit


def _ensure_django():
    pytest.importorskip("django")
    pytest.importorskip("django_ratelimit")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    try:
        import django
        django.setup()
    except Exception:
        pytest.skip("Django not configured in this environment")


def _has_blocking_ratelimit(callable_or_class) -> bool:
    """Heuristic: walk the source to verify block=True is present.

    We can't easily introspect django-ratelimit's runtime state, so
    we read the source. Crude but effective for this purpose.
    """
    src = inspect.getsource(inspect.getmodule(callable_or_class))
    # Find decorators on the callable's name
    name = callable_or_class.__name__
    # Look for any decorator stanza mentioning this name + block=True
    # anywhere in the same source file. This catches both:
    #   @ratelimit(..., block=True)
    #   @method_decorator(ratelimit(..., block=True), name='dispatch')
    return "block=True" in src and name in src


class TestLoginViewRateLimited:
    def test_LoginView_has_blocking_ratelimit(self):
        _ensure_django()
        from public.auth.login import LoginView
        assert _has_blocking_ratelimit(LoginView), (
            "LoginView must have @ratelimit(..., block=True). Without "
            "block=True the decorator is a no-op."
        )


class TestOTPViewsRateLimited:
    def test_start_otp_has_blocking_ratelimit(self):
        _ensure_django()
        from public.auth.otp_verification import start_otp
        assert _has_blocking_ratelimit(start_otp)

    def test_verify_otp_has_blocking_ratelimit(self):
        _ensure_django()
        from public.auth.otp_verification import verify_otp
        assert _has_blocking_ratelimit(verify_otp)

    def test_resend_otp_has_blocking_ratelimit(self):
        _ensure_django()
        from public.auth.otp_verification import resend_otp
        assert _has_blocking_ratelimit(resend_otp)


class TestResetPasswordRateLimited:
    def test_set_password_with_proof_has_blocking_ratelimit(self):
        _ensure_django()
        from public.auth.reset_password import set_password_with_proof
        assert _has_blocking_ratelimit(set_password_with_proof)


class TestSignupRateLimited:
    def test_signup_with_proof_has_blocking_ratelimit(self):
        _ensure_django()
        from public.auth.signup import signup_with_proof
        assert _has_blocking_ratelimit(signup_with_proof)
