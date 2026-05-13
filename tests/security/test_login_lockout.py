"""Tests for public.auth.lockout — Phase 8.A7 progressive lockout.

The lockout fires after AUTH_LOCKOUT_THRESHOLD failed login attempts
for the same email within AUTH_LOCKOUT_WINDOW_MINUTES. These tests
mock the UserLoginHistory query so they don't need a DB.
"""

from __future__ import annotations

import os
from unittest.mock import patch

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


class TestIsLockedOut:
    def test_empty_email_not_locked(self):
        _ensure_django()
        from public.auth.lockout import is_locked_out
        assert is_locked_out(None) is False
        assert is_locked_out("") is False

    def test_below_threshold_not_locked(self):
        _ensure_django()
        from public.auth.lockout import is_locked_out

        with patch("api.models.UserLoginHistory") as fake_hist:
            fake_qs = fake_hist.objects.filter.return_value
            fake_qs.count.return_value = 2  # below default threshold of 5
            assert is_locked_out("user@example.com") is False

    def test_at_threshold_locked(self):
        _ensure_django()
        from public.auth.lockout import is_locked_out

        with patch("api.models.UserLoginHistory") as fake_hist:
            fake_qs = fake_hist.objects.filter.return_value
            fake_qs.count.return_value = 5  # at default threshold
            assert is_locked_out("user@example.com") is True

    def test_above_threshold_locked(self):
        _ensure_django()
        from public.auth.lockout import is_locked_out

        with patch("api.models.UserLoginHistory") as fake_hist:
            fake_qs = fake_hist.objects.filter.return_value
            fake_qs.count.return_value = 17
            assert is_locked_out("user@example.com") is True

    def test_count_failure_fails_open(self):
        """If the count query throws (DB blip, missing migration), don't
        accidentally lock out everyone — log + allow login. This is a
        deliberate fail-open because the alternative is bringing down
        login when the lockout query has a bug."""
        _ensure_django()
        from public.auth.lockout import is_locked_out

        with patch("api.models.UserLoginHistory") as fake_hist:
            fake_hist.objects.filter.side_effect = RuntimeError("DB down")
            assert is_locked_out("user@example.com") is False


class TestLockoutResponsePayload:
    def test_payload_doesnt_leak_existence(self):
        _ensure_django()
        from public.auth.lockout import lockout_response_payload

        body = lockout_response_payload("known@example.com")
        # Must not include the email, must not say "this account is locked"
        # specifically — same shape regardless of whether the email exists.
        assert "known@example.com" not in str(body)
        assert "error" in body
        assert "message" in body
        assert body["error"] == "too_many_attempts"

    def test_payload_same_for_unknown_email(self):
        _ensure_django()
        from public.auth.lockout import lockout_response_payload

        a = lockout_response_payload("known@example.com")
        b = lockout_response_payload("does-not-exist@example.com")
        assert a == b  # shape must not betray account existence
