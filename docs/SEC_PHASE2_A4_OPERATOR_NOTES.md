# Phase 2.A4 — DRF auth gate (operator notes)

**Status:** Infrastructure shipped; flag is OFF by default
**Branch:** `claude/sec-phase2-drf-auth-gate`

## What this branch does in plain English

Today, if a developer forgets `permission_classes = [IsAuthenticated]`
on a new API view, the view ships **wide open**. The Dispatcher
(`/v2/api/...`) is safe because it sets that explicitly, but anything
else — admin views, public utility views, integration callbacks —
relies on per-view discipline.

A4 makes "must be authenticated" the **DEFAULT**. Every DRF view
either inherits the global default (and requires a JWT), or the
developer has to explicitly opt out with
`permission_classes = [AllowAny]` + `authentication_classes = []`.
Forgetting the declaration becomes a 401 instead of a security hole.

This branch ships:

1. **A feature flag** (`STRICT_AUTH`) so the gate is wired but OFF
   by default. Setting `STRICT_AUTH=1` in the environment flips it
   on globally. Lets the team flip it after the staging soak.

2. **A public-URL allowlist** (`tests/security/public_urls.txt`) listing
   every URL that's legitimately reachable without a JWT.

3. **A regression test** (`tests/security/test_auth_required.py`) that
   walks the URL conf and flags any view that has `AllowAny` but isn't
   on the allowlist. Adding a public URL forces the developer to
   update the allowlist file, which requires security review on the PR.

4. **Explicit `authentication_classes = []`** added to the two webhook
   views that were missing it (`FacebookWebhookView`, `VerifyWebhookView`)
   so they keep working when the global default flips. They were already
   `AllowAny`-correct; this just makes the intent explicit.

## What this branch DOES NOT do

* It doesn't flip `STRICT_AUTH=1`. That's the operator's job AFTER the
  soak. Flipping it without the soak risks a customer-visible outage if
  any view is accidentally protected.
* It doesn't add HMAC verification to webhook views that lack it. The
  audit identified them as REVIEW items — see below.
* It doesn't resolve the 8 REVIEW items from `docs/security/url_audit.md`.
  Some of those (e.g. `/media/<path>`) need engineering decisions before
  the gate can flip safely.

## Rollout plan — step by step

### Pre-flight (~2 days)

1. **Review `docs/security/url_audit.md`** — 44 routes inventoried.
   Confirm or change the classification on each row. Pay special
   attention to the 8 `REVIEW` items.
2. **Add HMAC verification to every webhook** that doesn't have it
   yet. `api/security/webhook_verification.py` exists for this.
   Webhooks that are `AllowAny` but skip HMAC are effectively
   unauthenticated public endpoints — a worse posture than the
   old behaviour.
3. **Run the regression test in dry-run mode** (locally):

   ```bash
   pytest tests/security/test_auth_required.py -v
   ```

   The test passes when every URL is either on the allowlist or
   inherits a JWT requirement. Failures list which URLs are
   `AllowAny` without being explicitly listed — security-team review
   each one before adding to the allowlist OR fixing the view.

### Step 1 — apply in staging (no behaviour change yet)

1. Merge this branch.
2. Confirm `STRICT_AUTH` is unset (or set to 0) in staging env.
3. Smoke test — nothing should change. The branch is inert with the
   flag off.

### Step 2 — flip in staging (`STRICT_AUTH=1`)

1. Set `STRICT_AUTH=1` in staging.
2. Restart the application.
3. Watch the error logs for the next 48 hours. Look for:

   * `401 Unauthorized` on endpoints that worked before — either
     the endpoint is missing an `AllowAny` opt-out (add it + add to
     the allowlist file) OR it's a real client bug that needs fixing.
   * `403 Forbidden` — usually the JWT is valid but the user isn't
     authorized for the resource. Different bug class; fix the
     view's permission logic.

4. Triage every new 401/403. Goal: zero unexpected 401s for 24
   consecutive hours.

### Step 3 — production rollout (low-traffic window)

1. Set `STRICT_AUTH=1` in production.
2. Tail logs for 4-6 hours.
3. Have on-call ready to flip the flag back if a customer-impacting
   401 surge appears.

### Step 4 — make STRICT_AUTH=1 the hard default

Once stable for 2 weeks in production:

1. Change `version2/settings.py`:
   ```python
   STRICT_AUTH = env.bool("STRICT_AUTH", default=True)  # was default=False
   ```
2. Document that `STRICT_AUTH=0` is now a development-only escape hatch.

## Rollback

If the rollout produces unexpected 401s in production:

```bash
# Set in the environment + restart:
STRICT_AUTH=0
```

The flag is checked at app startup, so a deployment restart picks
up the new value. No code change needed.

## Risk

* **High risk during rollout** — a missed public endpoint
  produces customer-impacting 401s. The 48h staging soak is what
  catches this. Don't skip it.
* **Low risk going forward** — once stable, the gate is set-and-forget
  and adding a new view automatically inherits the safe default.

## Verification — what "working" looks like

After Step 2:

```
# An authenticated GET works:
$ curl -H "Authorization: Bearer $JWT" https://staging.bussus.com/v2/api/leads
{...records...}

# An unauthenticated GET to the same endpoint fails closed:
$ curl https://staging.bussus.com/v2/api/leads
{"detail": "Authentication credentials were not provided."}
# HTTP/1.1 401 Unauthorized

# An unauthenticated GET to a legitimately-public endpoint still works:
$ curl https://staging.bussus.com/v2/login
# (whatever the login endpoint's response shape is — not 401)
```

## Pre-deploy checklist

- [ ] `docs/security/url_audit.md` — every row classification reviewed
- [ ] All 8 REVIEW items in url_audit.md resolved
- [ ] HMAC verification confirmed on every webhook (`telephony/*`,
      `facebook/leadcapture`, `whatsapp/webhook`)
- [ ] `tests/security/test_auth_required.py` passes locally
- [ ] `tests/security/public_urls.txt` reviewed by security working group
- [ ] Staging deployed with `STRICT_AUTH=1` for 48h
- [ ] Zero unexpected 401s for the last 24 of those hours
- [ ] Rollback runbook tested (flip flag back, restart, traffic returns)

Anything not checked above and the flag should NOT flip in production.

## Items still requiring engineering decisions (from url_audit.md)

1. **`/media/<path>`** — serves uploaded files. Tenant-isolation
   check on the storage path?
2. **`/v2/admin/<table>`** — admin variants; org-admin vs.
   platform-admin? MFA?
3. **`/v2/api/invoice/<id>/pdf`** — guessable IDs; org_id check
   inside the view?
4. **`/v2/exists/<table>`** — anti-enumeration?
5. **`/v2/suggestion/domain`** + **`/v2/suggestion/email`** —
   what do they do? Tenant data?
6. **OAuth callbacks** (Gmail/Outlook/Facebook) — `state` parameter
   verification?
7. **Webhook endpoints** — HMAC verified BEFORE any business logic?
8. **`/export/*` views** — cross-tenant export risk?

These don't block this branch from merging (the flag is OFF), but they
DO block flipping it to ON.
