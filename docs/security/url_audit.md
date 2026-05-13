# URL audit — every public-facing endpoint

**Status:** Phase 2.A4 starter — enumeration complete, classifications proposed, **needs engineering review before any code change.**
**Date:** 2026-05-13
**Owner:** Engineering + Security working group

## How to use this document

1. Engineering reviews every row and confirms the **Classification** column.
2. Security working group signs off on every `public` and `webhook` classification — those are the bypass paths to DRF auth defaults.
3. Once signed off, build `tests/security/public_urls.txt` from the rows classified `public` or `webhook`.
4. Flip `STRICT_AUTH=1` in settings; DRF defaults to `IsAuthenticated` globally.
5. Run the regression test that asserts every URL is either authenticated OR on the allowlist.
6. 48h staging soak.

**Until this doc is reviewed, don't flip `STRICT_AUTH`.**

## Classifications used

| Code | Meaning |
|---|---|
| `auth_required` | JWT required. Default for everything that touches tenant data. |
| `public` | Legitimately anonymous (login, OTP send, OAuth start, signup). Must explicitly declare `permission_classes = [AllowAny]`. |
| `webhook` | Public *but* authenticated via HMAC / shared secret on each request. Must verify before doing anything. |
| `health` | Liveness/readiness probes from k8s/ECS/load-balancer. Public, no auth. |
| `internal` | Admin/ops only, not exposed to internet. Currently means Django admin. |
| `REVIEW` | Classification needs an engineer/security eye — flagged below. |

## URL inventory (sorted by mount point)

### `version2/urls.py` — top level

| Path | View | Classification | Notes |
|---|---|---|---|
| `/healthz` | `api.health.views.liveness` | `health` | k8s liveness probe |
| `/livez` | `api.health.views.liveness` | `health` | Alias |
| `/readyz` | `api.health.views.readiness` | `health` | DB + Redis reachability |
| `/admin/*` | `django.contrib.admin` | `internal` | Should be IP-restricted at the load balancer; Django session-auth. |
| `/media/<path>` | `cached_media_serve` | **REVIEW** | Serves uploaded files. If a tenant's file path is guessable, this exposes it cross-tenant. Long-term: signed URLs. Short-term: confirm `MEDIA_ROOT` doesn't include sensitive content. |
| `/` | `empty_view` | `public` | Probably a 200 OK placeholder; harmless. |

### `adminuser/urls.py` — mounted at `/v2/`

| Path | View | Classification | Notes |
|---|---|---|---|
| `/v2/admin/login` | `LoginView` (admin user variant) | `public` | Login endpoint — rate-limited in Phase 8.A7. |
| `/v2/admin/<table>` | `YourAPIView` | `auth_required` | Admin operations. **REVIEW** — what kind of admin? If org-admin, normal auth; if platform-admin, needs MFA + bastion. |
| `/v2/admin/<table>/<second>` | `YourAPIView` | `auth_required` | Same |
| `/v2/admin/<table>/<second>/<third>` | `YourAPIView` | `auth_required` | Same |

### `api/urls.py` — mounted at `/v2/`

| Path | View | Classification | Notes |
|---|---|---|---|
| `/v2/api/organization/logo` | `OrganizationLogoView` | `auth_required` | |
| `/v2/api/invoice/<id>/pdf` | `InvoicePDFView` | `auth_required` | **REVIEW** — invoice IDs are guessable; confirm view checks `org_id`. |
| `/v2/api/<object_name>` | `Dispatcher` | `auth_required` | Hot path; already has `permission_classes = [IsAuthenticated]`. |
| `/v2/api/<object_name>/<another>` | `Dispatcher` | `auth_required` | Same |
| `/v2/api/<object_name>/<another>/<param3>` | `Dispatcher` | `auth_required` | Same |
| `/v2/api/send-email/` | `SendTestEmailAPIView` | `auth_required` | |
| `/v2/api/gmail/oauth/callback/` | `GmailOAuthCallbackView` | `public` | OAuth redirect target — Google calls this after user grants. **Must verify the `state` parameter** that this server originally issued; otherwise an attacker can replay a callback. **REVIEW state-verification logic.** |
| `/v2/api/outlook/connect-url/` | `OutlookAuthURLView` | `auth_required` | User-initiated; needs the user's JWT to know whose Outlook to connect. |
| `/v2/api/outlook/oauth/callback/` | `OutlookOAuthCallbackView` | `public` | Same as Gmail callback — `state` verification critical. |
| `/v2/telephony/route` | `telephony_route` | `webhook` | Twilio webhook. **Must HMAC-verify the Twilio request signature.** |
| `/v2/telephony/connecting` | `telephony_connecting` | `webhook` | Same |
| `/v2/telephony/hangup` | `telephony_hangup` | `webhook` | Same |
| `/v2/telephony/cdr` | `telephony_cdr` | `webhook` | Same |
| `/v2/telephony/outgoing` | `telephony_outgoing` | `webhook` | Same |
| `/v2/incoming-call/` | `incoming_call` | `webhook` | Same |

### `public/urls.py` — mounted at `/v2/`

| Path | View | Classification | Notes |
|---|---|---|---|
| `/v2/login` | `LoginView` | `public` | Main login. Rate-limited in Phase 8.A7. |
| `/v2/auth/logout/` | `LogoutView` | `auth_required` | Can only log out if you're logged in. |
| `/v2/reset_password` | `set_password_with_proof` | `public` | Password reset (uses signed proof token). Rate-limited. |
| `/v2/start` | `otp_verification.start_otp` | `public` | Send OTP. Rate-limited. |
| `/v2/verify` | `otp_verification.verify_otp` | `public` | Verify OTP. Rate-limited. |
| `/v2/resend` | `otp_verification.resend_otp` | `public` | Resend OTP. Rate-limited. |
| `/v2/status` | `otp_verification.status_otp` | `public` | Check OTP session status; verification_id is required (opaque). |
| `/v2/cancel` | `otp_verification.cancel_otp` | `public` | Cancel a verification session. |
| `/v2/auth/signup` | `signup_with_proof` | `public` | Signup. Rate-limited. |
| `/v2/exists/<table_name>` | `ExistsView` | **REVIEW** | Reveals whether a record exists in the named table — likely intended for "username exists?" checks during signup. Anti-enumeration risk: respond `True` even for non-existent emails to avoid leaking. |
| `/v2/suggestion/domain` | `SuggestionDomainView` | **REVIEW** | What does this do? Suggests domain names? Should be auth-required if it touches tenant data. |
| `/v2/suggestion/email` | `SuggestionUsernameView` | **REVIEW** | Same |
| `/v2/check/username/` | `CheckUsernameExistsView` | `public` | OK to be public for signup, but harden against enumeration. |

### `sf_integration/urls.py` — mounted at `/salesforce/`

| Path | View | Classification | Notes |
|---|---|---|---|
| `/salesforce/salesforce-sync/` | `get_salesforce_sync` | `auth_required` | |
| `/salesforce/salesforce-sync-update/` | `update_salesforce_sync` | `auth_required` | |
| `/salesforce/sync-metadata/` | `sync_salesforce_metadata` | `auth_required` | |

### `facebook/urls.py` — mounted at `/facebook/`

| Path | View | Classification | Notes |
|---|---|---|---|
| `/facebook/api/facebook/login/` | `facebook_login` | `public` | OAuth redirect target — `state` verification critical. **REVIEW.** |
| `/facebook/fetch-lead-forms/` | `FetchLeadForms` | `auth_required` | |
| `/facebook/get-page-access-token/` | `GetPageAccessToken` | `auth_required` | |
| `/facebook/leadcapture/` | `FacebookWebhookView` | `webhook` | Facebook lead webhook. **Must verify the X-Hub-Signature-256 header** against the app secret before processing. |

### `whatsapp/urls.py` — mounted at `/whatsapp/`

| Path | View | Classification | Notes |
|---|---|---|---|
| `/whatsapp/webhook/` | `VerifyWebhookView` | `webhook` | WhatsApp webhook. **Must HMAC-verify the X-Hub-Signature-256 header.** GET request is the verification handshake (must echo `hub.challenge` only after checking `hub.verify_token`). |

### `data_export/urls.py` — mounted at `/export/`

| Path | View | Classification | Notes |
|---|---|---|---|
| `/export/exportdata/` | `export_selected_objects` | `auth_required` | Exports tenant data. Critical that it respects the requesting user's tenant; **REVIEW** for cross-tenant export risk. |
| `/export/export_audit_trail/` | `export_audit_trail` | `auth_required` | Same |
| `/export/export_report_excel` | `export_report_excel` | `auth_required` | Same |

## Items needing engineering / security review

The following rows are marked `REVIEW` and need a decision before `STRICT_AUTH` flips:

1. **`/media/<path>`** — confirm what's served. Tenant-scoped uploads should be behind a signed URL or an auth-checked view, not raw filesystem serve.
2. **`/v2/admin/<table>` (adminuser)** — what's "admin"? Org-admin or platform-admin? Decide whether MFA is required (Phase 2 also covers this).
3. **`/v2/api/invoice/<invoice_id>/pdf`** — confirm `InvoicePDFView` checks `invoice.organization_id == request.user.organization_id`.
4. **`/v2/exists/<table_name>`** — confirm it's anti-enumeration (always returns `True` regardless of actual existence).
5. **`/v2/suggestion/domain`**, **`/v2/suggestion/email`** — what do they do? Likely auth-required if they hit tenant data.
6. **OAuth callbacks** (`Gmail`, `Outlook`, `Facebook login`) — confirm `state` parameter is server-issued and verified on callback. **Without this, attackers can hijack the OAuth flow.**
7. **All webhook endpoints** (`telephony/*`, `facebook/leadcapture`, `whatsapp/webhook`) — confirm HMAC verification runs **before** any business logic. `api/security/webhook_verification.py` exists; verify it's actually called.
8. **All `data_export/*` views** — confirm the export queries are scoped to the requesting user's `org_id`.

## Next step — the actual A4 work

Once this audit is reviewed and signed off:

1. **Build the allowlist file**: `tests/security/public_urls.txt` — one line per URL classified `public`, `webhook`, or `health`. Anything not on the list MUST require auth.

2. **Enable the gate behind a flag in `version2/settings.py`**:
   ```python
   REST_FRAMEWORK = {
       'DEFAULT_AUTHENTICATION_CLASSES': (
           'authentication.custom_jwt_auth.CustomJWTAuthentication',
       ),
       'DEFAULT_PERMISSION_CLASSES': (
           'rest_framework.permissions.IsAuthenticated',
       ) if env.bool("STRICT_AUTH", default=False) else (),
   }
   ```

3. **Add `permission_classes = [AllowAny]` and `authentication_classes = []` explicitly** to every `public` / `webhook` / `health` view. No silent inheritance.

4. **Add HMAC verification** to every `webhook` view that doesn't have it yet. Use the existing `api/security/webhook_verification.py` helper.

5. **Build the regression test** `tests/security/test_auth_required.py`:
   - Import the URL conf
   - For every URL pattern: send an unauthenticated request, assert 401/403 unless the URL is in `public_urls.txt`
   - Fail CI on any new public URL added without updating the allowlist (forces the security review)

6. **Stage with `STRICT_AUTH=1`** for 48h+. Triage every unexpected 401/403 — they're either missed exemptions (step 3) or real client bugs needing a fix.

7. **Promote to production** with the flag rollback ready. Plan ≥1 hotfix during the rollout window.

## Estimated effort once review is done

- Allowlist file + regression test: 8h
- Per-view `AllowAny` declarations (~15 views): 4h
- HMAC verification for any webhook that's missing it: 4h
- Settings change + feature flag wiring: 2h
- Staging soak + triage: 16-24h
- Production rollout: 4-8h
- **Total: 38-50h** after this audit is reviewed.

The `REVIEW` items above may surface bugs that need their own fix branches — budget +20-40h for those.

## Hard blockers — these MUST be true before flipping STRICT_AUTH

- [ ] Every row classified `auth_required` confirmed to work today (otherwise flipping the gate produces a 401 storm).
- [ ] Every row classified `public` confirmed safe (anti-enumeration on signup-related endpoints, `state` verification on OAuth callbacks).
- [ ] Every row classified `webhook` confirmed to HMAC-verify before any business logic.
- [ ] Every row marked `REVIEW` either reclassified or fixed.
- [ ] Allowlist file authored and reviewed.
- [ ] Regression test added.
- [ ] 48h staging soak completed with replayed prod traffic.

Anything else and the gate flip risks a customer-visible outage.
