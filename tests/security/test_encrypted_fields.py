"""Tests for api.security.encrypted_fields — Phase 3.

Verify the EncryptedCharField / EncryptedTextField:
  1. Encrypt on save (get_prep_value)
  2. Decrypt on read (from_db_value)
  3. Idempotent: re-encrypting an already-encrypted value returns it as-is
  4. Legacy plaintext passthrough: pre-encryption rows still readable
  5. None handling
"""

from __future__ import annotations

import os

import pytest


pytestmark = pytest.mark.unit


def _ensure_django_with_key():
    pytest.importorskip("django")
    pytest.importorskip("cryptography")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    # Token encryption needs a key configured.
    if not os.environ.get("OAUTH_TOKEN_ENC_KEY") and not os.environ.get("OAUTH_TOKEN_ENC_KEYS"):
        from cryptography.fernet import Fernet
        os.environ["OAUTH_TOKEN_ENC_KEY"] = Fernet.generate_key().decode()
    try:
        import django
        django.setup()
    except Exception:
        pytest.skip("Django not configured in this environment")
    # Reset the cached cipher so the new key takes effect for this test
    # run (otherwise a previous import without a key cached a None cipher).
    from api.security import token_encryption as te
    te._cipher = None


class TestEncryptedCharField:
    """get_prep_value / from_db_value / to_python round-trip."""

    def test_get_prep_value_encrypts_plaintext(self):
        _ensure_django_with_key()
        from api.security.encrypted_fields import EncryptedCharField
        from api.security.token_encryption import ENCRYPTED_PREFIX

        field = EncryptedCharField(max_length=1024)
        out = field.get_prep_value("plaintext-secret-123")
        assert out.startswith(ENCRYPTED_PREFIX)
        assert "plaintext-secret-123" not in out  # actual ciphertext

    def test_get_prep_value_idempotent_on_already_encrypted(self):
        _ensure_django_with_key()
        from api.security.encrypted_fields import EncryptedCharField

        field = EncryptedCharField(max_length=1024)
        first = field.get_prep_value("hello")
        second = field.get_prep_value(first)
        # Same ciphertext returned — NOT re-encrypted (which would
        # mean the original plaintext is no longer recoverable).
        assert first == second

    def test_from_db_value_decrypts_encrypted_value(self):
        _ensure_django_with_key()
        from api.security.encrypted_fields import EncryptedCharField

        field = EncryptedCharField(max_length=1024)
        encrypted = field.get_prep_value("round-trip-plaintext")
        recovered = field.from_db_value(encrypted, None, None)
        assert recovered == "round-trip-plaintext"

    def test_from_db_value_passthrough_for_legacy_plaintext(self):
        _ensure_django_with_key()
        from api.security.encrypted_fields import EncryptedCharField

        field = EncryptedCharField(max_length=1024)
        # Row written before encryption rollout — no ENC1: prefix.
        out = field.from_db_value("old-plaintext-token", None, None)
        assert out == "old-plaintext-token"

    def test_none_round_trips(self):
        _ensure_django_with_key()
        from api.security.encrypted_fields import EncryptedCharField

        field = EncryptedCharField(max_length=1024, null=True)
        assert field.get_prep_value(None) is None
        assert field.from_db_value(None, None, None) is None
        assert field.to_python(None) is None
