"""Multi-factor authentication core — Phase C9.

In plain English
----------------

A password alone is one factor — "something you know." If it's
phished, leaked, or reused from another breached site, the account
is gone. MFA adds a second factor — "something you have" — a code
from an authenticator app (Google Authenticator, Authy, 1Password)
that changes every 30 seconds.

This module is the **pure logic** of TOTP MFA — no Django models,
no HTTP. It's deliberately separated so it can be unit-tested in
isolation and reused from any caller (the enroll endpoint, the
login flow, a management command).

What's here
-----------

  * generate_secret()        — a new random TOTP secret
  * provisioning_uri()       — the otpauth:// URI an authenticator
                               app scans (the frontend renders it
                               as a QR code)
  * verify_totp()            — check a 6-digit code, with a small
                               time window for clock skew
  * generate_recovery_codes()— one-time backup codes for a lost device
  * hash_recovery_code()     — recovery codes are stored HASHED,
    check_recovery_code()      never plaintext (same as passwords)

TOTP = Time-based One-Time Password (RFC 6238). We use the `pyotp`
library — never hand-roll crypto.
"""

from __future__ import annotations

import secrets
from typing import Optional

import pyotp
from django.contrib.auth.hashers import check_password, make_password


# Issuer name shown in the authenticator app next to the account.
DEFAULT_ISSUER = "Bussus CRM"

# How many 30-second windows of clock skew to tolerate when verifying.
# 1 = accept the current code plus the immediately previous/next one
# (covers a phone clock that's slightly off). Don't raise this much —
# a wider window weakens the second factor.
TOTP_VALID_WINDOW = 1

# Number of one-time recovery codes issued at enrollment.
RECOVERY_CODE_COUNT = 10


def generate_secret() -> str:
    """Return a fresh base32 TOTP secret.

    Store this ENCRYPTED (EncryptedCharField). It is as sensitive as
    a password — anyone with the secret can generate valid codes.
    """
    return pyotp.random_base32()


def provisioning_uri(secret: str, account_email: str,
                     issuer: str = DEFAULT_ISSUER) -> str:
    """Build the ``otpauth://`` URI for an authenticator app.

    The frontend renders this string as a QR code. The user scans
    it once; the app then generates codes forever from the secret.
    """
    return pyotp.TOTP(secret).provisioning_uri(
        name=account_email,
        issuer_name=issuer,
    )


def verify_totp(secret: str, code: str) -> bool:
    """Return True if ``code`` is a currently-valid TOTP for ``secret``.

    Accepts a small clock-skew window (TOTP_VALID_WINDOW). Returns
    False for any malformed input rather than raising.
    """
    if not secret or not code:
        return False
    code = str(code).strip().replace(" ", "")
    if not code.isdigit():
        return False
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=TOTP_VALID_WINDOW)
    except Exception:
        return False


def generate_recovery_codes(count: int = RECOVERY_CODE_COUNT) -> list[str]:
    """Generate ``count`` human-friendly one-time recovery codes.

    Format: ``xxxx-xxxx`` (8 hex chars, dashed). Shown to the user
    ONCE at enrollment — they save them somewhere safe. Each can be
    used once if they lose their authenticator device.

    The CALLER is responsible for storing only the HASHED form
    (see hash_recovery_code) and showing the plaintext to the user
    exactly once.
    """
    codes = []
    for _ in range(count):
        raw = secrets.token_hex(4)  # 8 hex chars
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def hash_recovery_code(code: str) -> str:
    """Hash a recovery code for storage (same hasher as passwords)."""
    return make_password(_normalize_recovery_code(code))


def check_recovery_code(code: str, hashed: str) -> bool:
    """Return True if ``code`` matches the stored ``hashed`` value."""
    if not code or not hashed:
        return False
    try:
        return check_password(_normalize_recovery_code(code), hashed)
    except Exception:
        return False


def _normalize_recovery_code(code: str) -> str:
    """Normalise so 'AB12-CD34', 'ab12cd34', ' AB12-CD34 ' all match."""
    return str(code).strip().lower().replace("-", "").replace(" ", "")


def consume_recovery_code(code: str, hashed_codes: list[str]) -> Optional[int]:
    """Find which stored hash a recovery code matches.

    Returns the INDEX of the matching hash in ``hashed_codes`` (so the
    caller can delete that one — recovery codes are one-time), or
    None if the code matches nothing.
    """
    for i, h in enumerate(hashed_codes or []):
        if check_recovery_code(code, h):
            return i
    return None
