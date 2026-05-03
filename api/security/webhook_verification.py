"""Webhook signature verification helpers.

Each external integration that posts to us (Voxbay telephony, OAuth
callbacks, future SendGrid/Twilio webhooks) is expected to authenticate
its requests with one of:

  - HMAC-SHA256 signature of the raw body, sent in a header.
  - For OAuth code-exchange callbacks: a JWT-encoded ``state`` parameter
    that we minted on the outbound redirect, with a short TTL.

Helpers below provide the primitives. Each integration's view calls
``verify_hmac_signature`` (or ``verify_oauth_state``) before doing
anything with the payload. If verification fails the view should
return 401 / 403 and log the rejection.

Operator: provide signing secrets via environment variables. Names below
are the conventional ones; rotate them with the provider when changed.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)


def _const_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def verify_hmac_signature(
    raw_body: bytes,
    signature_header: Optional[str],
    secret_env_var: str,
    *,
    algo: str = "sha256",
    prefix: str = "sha256=",
) -> bool:
    """Verify an HMAC signature header against the raw request body.

    Returns True iff the signature is present, well-formed, and matches.
    Falsy returns must be treated as authentication failure by the caller.
    """
    if not signature_header:
        logger.warning(
            "Webhook rejected: missing signature header (secret=%s)",
            secret_env_var,
        )
        return False

    secret = os.getenv(secret_env_var)
    if not secret:
        logger.error(
            "Webhook rejected: %s env var is unset; refusing to accept",
            secret_env_var,
        )
        return False

    expected = hmac.new(
        secret.encode("utf-8"), raw_body, getattr(hashlib, algo)
    ).hexdigest()
    expected_with_prefix = f"{prefix}{expected}"

    candidate = signature_header.strip()
    if not (
        _const_eq(candidate, expected_with_prefix)
        or _const_eq(candidate, expected)
    ):
        logger.warning("Webhook rejected: signature mismatch (secret=%s)", secret_env_var)
        return False
    return True


def verify_oauth_state(
    state_token: Optional[str],
    *,
    max_age_seconds: int = 600,
) -> Optional[dict]:
    """Validate an OAuth ``state`` we previously minted via JWTHandler.

    Returns the decoded payload on success or None on any failure.
    Caller must treat None as authentication failure.
    """
    if not state_token:
        logger.warning("OAuth callback rejected: missing state token")
        return None
    try:
        # Local import to avoid pulling JWTHandler at module import time
        # (it currently lives in BL/utils which has heavy imports).
        from api.BL.utils import JWTHandler

        decoded = JWTHandler().decrypt(state_token)
    except Exception as exc:
        logger.warning("OAuth callback rejected: state decrypt failed: %s", exc)
        return None
    if not isinstance(decoded, dict):
        logger.warning("OAuth callback rejected: state payload not a dict")
        return None

    issued_at = decoded.get("iat") or decoded.get("issued_at")
    expires_at = decoded.get("exp")
    now = time.time()
    if expires_at and now > float(expires_at):
        logger.warning("OAuth callback rejected: state expired")
        return None
    if issued_at and (now - float(issued_at)) > max_age_seconds:
        logger.warning("OAuth callback rejected: state too old")
        return None
    return decoded
