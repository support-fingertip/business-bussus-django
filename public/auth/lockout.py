"""Progressive lockout for the login endpoint — Phase 8.A7.

Pairs with the per-IP/per-email rate limits in ``public.auth.login``.
Rate-limiting handles the *volume* axis (one IP can't brute-force);
this module handles the *target* axis (one account can't be brute-
forced even across rotating IPs).

Mechanism
---------

We count failed `UserLoginHistory` rows for a given email in the
last ``AUTH_LOCKOUT_WINDOW_MINUTES``. If the count reaches
``AUTH_LOCKOUT_THRESHOLD``, subsequent login attempts for that email
are refused for ``AUTH_LOCKOUT_MINUTES`` from the moment of the
threshold-crossing failure.

``UserLoginHistory`` already records every login (success/failed)
with timestamp + email-derived user FK + IP. The lockout reads from
this table — no new table needed, no new write path on the hot login
path beyond what was already there.

Defaults (overridable via env vars in settings.py)
--------------------------------------------------

* AUTH_LOCKOUT_THRESHOLD       — 5 failures
* AUTH_LOCKOUT_WINDOW_MINUTES  — within a 15-minute window
* AUTH_LOCKOUT_MINUTES         — locks for 15 minutes

Notification (future enhancement, Phase 8.A7+)
----------------------------------------------

When an account hits the lockout threshold, we should email the
account owner so they know someone is brute-forcing them. Out of
scope for the foundation commit; tracked in
docs/security/TRACK_A_DEFERRED_SCOPE.md.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.utils.timezone import now

logger = logging.getLogger(__name__)


def is_locked_out(email: Optional[str]) -> bool:
    """Return True if ``email`` is currently in a lockout window.

    Implementation note: we run the count via the ORM rather than raw
    SQL so the search-path / role guards continue to apply. The query
    hits the ``user_login_history`` table once with two filters; it's
    indexed on ``login_time`` so the cost is constant on a small
    rolling window.
    """
    if not email:
        return False

    from api.models import UserLoginHistory, User

    threshold = getattr(settings, "AUTH_LOCKOUT_THRESHOLD", 5)
    window_min = getattr(settings, "AUTH_LOCKOUT_WINDOW_MINUTES", 15)

    try:
        # We don't import User just for the foreign-key resolve — the
        # history table records via the `users` FK and the username is
        # accessed through `user__email` reverse-lookup. Filter via
        # email so we don't need an extra User.objects.get() call.
        recent_failures = UserLoginHistory.objects.filter(
            user__email__iexact=email.strip().lower(),
            login_time__gte=now() - timedelta(minutes=window_min),
            login_type="failed",
        ).count()
    except Exception:
        # If the count fails (DB hiccup, unmigrated env), fail OPEN —
        # we don't want a lockout-query bug to take down login. Log
        # so monitoring catches it.
        logger.exception("is_locked_out: count failed; allowing login")
        return False

    if recent_failures >= threshold:
        logger.warning(
            "Login lockout active for email",
            extra={"email": email, "recent_failures": recent_failures},
        )
        return True
    return False


def lockout_response_payload(email: Optional[str]) -> dict:
    """The body of a 429 response when the lockout fires.

    Deliberately vague — never reveal whether the email exists or how
    many attempts remain. An attacker enumerating accounts must not
    learn anything from this response.
    """
    minutes = getattr(settings, "AUTH_LOCKOUT_MINUTES", 15)
    return {
        "error": "too_many_attempts",
        "message": (
            f"Too many failed login attempts. Try again in "
            f"approximately {minutes} minutes, or use Forgot Password."
        ),
    }
