"""Tests for BreachedPasswordValidator — Phase C6.

The validator checks a password against Have I Been Pwned via the
k-anonymity range API. These tests mock the HTTP call so they're
fast, deterministic, and don't depend on the network.
"""

from __future__ import annotations

import hashlib
import os
from unittest.mock import MagicMock, patch

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


def _suffix_for(password: str) -> str:
    """The HIBP hash suffix (chars 5+) for a password."""
    return hashlib.sha1(password.encode()).hexdigest().upper()[5:]


def _fake_response(text: str, status: int = 200):
    r = MagicMock()
    r.status_code = status
    r.text = text
    return r


class TestBreachedPasswordRejected:
    def test_breached_password_raises(self):
        _ensure_django()
        from django.core.exceptions import ValidationError
        from api.security.password_validators import BreachedPasswordValidator

        pw = "Password123!"
        suffix = _suffix_for(pw)
        # HIBP returns the suffix with a high count.
        body = f"{suffix}:42007\nAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:5"

        with patch("requests.get", return_value=_fake_response(body)):
            v = BreachedPasswordValidator()
            with pytest.raises(ValidationError) as exc:
                v.validate(pw)
            assert exc.value.code == "password_breached"


class TestCleanPasswordAccepted:
    def test_unbreached_password_passes(self):
        _ensure_django()
        from api.security.password_validators import BreachedPasswordValidator

        pw = "an-extremely-unlikely-passphrase-9f3a2c"
        # HIBP response that does NOT contain our suffix.
        body = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA:5\nBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBBB:9"

        with patch("requests.get", return_value=_fake_response(body)):
            v = BreachedPasswordValidator()
            # Should NOT raise.
            v.validate(pw)


class TestFailOpen:
    """A HIBP outage must NOT block the user — fail open."""

    def test_network_error_allows_password(self):
        _ensure_django()
        from api.security.password_validators import BreachedPasswordValidator

        with patch("requests.get", side_effect=RuntimeError("network down")):
            v = BreachedPasswordValidator()
            # Fail-open: no exception even though HIBP is unreachable.
            v.validate("Password123!")

    def test_non_200_response_allows_password(self):
        _ensure_django()
        from api.security.password_validators import BreachedPasswordValidator

        with patch("requests.get", return_value=_fake_response("", status=503)):
            v = BreachedPasswordValidator()
            v.validate("Password123!")  # no raise


class TestKAnonymity:
    """Confirm we only ever send the first 5 hash chars to HIBP."""

    def test_only_prefix_is_sent(self):
        _ensure_django()
        from api.security.password_validators import BreachedPasswordValidator

        pw = "some-test-password"
        full_sha1 = hashlib.sha1(pw.encode()).hexdigest().upper()
        prefix = full_sha1[:5]

        captured = {}

        def _fake_get(url, *args, **kwargs):
            captured["url"] = url
            return _fake_response("")

        with patch("requests.get", side_effect=_fake_get):
            BreachedPasswordValidator().validate(pw)

        # The URL must contain ONLY the 5-char prefix, never the full hash.
        assert prefix in captured["url"]
        assert full_sha1 not in captured["url"]
        assert full_sha1[5:] not in captured["url"]  # suffix never sent
