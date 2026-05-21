"""Tests for the MFA core logic — Phase C9.

Exercises api/security/mfa.py — the pure TOTP + recovery-code logic.
No Django models, no HTTP; just the cryptographic core.
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.unit


def _mfa():
    pytest.importorskip("pyotp")
    pytest.importorskip("django")
    import os
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    try:
        import django
        django.setup()
    except Exception:
        pytest.skip("Django not configured in this environment")
    from api.security import mfa
    return mfa


class TestSecretAndURI:
    def test_generate_secret_is_base32(self):
        mfa = _mfa()
        secret = mfa.generate_secret()
        # base32 alphabet: A-Z, 2-7
        assert len(secret) >= 16
        assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for c in secret)

    def test_two_secrets_differ(self):
        mfa = _mfa()
        assert mfa.generate_secret() != mfa.generate_secret()

    def test_provisioning_uri_shape(self):
        mfa = _mfa()
        uri = mfa.provisioning_uri("JBSWY3DPEHPK3PXP", "user@example.com")
        assert uri.startswith("otpauth://totp/")
        assert "user@example.com" in uri
        assert "Bussus" in uri  # issuer


class TestVerifyTOTP:
    def test_correct_code_verifies(self):
        mfa = _mfa()
        import pyotp
        secret = mfa.generate_secret()
        current_code = pyotp.TOTP(secret).now()
        assert mfa.verify_totp(secret, current_code) is True

    def test_wrong_code_rejected(self):
        mfa = _mfa()
        secret = mfa.generate_secret()
        assert mfa.verify_totp(secret, "000000") is False

    def test_non_digit_code_rejected(self):
        mfa = _mfa()
        secret = mfa.generate_secret()
        assert mfa.verify_totp(secret, "abcdef") is False

    def test_empty_inputs_rejected(self):
        mfa = _mfa()
        assert mfa.verify_totp("", "123456") is False
        assert mfa.verify_totp("JBSWY3DPEHPK3PXP", "") is False

    def test_code_with_spaces_normalised(self):
        mfa = _mfa()
        import pyotp
        secret = mfa.generate_secret()
        code = pyotp.TOTP(secret).now()
        # A user pasting "123 456" should still verify.
        spaced = f"{code[:3]} {code[3:]}"
        assert mfa.verify_totp(secret, spaced) is True


class TestRecoveryCodes:
    def test_generate_count_and_format(self):
        mfa = _mfa()
        codes = mfa.generate_recovery_codes()
        assert len(codes) == mfa.RECOVERY_CODE_COUNT
        for c in codes:
            assert "-" in c  # xxxx-xxxx format

    def test_codes_are_unique(self):
        mfa = _mfa()
        codes = mfa.generate_recovery_codes()
        assert len(set(codes)) == len(codes)

    def test_hash_then_check_roundtrip(self):
        mfa = _mfa()
        code = "ab12-cd34"
        hashed = mfa.hash_recovery_code(code)
        assert hashed != code                       # actually hashed
        assert mfa.check_recovery_code(code, hashed) is True
        assert mfa.check_recovery_code("ffff-ffff", hashed) is False

    def test_check_is_normalised(self):
        mfa = _mfa()
        hashed = mfa.hash_recovery_code("AB12-CD34")
        # Different formatting of the same code still matches.
        assert mfa.check_recovery_code("ab12cd34", hashed) is True
        assert mfa.check_recovery_code(" AB12-CD34 ", hashed) is True

    def test_consume_recovery_code_returns_index(self):
        mfa = _mfa()
        plaintext = mfa.generate_recovery_codes()
        hashed = [mfa.hash_recovery_code(c) for c in plaintext]

        # The 3rd code should be found at index 2.
        idx = mfa.consume_recovery_code(plaintext[2], hashed)
        assert idx == 2

        # A non-matching code returns None.
        assert mfa.consume_recovery_code("zzzz-zzzz", hashed) is None
