"""Encrypted-at-rest Django field types — Phase 3 foundation.

These field classes wrap :func:`api.security.token_encryption.encrypt_token`
and :func:`decrypt_token` so a model column is transparently encrypted
on write and decrypted on read, with no code changes at the call site.

Why field-level instead of a one-off property?
----------------------------------------------

* Reading a model attribute (``session.access_token``) returns the
  plaintext just like before. No call-site change.
* Writing (``session.access_token = "new value"; session.save()``)
  encrypts before persisting. No call-site change.
* Existing rows (plaintext, no ``ENC1:`` prefix) keep working — the
  underlying ``decrypt_token`` returns plaintext unchanged. Existing
  data survives the rollout window; a backfill management command
  re-encrypts at leisure.
* ``get_prep_value`` is idempotent — re-saving an already-encrypted
  value doesn't double-encrypt.

Available types
---------------

* :class:`EncryptedCharField` — drop-in replacement for ``CharField``.
  Bump ``max_length`` to at least ~200 for short tokens, ~1024 for
  refresh tokens / API keys.
* :class:`EncryptedTextField` — drop-in for ``TextField`` (preferred
  when the plaintext length isn't bounded — OAuth refresh tokens,
  page access tokens).

Migration considerations
------------------------

Switching a CharField → EncryptedCharField with the same
``max_length`` generates a Django migration that's a no-op at the
DB level (the column type is unchanged). You DO need to run
``makemigrations`` so Django knows about the new field class.

If the ciphertext is longer than the old ``max_length`` (Fernet
output is ~140 chars overhead), bump the field's ``max_length``
in the same migration.

Usage
-----

    from api.security.encrypted_fields import EncryptedCharField

    class SessionLog(models.Model):
        access_token = EncryptedCharField(max_length=1024)
        # Reads return plaintext; writes encrypt. No other code change.
"""

from __future__ import annotations

from django.db import models

from api.security.token_encryption import (
    ENCRYPTED_PREFIX,
    decrypt_token,
    encrypt_token,
)


class _EncryptedFieldMixin:
    """Shared encrypt-on-write / decrypt-on-read behaviour.

    The mixin defers to the existing :mod:`api.security.token_encryption`
    helpers; behaviour for legacy plaintext values matches what
    those helpers already do (return-as-is, with a DEBUG log).
    """

    def from_db_value(self, value, expression, connection):  # type: ignore[override]
        """Called when Django loads the value from the DB."""
        if value is None:
            return None
        return decrypt_token(value)

    def to_python(self, value):  # type: ignore[override]
        """Called by ``full_clean``/serialization paths."""
        if value is None:
            return None
        if isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX):
            # Stored value — decrypt back to plaintext.
            return decrypt_token(value)
        # Already a Python value (plaintext) — return as-is.
        return value

    def get_prep_value(self, value):  # type: ignore[override]
        """Called before Django persists the value to the DB.

        Idempotent: if the value is already an ``ENC1:`` ciphertext
        (e.g. saved twice without setattr in between), we don't
        re-encrypt — that would render it un-decryptable.
        """
        if value is None:
            return None
        if not isinstance(value, str):
            value = str(value)
        if value.startswith(ENCRYPTED_PREFIX):
            return value
        return encrypt_token(value)


class EncryptedCharField(_EncryptedFieldMixin, models.CharField):
    """CharField that encrypts at rest.

    Default ``max_length`` is 1024 because Fernet output adds
    ~140 chars of overhead and most token columns we encrypt store
    OAuth-shaped values that already approach the legacy 500-char
    cap before the overhead.
    """

    description = "Char field encrypted via api.security.token_encryption"


class EncryptedTextField(_EncryptedFieldMixin, models.TextField):
    """TextField that encrypts at rest.

    Preferred for OAuth refresh tokens, page-access tokens, and
    anything else where the plaintext upper bound isn't known.
    """

    description = "Text field encrypted via api.security.token_encryption"
