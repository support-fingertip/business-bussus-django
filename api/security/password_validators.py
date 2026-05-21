"""Password validators — Phase C6.

In plain English
----------------

Django ships a ``CommonPasswordValidator`` that checks a password
against a static list of ~20,000 common passwords. That's useful but
small — it doesn't catch a password that leaked in a real-world data
breach but isn't a "common" word.

``BreachedPasswordValidator`` closes that gap. It checks the password
against the Have I Been Pwned (HIBP) "Pwned Passwords" database, which
has **hundreds of millions** of real breached passwords. If the
password has appeared in any known breach, it's rejected.

The k-anonymity model — HIBP never sees the password
----------------------------------------------------

We do NOT send the password (or its full hash) anywhere. The HIBP
"range" API works like this:

  1. SHA-1 hash the password locally.            e.g. 5BAA61E4C9B93F3F...
  2. Send ONLY the first 5 hex characters.       e.g. 5BAA6
  3. HIBP returns every breached-password hash suffix that starts
     with those 5 chars (~500-1000 suffixes).
  4. We check, locally, whether OUR suffix is in that list.

HIBP learns 5 hex chars — which match millions of different
passwords — and never the password itself. This is the standard,
privacy-preserving way to use the service.

Fail-open on network error
--------------------------

If the HIBP API is slow or down, we ALLOW the password (and log it).
Rationale: a temporary HIBP outage must not block every user from
signing up or resetting their password. The other validators
(min length, similarity, common-list, numeric) still apply, so a
fail-open here degrades gracefully rather than breaking auth.

Register it in settings.py AUTH_PASSWORD_VALIDATORS.
"""

from __future__ import annotations

import hashlib
import logging

from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _

logger = logging.getLogger(__name__)


HIBP_RANGE_URL = "https://api.pwnedpasswords.com/range/{prefix}"
HIBP_TIMEOUT_SECONDS = 3


class BreachedPasswordValidator:
    """Reject passwords found in the Have I Been Pwned breach corpus.

    Args:
        threshold: minimum breach-appearance count to reject on.
            Default 1 — reject if the password has appeared in ANY
            breach. Raise this if you want to allow passwords seen
            only a handful of times (not recommended).
    """

    def __init__(self, threshold: int = 1):
        self.threshold = max(1, int(threshold))

    def validate(self, password: str, user=None) -> None:
        if not password:
            return

        # 1. SHA-1 the password locally.
        sha1 = hashlib.sha1(password.encode("utf-8")).hexdigest().upper()
        prefix, suffix = sha1[:5], sha1[5:]

        # 2. Ask HIBP for all hashes sharing the 5-char prefix.
        count = self._breach_count(prefix, suffix)

        # 3. Reject if the breach count meets the threshold.
        if count >= self.threshold:
            raise ValidationError(
                _(
                    "This password has appeared in a known data breach "
                    "and is unsafe to use. Please choose a different password."
                ),
                code="password_breached",
            )

    def _breach_count(self, prefix: str, suffix: str) -> int:
        """Return how many times the password's hash-suffix appears in
        HIBP. Returns 0 (fail-open) on any network/parse error."""
        # Import requests lazily so this module is importable even in
        # an environment without it; fail-open if it isn't installed.
        try:
            import requests
        except ImportError:
            logger.warning(
                "BreachedPasswordValidator: `requests` not installed; "
                "skipping HIBP check (fail-open)."
            )
            return 0

        try:
            resp = requests.get(
                HIBP_RANGE_URL.format(prefix=prefix),
                timeout=HIBP_TIMEOUT_SECONDS,
                headers={"User-Agent": "bussus-crm-password-check"},
            )
            if resp.status_code != 200:
                logger.warning(
                    "BreachedPasswordValidator: HIBP returned %s; "
                    "skipping check (fail-open).",
                    resp.status_code,
                )
                return 0

            # The response is lines of "HASHSUFFIX:COUNT".
            for line in resp.text.splitlines():
                line_suffix, _, line_count = line.partition(":")
                if line_suffix.strip().upper() == suffix:
                    try:
                        return int(line_count.strip())
                    except ValueError:
                        return 1  # found, but count unparseable — reject
            return 0  # suffix not in the breach list — password is clean
        except Exception as exc:
            # Network timeout / DNS failure / TLS error — fail OPEN.
            # A HIBP outage must not block all signups + resets.
            logger.warning(
                "BreachedPasswordValidator: HIBP check failed (%s); "
                "skipping check (fail-open).",
                exc,
            )
            return 0

    def get_help_text(self) -> str:
        return _(
            "Your password must not have appeared in a known data breach."
        )
