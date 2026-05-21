"""Tests for the MFA login-challenge helpers — Phase C9.

Exercises api/security/mfa_login.py — the short-lived signed
mfa_ticket that connects MFA enrollment to the LOGIN moment (the
two-step "Pattern A" login). No HTTP, no tenant DB; just the
ticket-signing primitive and the fail-safe input guards.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.unit


def _mfa_login():
    pytest.importorskip("django")
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    try:
        import django
        django.setup()
    except Exception:
        pytest.skip("Django not configured in this environment")
    from api.security import mfa_login
    return mfa_login


class TestMfaTicket:
    def test_issue_then_verify_roundtrip(self):
        mfa_login = _mfa_login()
        ticket = mfa_login.issue_mfa_ticket("user-123")
        assert isinstance(ticket, str) and ticket
        # The exact user id must come back out.
        assert mfa_login.verify_mfa_ticket(ticket) == "user-123"

    def test_ticket_is_signed_not_plain(self):
        mfa_login = _mfa_login()
        # The ticket must be a signed token, not the id echoed back.
        assert mfa_login.issue_mfa_ticket("user-123") != "user-123"

    def test_tampered_ticket_rejected(self):
        mfa_login = _mfa_login()
        ticket = mfa_login.issue_mfa_ticket("user-123")
        # Flip the last character — the HMAC signature no longer matches.
        tampered = ticket[:-1] + ("A" if ticket[-1] != "A" else "B")
        assert mfa_login.verify_mfa_ticket(tampered) is None

    def test_expired_ticket_rejected(self, monkeypatch):
        mfa_login = _mfa_login()
        ticket = mfa_login.issue_mfa_ticket("user-123")
        # Force every ticket to read as already-expired.
        monkeypatch.setattr(mfa_login, "TICKET_MAX_AGE_SECONDS", -1)
        assert mfa_login.verify_mfa_ticket(ticket) is None

    def test_empty_and_garbage_tickets_rejected(self):
        mfa_login = _mfa_login()
        assert mfa_login.verify_mfa_ticket(None) is None
        assert mfa_login.verify_mfa_ticket("") is None
        assert mfa_login.verify_mfa_ticket("not-a-real-ticket") is None
        assert mfa_login.verify_mfa_ticket("a:b:c") is None


class TestInputGuards:
    """The DB-backed helpers must fail safe on empty input — and the
    guard branch returns before any database access."""

    def test_user_has_mfa_enabled_empty_is_false(self):
        mfa_login = _mfa_login()
        assert mfa_login.user_has_mfa_enabled("") is False
        assert mfa_login.user_has_mfa_enabled(None) is False

    def test_verify_login_mfa_empty_is_false(self):
        mfa_login = _mfa_login()
        assert mfa_login.verify_login_mfa("", "123456") is False
        assert mfa_login.verify_login_mfa("user-123", "") is False
        assert mfa_login.verify_login_mfa(None, None) is False
