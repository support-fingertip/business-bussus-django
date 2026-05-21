"""MFA login-challenge helpers — Phase C9 (login wiring).

In plain English
----------------

These helpers connect the MFA enrollment (already built) to the
LOGIN moment. They implement "Pattern A" from
docs/security/C9_MFA_INTEGRATION_GUIDE.md — the two-step login:

  Step 1  POST /v2/login         username + password
          -> if the user has MFA on, the server returns a short-lived
             "mfa_ticket" instead of a JWT.
  Step 2  POST /v2/login/mfa     mfa_ticket + 6-digit code
          -> the server verifies the ticket + code, then issues the JWT.

Why a signed ticket
-------------------

Between step 1 and step 2 the user is "password-verified but not yet
fully logged in". We must NOT issue a real session token yet. The
``mfa_ticket`` is a signed, time-limited token that ONLY says "this
user id passed the password check, < 5 minutes ago". It cannot be
used as a session — it is only accepted by /v2/login/mfa.

We use Django's TimestampSigner — no new dependency, and it is
tamper-proof (signed with SECRET_KEY) and self-expiring.

Safe to deploy immediately
--------------------------

MFA is opt-in. ``user_has_mfa_enabled`` returns False for every user
who has not enrolled — so on a fresh system this whole path is
DORMANT and login is byte-for-byte unchanged. It only activates,
per-user, the moment that user enrolls in MFA. It cannot break an
existing login.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.utils.timezone import now

logger = logging.getLogger(__name__)


# The mfa_ticket is valid for 5 minutes — long enough to open an
# authenticator app, short enough that a stolen ticket is near-useless.
TICKET_MAX_AGE_SECONDS = 300

# Namespacing salt so an mfa_ticket can't be confused with any other
# TimestampSigner-signed value in the app.
_SIGNER_SALT = "bussus.mfa.login.ticket.v1"


def _signer() -> TimestampSigner:
    return TimestampSigner(salt=_SIGNER_SALT)


def issue_mfa_ticket(user_id: str) -> str:
    """Sign a short-lived ticket proving ``user_id`` passed the password
    check. Returned to the client after step 1; spent at step 2."""
    return _signer().sign(str(user_id))


def verify_mfa_ticket(ticket: str) -> Optional[str]:
    """Return the user_id if ``ticket`` is a valid, unexpired MFA ticket,
    otherwise None. Never raises — bad input just returns None."""
    if not ticket:
        return None
    try:
        return _signer().unsign(ticket, max_age=TICKET_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    except Exception:
        return None


def user_has_mfa_enabled(user_id: str) -> bool:
    """True if this user has completed MFA enrollment.

    Returns False on any error (fail-OPEN here is correct: an MFA
    bug must not lock every user out of login — the password check
    has already passed at this point, and the other auth layers
    still apply)."""
    if not user_id:
        return False
    try:
        from api.models import UserMFA
        return UserMFA.objects.filter(user_id=user_id, enabled=True).exists()
    except Exception:
        logger.exception("user_has_mfa_enabled check failed for %s", user_id)
        return False


def verify_login_mfa(user_id: str, code: str) -> bool:
    """Verify a login-time MFA code for ``user_id``.

    Accepts EITHER a current TOTP code OR a one-time recovery code.
    A used recovery code is burned (removed from the stored list).
    Returns False for any bad input."""
    if not user_id or not code:
        return False
    try:
        from api.models import UserMFA
        from api.security import mfa as mfa_core

        row = UserMFA.objects.filter(user_id=user_id, enabled=True).first()
        if not row:
            return False

        # 1. Try a normal TOTP code.
        if mfa_core.verify_totp(row.secret, code):
            row.last_used_at = now()
            row.save(update_fields=["last_used_at"])
            return True

        # 2. Fall back to a one-time recovery code.
        idx = mfa_core.consume_recovery_code(code, row.recovery_codes)
        if idx is not None:
            # Burn the used recovery code so it can't be replayed.
            remaining = list(row.recovery_codes)
            remaining.pop(idx)
            row.recovery_codes = remaining
            row.last_used_at = now()
            row.save(update_fields=["recovery_codes", "last_used_at"])
            logger.info("MFA recovery code used for user %s", user_id)
            return True

        return False
    except Exception:
        logger.exception("verify_login_mfa failed for %s", user_id)
        return False
