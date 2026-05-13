# Track A — deferred scope (A4, A5, A7, A8)

**Status:** Pending — separate session(s) needed
**Date:** 2026-05-13
**Owner:** Engineering + Security working group

Phase 1 triage (`claude/sec-01` to `sec-05`) and Phase 3/5/6/7 foundation +
encryption (`sec-phase5-7-foundation`, `sec-phase3-telephony-tokens`,
`sec-phase3-oauth-tokens`, `sec-phase3-salesforce-creds`,
`sec-phase8-file-upload-wiring`) are pushed and ready to merge.

The remaining four Track A items each need a focused session — they're
not mechanical, and rushing them risks breaking production traffic.
This document captures what each one requires so a different engineer
or a future session can pick them up cold.

---

## A4 — DRF auth gate (`claude/sec-phase2-drf-auth-gate`)

**Effort:** 60-80h • **Risk:** High during cutover

### Problem

`version2/settings.py:329-338` has both `DEFAULT_AUTHENTICATION_CLASSES`
and `DEFAULT_PERMISSION_CLASSES` commented out. The dispatcher
explicitly sets `permission_classes = [IsAuthenticated]` (good), but
any view that *doesn't* go through the dispatcher (any of the
`api/APIs/*.py` files outside `dispatcher.py`, plus all `*View.py`
files across apps) inherits NOTHING from DRF defaults — they're
authenticated only if the view explicitly declares it.

This means a forgotten `permission_classes = [...]` declaration on a
view leaves it open. The audit graded this CRITICAL.

### Why it's deferred

This is not a one-line change. Flipping DRF defaults on causes every
view to refuse anonymous traffic — including the ~10-15 legitimately-
public endpoints (login, OTP send/verify, password reset, OAuth
callbacks, third-party webhooks: Facebook, WhatsApp, telephony,
Salesforce). Each of those needs an explicit
`permission_classes = [AllowAny]` opt-out, and the LIST of legitimate
opt-outs has to be audited — not just enumerated — because some
endpoints are mistakenly public today and should be authenticated.

### Plan when picked up

1. **URL audit doc** — list every URL in:
   `api/urls.py`, `adminuser/urls.py`, `facebook/urls.py`,
   `whatsapp/urls.py`, `sf_integration/urls.py`, `public/urls.py`,
   `version2/urls.py`. Classify each as `auth_required` / `public`
   (login, OTP, health) / `webhook` (HMAC-verified) / `internal-only`
   (admin/cron).
2. **Feature flag**: `STRICT_AUTH = env.bool("STRICT_AUTH", default=False)`.
   When True, DRF defaults to `IsAuthenticated` globally.
3. **Per-view opt-outs**: for every URL classified `public`, add
   explicit `permission_classes = [AllowAny]` and
   `authentication_classes = []`. For `webhook`, add HMAC verification
   first (already exists in `api/security/webhook_verification.py`).
4. **Regression test**: `tests/security/test_auth_required.py`
   iterates every URL pattern and asserts unauthenticated requests
   get 401 unless on `tests/security/public_urls.txt` allowlist.
5. **Staging soak**: enable `STRICT_AUTH=1` in staging, replay
   production-shaped traffic for 48h. Triage every unexpected 401
   — either the URL was missed in step 3 or there's a real client
   bug that needs fixing.
6. **Prod rollout**: flip the flag with feature-flag rollback ready.

### Risk

The 48h staging soak is essential. Without it, a forgotten public
endpoint shows up as a customer outage when prod is flipped. Plan
for ≥1 rollback during the soak; budget time for at least 2 iterations.

---

## A5 — SQL injection in `computed_fields.py` (`claude/sec-phase8-sql-injection-fix`)

**Effort:** 24-32h • **Risk:** Medium (deep refactor, runtime-critical path)

### Problem

`api/BL/computed_fields.py` at lines 320, 323, 327 (and several
similar sites) builds SQL via f-string interpolation:

```python
sql = f"SELECT id FROM \"{parent_table}\" WHERE {having_clause}"
sql = f"SELECT id FROM \"{parent_table}\" WHERE ({expr}) {op_sql} %s"
```

A whitelist gates the interpolated values, but it permits parentheses,
commas, and arithmetic operators — sufficient to inject:

```
id) UNION SELECT password FROM users --
```

The audit graded this CRITICAL.

### Why it's deferred

The fix needs:

1. A robust `get_allowed_columns(schema, table)` lookup against
   `information_schema.columns`, with a cache that invalidates on
   DDL (object/field create-or-drop).
2. Conversion of every f-string SQL site to `psycopg2.sql.SQL` /
   `sql.Identifier` / `sql.Literal`, preserving the existing
   query semantics exactly.
3. An operator allow-list — currently `op_sql` can be `=`, `<`, `>`,
   `LIKE`, `ILIKE`, `IN`, `NOT IN`, `IS NULL`, `IS NOT NULL`, and
   probably others. Each needs a sanitised mapping.
4. Regression tests with the sqlmap payload corpus — the fix isn't
   "done" until known-attack payloads are demonstrably blocked at
   parse time, before any SQL reaches the DB.

This file is heavily exercised at runtime (every formula / rollup
evaluation). A bug in the rewrite is a production outage. Tests
need to come BEFORE the rewrite to catch regressions.

### Plan when picked up

1. **Add the test corpus first** —
   `tests/security/test_computed_fields_injection.py` — with the
   ten classic injection payloads. They should all FAIL today (no
   guard), then PASS after the fix.
2. **Inventory call sites** — every f-string and `.format()` SQL
   in `api/BL/computed_fields.py`. List each line + the variables it
   interpolates.
3. **Build the column allow-list cache** in a new module
   `api/BL/computed_fields_columns.py`. Cache lifecycle:
     - Read on first access, store in module-global dict keyed on
       `(schema, table)`.
     - Invalidate when `ObjectManager.create_object`,
       `add_field`, `drop_field` (or the equivalent DDL paths) run.
4. **Rewrite each site** with `psycopg2.sql`.
5. **Soak in staging** for at least 1 week — formula/rollup paths
   are well-trafficked and bugs surface quickly.

### Pre-existing related bug

`api/BL/blcontroller.py:3172` has an f-string with unmatched quotes
under Python 3.11 strict mode (parses fine under 3.12+). Worth
fixing in the same branch since it's adjacent in the BL layer.

---

## A7 — Rate limiting (`claude/sec-phase8-rate-limiting`)

**Effort:** 12-16h • **Risk:** Low (additive)

### Problem

`/login`, `/otp/send`, `/otp/verify`, `/password-reset` have no rate
limiting. An attacker can:
  * Brute-force passwords (no lockout)
  * Spam OTP delivery (cost + DoS via Twilio bill)
  * Spam password-reset emails (annoy users)

The OTP knobs in `settings.py:453-458` (TTL, max attempts, max sends)
are app-level limits but NOT enforced as per-IP / per-account
throttles.

### Why it's deferred

`django-ratelimit` is a small library install plus per-view decorator.
The work is identifying every view that needs throttling and writing
the decorator stacks. It also needs a Redis-backed counter (which
already exists — `CACHES['default']` is Redis) and a progressive-
lockout mechanism using `UserLoginHistory`.

### Plan when picked up

1. `pip install django-ratelimit` + add to requirements.txt.
2. `settings.py`:
   ```python
   RATELIMIT_ENABLE = True
   RATELIMIT_USE_CACHE = "default"
   ```
3. Annotate each login/OTP/password-reset view:
   ```python
   @method_decorator(ratelimit(key='ip', rate='10/h', method='POST', block=True))
   @method_decorator(ratelimit(key='post:email', rate='5/h', method='POST', block=True))
   class LoginView(APIView): ...
   ```
4. Progressive lockout via `UserLoginHistory` (the table exists):
   after 5 failed logins in 15min → 15-min cooldown; after 10 in
   1h → 1-hour cooldown + notification email.
5. Tests — hit each endpoint at the limit + 1 and assert 429.

### Pointers

- `adminuser/LoginView.py` — main login view
- `api/APIs/` — OTP send / verify endpoints (need to locate exact files)
- `authentication/custom_jwt_auth.py` — JWT refresh endpoint

---

## A8 — Mass-assignment whitelist (`claude/sec-phase8-mass-assignment-whitelist`)

**Effort:** 16-24h • **Risk:** Medium (touches many call sites)

### Problem

`api/BL/blcontroller.py` has many sites like:

```python
create_data = {**create_data, 'created_by_id': user_id, 'created_date': now(), ...}
```

If `create_data` (from `request.data`) contains keys like `id`,
`created_by_id`, `owner_id`, `is_active`, those user-supplied values
land BEFORE the system fields — and depending on dict ordering and
later assignments, can win. An attacker constructing a custom
`POST /api/leads` body can:

  * Set `created_by_id` to a different user (audit trail spoof)
  * Set `owner_id` to claim ownership of a record
  * Set `id` to a chosen prefix (collide with someone else's row)
  * Toggle `is_deleted=False` on an existing soft-deleted record by
    POSTing with the same id

The audit graded this HIGH.

### Why it's deferred

The fix needs an explicit allow-list of write-able fields *per
object*. The platform already has this metadata in the `fields`
table (per-tenant), but no API consumes it for create/update
sanitisation. Building that lookup + threading it through every
create site in the 5,000-line god-file is mechanical but
labour-intensive — and you must NOT break the legitimate dict
keys for each object.

### Plan when picked up

1. **Reader for the allow-list**: new module
   `api/BL/allowed_fields.py` with
   `get_allowed_create_fields(schema, object_name)` and
   `get_allowed_update_fields(schema, object_name)`. Cached;
   invalidated on object/field DDL.
2. **Refactor each create-data construction site**:
   ```python
   allowed = get_allowed_create_fields(schema, object_name)
   create_data = {k: payload[k] for k in allowed if k in payload}
   create_data.update({
       'id': generate_id(object_name),
       'created_by_id': user_id,
       'owner_id': payload.get('owner_id', user_id),  # may be in allow-list
       'created_date': now(),
       ...
   })
   ```
3. **Reject (don't drop)** keys not in the allow-list — silent drops
   hide client bugs. Log them at WARNING.
4. **Tests** — for each major object: send `{"id": "ATTACKER", "created_by_id": "OTHER", "<field>": "<legit>"}`. Verify the row
   ends up with the server-side id and `created_by_id == JWT user`.
5. **Pair with audit-log entry**: any user-supplied system field
   that gets dropped should produce an `audit_trail_track` entry
   so attempts are visible.

### Inventory

Search:
```bash
grep -rn "\*\*create_data\|{\*\*.*'created_by_id'" api/BL/
```

Expected hits: ~10-15 sites scattered across the dispatch branches.
Each is a 5-10 line refactor.

---

## Sequencing recommendation

If a single engineer picks these up:

1. **A7** first — quick win, low risk, additive. 1-2 days.
2. **A4** — start the URL audit doc (no code). Then build the
   feature-flag work. 1-2 weeks including soak.
3. **A8** — needs the allow-list reader; couples cleanly with the
   ongoing god-file split (each handler extraction is a natural
   place to install the allow-list). Co-locate with the godfile-split
   waves where convenient. 3-5 days.
4. **A5** — last. Highest risk; do it once the surrounding
   infrastructure is well-tested. 1 week, half of that on regression
   test corpus.

If two engineers in parallel: A4 + A7 in week 1, A5 + A8 in weeks 2-3.

## Acceptance criteria for "Track A complete"

- [ ] A1, A2, A3, A6, foundation already pushed (this session)
- [ ] A4 — staging soak passed (no surprise 401s for 48h), regression test wired
- [ ] A5 — sqlmap payload corpus test passes; no f-string SQL remains in `computed_fields.py`
- [ ] A7 — rate-limit tests pass; integration test simulating burst gets 429
- [ ] A8 — mass-assignment test passes for at least 5 representative objects
- [ ] All eight branches merged to `main`
- [ ] 1 week of clean production traffic after the last merge
