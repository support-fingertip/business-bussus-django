# C9 — MFA in Bussus

## IMPORTANT — read this first

**Login is NOT in this repo.** It is owned entirely by
`backend-cpanel-bussus` — the only project that checks passwords and
issues JWTs. This repo (`bussus-bussiness-backend`) is the tenant
data API; it only *validates* the JWTs that cpanel issues
(see `authentication/custom_jwt_auth.py` → `CustomJWTAuthentication`).

Therefore **the login-time MFA challenge belongs in
`backend-cpanel-bussus`, not here.** Do not wire MFA into
`public/auth/login.py` — that `LoginView` (`/v2/login`) is legacy and
unused by the live login UI.

An earlier version of this guide contained a "Pattern A / Pattern B"
plan for wiring MFA into this repo's login views. That plan was
written before the cpanel / data-backend split was documented. It was
**wrong**, was briefly implemented, and has been reverted. The wiring
guidance has been removed from this doc so it cannot mislead again.

## What MFA code currently lives in this repo

Only the **enrollment / management** side — the endpoints an
already-authenticated user calls to set up or remove MFA:

| Piece | File |
|---|---|
| TOTP core logic (generate / verify / recovery codes) | `api/security/mfa.py` |
| `UserMFA` model (encrypted secret, enabled flag, hashed recovery codes) | `api/models.py` |
| Migration | `api/migrations/0016_user_mfa.py` |
| Enroll / confirm / disable / status endpoints | `api/security/mfa_views.py` |
| URL routes (`/v2/mfa/*`) | `public/urls.py` |
| `pyotp` dependency | `requirements.txt` |
| Core-logic tests | `tests/security/test_mfa.py` |

Enrollment flow (all routes require a valid JWT — the user is already
logged in via cpanel):

1. `POST /v2/mfa/enroll` → returns a `provisioning_uri` (frontend
   renders it as a QR code) + 10 one-time recovery codes.
2. User scans the QR with Google Authenticator / Authy / 1Password.
3. `POST /v2/mfa/confirm {"code": "123456"}` → MFA goes live.
4. `POST /v2/mfa/disable {"code": "..."}` → turn it off (needs a
   current code or a recovery code).
5. `GET /v2/mfa/status` → `{"enabled": true/false}`.

## Open architecture decision — before login-time MFA can be built

The login-time MFA challenge (demand a TOTP code before issuing the
JWT) must be built in `backend-cpanel-bussus`. To verify a code at
login, that project needs to read the `UserMFA` row for the user —
and `UserMFA` currently lives in **this** repo's `public` schema.

The team must decide one of:

- cpanel reads `UserMFA` directly from the shared `public` schema, or
- the `UserMFA` table and the enrollment endpoints move to
  `backend-cpanel-bussus`, so login owns its own MFA data.

This is a cross-project decision. Until it is made and login-time
verification is built in cpanel, MFA enrollment works but **login is
not yet actually protected by it.**
