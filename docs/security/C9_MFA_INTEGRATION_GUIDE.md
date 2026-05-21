# C9 — MFA login-integration guide

**Status:** MFA enrollment is fully built. The login-time challenge
needs ONE product decision + a small wiring change. This guide
spells out exactly what's left.

## What this branch shipped (complete + tested)

| Piece | File |
|---|---|
| TOTP core logic (generate / verify / recovery codes) | `api/security/mfa.py` |
| `UserMFA` model (encrypted secret, enabled flag, hashed recovery codes) | `api/models.py` |
| Migration | `api/migrations/0016_user_mfa.py` |
| Enroll / confirm / disable / status endpoints | `api/security/mfa_views.py` |
| URL routes (`/v2/mfa/*`) | `public/urls.py` |
| `pyotp` dependency | `requirements.txt` |
| Core-logic tests (17 tests) | `tests/security/test_mfa.py` |

A user can now **enroll** in MFA end to end:

1. `POST /v2/mfa/enroll` → returns a `provisioning_uri` (frontend
   renders it as a QR code) + 10 one-time recovery codes.
2. User scans the QR with Google Authenticator / Authy / 1Password.
3. `POST /v2/mfa/confirm {"code": "123456"}` → MFA goes live.
4. `POST /v2/mfa/disable {"code": "..."}` → turn it off (needs a
   current code or a recovery code).
5. `GET /v2/mfa/status` → `{"enabled": true/false}`.

## What is NOT yet wired — and why

The **login-time challenge**: when an MFA-enrolled user logs in,
after the password check, the server must demand a TOTP code
*before* issuing the JWT.

That wiring is intentionally not in this branch because it requires
a **product/UX decision** that an engineer should not make alone:

> When a user with MFA submits the right password, what does the
> API return, and how does the frontend collect the code?

There are two standard patterns. Pick one with the product owner.

### Pattern A — two-step with a short-lived MFA ticket (recommended)

1. `POST /v2/login` with username + password.
2. If the password is correct AND the user has MFA enabled, the API
   does **NOT** return the JWT. It returns:
   ```json
   { "mfa_required": true, "mfa_ticket": "<short-lived signed token>" }
   ```
   The `mfa_ticket` is a signed token (use Django's `TimestampSigner`),
   valid ~5 minutes, that encodes the user id. It is NOT a session —
   it cannot be used for anything except step 3.
3. The frontend shows a "enter your 6-digit code" screen.
4. `POST /v2/login/mfa` with `{ "mfa_ticket": "...", "code": "123456" }`.
   The server verifies the ticket + the TOTP code, and only THEN
   issues the real JWT.

This is clean, stateless, and the industry norm.

### Pattern B — single-step (code submitted with the password)

`POST /v2/login` takes `username` + `password` + an optional `code`
in the same request. If the user has MFA and `code` is missing or
wrong → 401 with `{"mfa_required": true}`. The frontend re-submits
the whole form with the code.

Simpler server-side, slightly worse UX (the user re-types their
password). Acceptable if you want the smallest change.

## The wiring change (once the pattern is chosen)

Both login views — `public/auth/login.py` and
`adminuser/LoginView.py` — have the same shape:

```python
if check_password(password, hashed_password):
    # ... issue JWT ...
```

The change, right after `check_password` succeeds:

```python
from api.security import mfa
from api.models import UserMFA

mfa_row = UserMFA.objects.filter(user_id=user_id, enabled=True).first()
if mfa_row:
    # --- Pattern A ---
    code = data.get("code")          # or come back via /v2/login/mfa
    if not code:
        ticket = TimestampSigner().sign(str(user_id))
        return JsonResponse({"mfa_required": True, "mfa_ticket": ticket})
    if not mfa.verify_totp(mfa_row.secret, code):
        # also try a recovery code
        idx = mfa.consume_recovery_code(code, mfa_row.recovery_codes)
        if idx is None:
            return JsonResponse({"error": "Invalid MFA code."}, status=401)
        # recovery code used — burn it
        mfa_row.recovery_codes.pop(idx)
        mfa_row.save(update_fields=["recovery_codes"])
    mfa_row.last_used_at = now()
    mfa_row.save(update_fields=["last_used_at"])
# ... only now issue the JWT ...
```

Estimated effort for the wiring: **1-2 days** including the new
`/v2/login/mfa` endpoint (Pattern A) and updating both login views.

## Making MFA mandatory (rollout)

Don't force MFA on everyone on day one. Recommended sequence:

1. **Ship enrollment** (this branch). MFA is opt-in. Staff enroll
   first as a test.
2. **Mandatory for `is_staff` users.** Add a check in the login
   flow: if `is_staff and not mfa_enabled`, force enrollment before
   issuing a full JWT.
3. **Mandatory for all users**, with a grace period — show a
   "set up MFA" prompt for N logins, then require it.

## Test plan for the wiring

- Enroll a test user, log out, log in → password alone returns
  `mfa_required`; password + correct code returns the JWT.
- Use a recovery code once → it works; use it again → rejected.
- Wrong code → 401, no JWT issued.
- A user WITHOUT MFA → login unchanged (no extra step).

## Summary

| Item | Status |
|---|---|
| MFA enrollment (enroll / confirm / disable / status) | ✅ Done in this branch |
| TOTP core + recovery codes + tests | ✅ Done |
| Login-time challenge | ⏳ Needs Pattern A/B decision, then ~1-2 days wiring |
| Mandatory-MFA rollout | ⏳ Product decision on staging |

The honest reason the login wiring isn't in this branch: it changes
the login *contract* with the frontend (a new response shape, maybe
a new endpoint). That's a cross-team decision, not a unilateral
code change. Everything that CAN be built without that decision is
built, tested, and merged.
