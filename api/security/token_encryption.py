"""Symmetric token encryption helpers.

Used to protect long-lived secrets (OAuth refresh tokens, session refresh
tokens, ext-system credentials) at rest in Postgres.

Transparently handles both encrypted and legacy plaintext values so a
gradual data migration can run without breaking existing flows:
  - ``encrypt_token`` always returns an encrypted ciphertext with the
    ``ENC1:`` prefix.
  - ``decrypt_token`` recognises the prefix; values without it are
    returned unchanged (assumed legacy, to be re-saved encrypted).

Key management:
  - The Fernet key is read from ``OAUTH_TOKEN_ENC_KEY`` (env var). Generate
    once with ``python -c "from cryptography.fernet import Fernet;
    print(Fernet.generate_key().decode())"`` and store in your secrets
    manager.
  - Multiple keys can be supplied as ``OAUTH_TOKEN_ENC_KEYS`` (comma-
    separated). The first key is used for encryption; all keys are tried
    for decryption (key-rotation friendly).
"""

from __future__ import annotations

import logging
import os
from typing import Iterable

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

logger = logging.getLogger(__name__)

ENCRYPTED_PREFIX = "ENC1:"


def _load_keys() -> Iterable[bytes]:
    raw_multi = os.getenv("OAUTH_TOKEN_ENC_KEYS", "")
    raw_single = os.getenv("OAUTH_TOKEN_ENC_KEY", "")
    keys: list[bytes] = []
    if raw_multi:
        keys.extend(
            k.strip().encode() for k in raw_multi.split(",") if k.strip()
        )
    if raw_single:
        keys.append(raw_single.strip().encode())
    if not keys:
        raise RuntimeError(
            "OAUTH_TOKEN_ENC_KEY (or OAUTH_TOKEN_ENC_KEYS) is required to "
            "encrypt/decrypt OAuth tokens. Generate with "
            "Fernet.generate_key()."
        )
    return keys


_cipher: MultiFernet | None = None


def _get_cipher() -> MultiFernet:
    global _cipher
    if _cipher is None:
        keys = list(_load_keys())
        _cipher = MultiFernet([Fernet(k) for k in keys])
    return _cipher


def encrypt_token(plaintext: str) -> str:
    """Encrypt a plaintext token. Returns ``ENC1:<base64-fernet>``."""
    if plaintext is None:
        return plaintext
    if isinstance(plaintext, bytes):
        plaintext_bytes = plaintext
    else:
        plaintext_bytes = str(plaintext).encode("utf-8")
    token = _get_cipher().encrypt(plaintext_bytes)
    return ENCRYPTED_PREFIX + token.decode("ascii")


def decrypt_token(value: str | None) -> str | None:
    """Decrypt a value previously produced by ``encrypt_token``.

    Values without the ``ENC1:`` prefix are returned unchanged so legacy
    plaintext rows continue to work during the migration window.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    if not value.startswith(ENCRYPTED_PREFIX):
        # Legacy plaintext (pre-encryption rollout). Surface a debug log
        # so we can monitor the migration tail.
        logger.debug("decrypt_token: legacy plaintext value detected")
        return value
    payload = value[len(ENCRYPTED_PREFIX):].encode("ascii")
    try:
        return _get_cipher().decrypt(payload).decode("utf-8")
    except InvalidToken as exc:
        # Don't surface the ciphertext in logs; just record the failure.
        logger.error("decrypt_token: invalid token (key rotation needed?)")
        raise RuntimeError("Could not decrypt token") from exc


def is_encrypted(value: str | None) -> bool:
    return isinstance(value, str) and value.startswith(ENCRYPTED_PREFIX)
