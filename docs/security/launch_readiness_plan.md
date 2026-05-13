# Launch-readiness plan — multi-tenant zero-leak

**Status:** Active
**Date:** 2026-05-13
**Owner:** Engineering + Security working group

The 12-phase plan to take the platform from "works for one customer
under engineering supervision" to "safe for public multi-tenant sale."

See `docs/adrs/0004-multi-tenant-zero-leak.md` for the architecture
and `docs/security/isolation_contract.md` for the contract every code
path must obey.

---

## Phase 0 — Threat model & isolation contract (Week 0)

- [x] `docs/security/threat_model.md`
- [x] `docs/security/isolation_contract.md`
- [x] `docs/adrs/0004-multi-tenant-zero-leak.md`
- [ ] Sign-off from 2 senior engineers + external security advisor

## Phase 1 — Triage day (Day 1-2, 8-16h)

One PR per item. Deploy within 48h.

- [ ] **1.1** Delete `test_trigger` backdoor (`api/BL/blcontroller.py:2610-2611`)
- [ ] **1.2** Remove `SECRET_KEY` default (`version2/settings.py:119`)
- [ ] **1.3** Flip `is_active` fail-open in dispatcher (`api/APIs/dispatcher.py:72-74`)
- [x] **1.4** Stack-trace redaction in dispatcher — **already complete** via `_safe_500`
- [ ] **1.5** Production cookie/HSTS defaults gated on `ENVIRONMENT == "production"`
- [ ] **1.6** Startup check + alert if `SCHEMA_AUTHORITY_ENFORCE != "1"` in production

## Phase 2 — Auth gate (Week 1-2, 60-80h)

- [ ] URL audit + `tests/security/public_urls.txt` allowlist file
- [ ] DRF global defaults re-enabled (`DEFAULT_AUTHENTICATION_CLASSES`, `DEFAULT_PERMISSION_CLASSES`) behind `STRICT_AUTH` flag
- [ ] Every public endpoint marks `permission_classes = [AllowAny]` explicitly
- [ ] Regression test enumerates URLs vs. allowlist
- [ ] MFA mandatory for `is_staff=True`
- [ ] Access-token lifetime reduced to 15-30 min
- [ ] Session bound to `org_id`; mismatch invalidates session

## Phase 3 — Secrets at rest (Week 2-3, 40-60h)

- [ ] `SessionLog.access_token` / `refresh_token` encrypted
- [ ] `TelephonyConfig.authtoken` / `sid` encrypted
- [ ] `LeadCapture.page_access_token` encrypted
- [ ] `UserGmailToken` / `UserOutlookToken` legacy tokens encrypted
- [ ] `SalesforceSettings.password` / `client_secret` encrypted
- [ ] `User.app_password` encrypted
- [ ] Per-tenant DEK derivation (`encrypt_tenant_token`)
- [ ] One-shot backfill management commands per table
- [ ] Startup check warns if plaintext rows remain
- [ ] Key-rotation runbook (`docs/runbooks/key_rotation.md`)

## Phase 4 — Database isolation (Week 3-6, 120-180h) ⭐

- [ ] Per-tenant `tenant_<schema>_role` provisioning DDL
- [ ] `TenantSchemaMiddleware` issues `SET LOCAL ROLE` + `SET LOCAL search_path` + `SET LOCAL app.current_org_id`
- [ ] `ATOMIC_REQUESTS=True` for tenant-aware views
- [ ] `CONN_MAX_AGE=0` (until pgBouncer is introduced)
- [ ] RLS policies on `public.organizations`, `public.users`, `public.user_login_history`, `public.lead_capture` with `FORCE ROW LEVEL SECURITY`
- [ ] Backfill `organization_id` on `user_login_history`
- [ ] Hourly cross-tenant + RLS heartbeat job with PagerDuty alert
- [ ] Bastion-only prod DB access; `pg_hba.conf` locked down

## Phase 5 — Application boundary (Week 4-6, 80-120h) ⭐

- [ ] `TenantContext` dataclass
- [ ] `TenantManager` blocks naked `.objects.*`; exposes `for_tenant(ctx)`
- [ ] `api/db/tenant_cursor.py` audited raw-SQL helper
- [ ] `.semgrep/tenant_isolation.yml` rules (forbid naked objects, direct cursor, f-string SQL, kwargs schema)
- [ ] CI pre-commit + main-branch gate
- [ ] Migration tail: per-file conversion + whitelist shrinkage

## Phase 6 — Background work (Week 5-6, 30-50h)

- [ ] `TenantRequiredTask` base; default for `@shared_task`
- [ ] `AdminTask` base for explicit cross-tenant jobs (security-reviewed)
- [ ] Audit all existing tasks; convert to `_tenant_ctx` kwarg
- [ ] Channels consumers wrap handler in `with_tenant_schema`

## Phase 7 — Cache / storage isolation (Week 6, 30-50h)

- [ ] `CacheService.tenant_cache` wrapper with `tenant:<org_id>:` prefix
- [ ] Object-storage path helpers route via `tenants/<org_id>/...`
- [ ] Per-tenant S3 IAM policy (or per-bucket for enterprise tier)
- [ ] Email/SMS templates bound to `organization_id` at send time

## Phase 8 — Input validation & injection (Week 6-7, 60-80h)

- [ ] `api/BL/computed_fields.py` SQL identifiers via `psycopg2.sql.Identifier`
- [ ] Column allow-list from `information_schema`; cache invalidated on DDL
- [ ] File upload: MIME via `python-magic`, size cap, name sanitisation, UUID-prefixed storage
- [ ] Mass-assignment whitelist per object
- [ ] Rate limiting on `/login`, `/otp/*`, `/password-reset`
- [ ] Progressive lockout via `UserLoginHistory`

## Phase 9 — Testing (Week 7-9, 100-150h) ⭐

- [ ] Hypothesis property tests — cross-tenant access from any user/org/endpoint
- [ ] SQL fuzzing using sqlmap payload corpus
- [ ] Chaos test: disable each layer, assert others hold
- [ ] External pen test engaged
- [ ] Bug bounty program ready (private launch first)

## Phase 10 — Observability & forensics (Week 8, 30-40h)

- [ ] `tenant_id` on every log/metric/Sentry event
- [ ] `SafeLogFilter` redacts JWT/token/password/secret keys
- [ ] `audit_trail_track` coverage audited; append-only at DB role level
- [ ] Anomaly alerts (cross-tenant read attempts, denied-RLS spikes)

## Phase 11 — Operational readiness (Week 8-9, 60-100h)

- [ ] Per-tenant feature flags
- [ ] Per-tenant rate limits
- [ ] DSAR (data export) per tenant
- [ ] Right-to-erasure tooling
- [ ] Backup + PITR per tenant
- [ ] `docs/runbooks/tenant_onboard.md`
- [ ] `docs/runbooks/tenant_offboard.md`
- [ ] `docs/runbooks/incident_response_cross_tenant_leak.md`
- [ ] `docs/runbooks/restore_drill.md`
- [ ] SOC 2 Type 1 controls work begun
- [ ] Cyber-insurance bound

## Phase 12 — Pre-launch verification (Week 10)

Hard gates — all must pass before opening signups:

- [ ] All phase 1-11 items shipped + 1 week staging soak
- [ ] Property test: 10,000 random cross-tenant trials, zero leaks
- [ ] Chaos test: each layer disabled in turn, others hold
- [ ] Pen-test report: zero high/critical open
- [ ] DB heartbeat: 168h continuous, all cross-tenant probes blocked
- [ ] Audit-log completeness verified
- [ ] Synthetic-tenant restore drill passed
- [ ] `python manage.py check --deploy` clean
- [ ] On-call rotation staffed + tabletop exercise completed

Soft gates:

- [ ] SOC 2 Type 1 audit underway
- [ ] DPA / ToS / Privacy Policy reviewed by counsel
- [ ] Status page live
- [ ] Customer-facing security white paper

---

## Effort summary

| Phase | Calendar | Engineer-hours |
|---|---|---|
| 0 — Threat model | Week 0 | 20-30 |
| 1 — Triage | Day 1-2 | 8-16 |
| 2 — Auth gate | Week 1-2 | 60-80 |
| 3 — Secrets | Week 2-3 | 40-60 |
| 4 — DB isolation ⭐ | Week 3-6 | 120-180 |
| 5 — App boundary ⭐ | Week 4-6 | 80-120 |
| 6 — Background work | Week 5-6 | 30-50 |
| 7 — Cache/storage | Week 6 | 30-50 |
| 8 — Input validation | Week 6-7 | 60-80 |
| 9 — Testing ⭐ | Week 7-9 | 100-150 |
| 10 — Observability | Week 8 | 30-40 |
| 11 — Ops readiness | Week 8-9 | 60-100 |
| 12 — Pre-launch | Week 10 | 30-50 |
| **Total** | **~10 weeks** | **~670-1000 eng-hrs** |

Assumes 3 senior engineers + 1 DevOps + 1 security engineer (or
external consultant) plus a ~$30-60K pen test budget.
