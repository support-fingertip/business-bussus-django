# Tenant isolation contract

**Status:** Draft
**Date:** 2026-05-13

The contract every code path must obey. Each row is **enforced** by
the layer named, and **verified** by the test or runtime check named.

## L1 — Auth / identity

| Rule | Enforcement | Verification |
|---|---|---|
| Every authenticated request must produce a `TenantContext` before any view body runs | `Dispatcher._init_request_context` → `pin_request_tenant` | `tests/security/test_auth_required.py` enumerates every URL |
| JWT-claimed `org_id` must match `public.users.organization_id` | `schema_authority.resolve_tenant` | Unit test in `tests/security/test_schema_authority.py` |
| Inactive users cannot transact | `Dispatcher._init_request_context` checks `is_active` explicitly (fail-closed) | `tests/security/test_inactive_user_blocked.py` |
| JWT `org_id` is immutable after issue; refresh keeps `org_id` | `simple_jwt` claims; refresh path validates | Test: re-issue refresh with mutated org → reject |

## L2 — Application

| Rule | Enforcement | Verification |
|---|---|---|
| `request.tenant_schema` is the only trusted schema source | Code review + Semgrep rule `forbid-kwarg-schema` | CI fails on `kwargs.get('schema')` outside helpers |
| Public endpoints declare `permission_classes = [AllowAny]` explicitly; no silent exemptions | `tests/security/public_urls.txt` allowlist | Regression test fails on un-listed public URL |
| Webhook receivers verify HMAC before any tenant resolution | `api/security/webhook_verification.py` | Unit test per receiver |
| Cross-tenant resource id returns 404, never 403 | View-layer assertion `record.organization_id == ctx.org_id` | Property test |

## L3 — ORM / query

| Rule | Enforcement | Verification |
|---|---|---|
| `Model.objects.all()` raises unless `for_tenant(ctx)` is used | `TenantManager` in `_base.py` | Build-time Semgrep + unit test |
| Direct `connection.cursor()` is forbidden outside `api/db/tenant_cursor.py` and `api/security/` | Semgrep rule `forbid-direct-cursor` | CI fail |
| F-string SQL is forbidden | Semgrep rule `forbid-fstring-sql` | CI fail |
| Identifiers in raw SQL use `psycopg2.sql.Identifier`, never string interpolation | Code review + Phase 4 audit | `tests/security/test_computed_fields_injection.py` |

## L4 — Database role

| Rule | Enforcement | Verification |
|---|---|---|
| App role assumes `tenant_<schema>_role` per request via `SET LOCAL ROLE` | `TenantSchemaMiddleware.process_view` | Hourly cross-tenant heartbeat job |
| Per-tenant role has `USAGE` only on its own schema + narrow shared-table whitelist | Provisioning DDL in `scripts/provision_customer.sh` | Nightly DB role audit |
| Shared tables (`public.organizations`, `public.users`, `public.user_login_history`, `public.lead_capture`) enforce RLS keyed on `current_setting('app.current_org_id')` | DDL with `FORCE ROW LEVEL SECURITY` | Test: query shared table with wrong `app.current_org_id` → empty |
| `RESET ROLE` runs on response | `TenantSchemaMiddleware.process_response` | Unit test |

## L5 — Infrastructure

| Rule | Enforcement | Verification |
|---|---|---|
| All Redis keys prefixed `tenant:<org_id>:` | `CacheService.tenant_cache` wrapper | Semgrep on `cache.get/set` outside wrapper |
| Object-storage paths under `tenants/<org_id>/…` | Storage path helpers | Code review |
| Per-tenant data-encryption keys derived from KEK via HKDF | `api/security/token_encryption.encrypt_tenant_token` | Unit test: tenant A's DEK cannot decrypt tenant B's ciphertext |
| Backups encrypted with KMS key separate from app role | Cloud config | Quarterly restore drill |
| Logs / metrics / Sentry events tagged with `tenant_id` | `RequestCorrelationMiddleware` + `SafeLogFilter` | Log audit |

## Invariants verified at runtime

These run continuously in production and page on-call on failure:

1. **Hourly cross-tenant heartbeat**: as `tenant_A_role`, attempt
   `SELECT * FROM tenant_B.<table>` → must raise `permission denied`.
2. **Hourly RLS heartbeat**: with `app.current_org_id = 'org_A'`,
   `SELECT count(*) FROM public.users WHERE organization_id = 'org_B'`
   → must return 0.
3. **Connection-reset assert**: `SHOW search_path` at the start of
   each request → must equal `"$user", public` (default), not a stale tenant.
4. **Per-request audit**: every request that reads or writes tenant
   data emits one row to `audit_trail_track`.

## Failure modes — what we ALERT on

| Event | Severity | Action |
|---|---|---|
| `TenantViolation` raised | P1 | Page on-call immediately |
| Cross-tenant heartbeat succeeded | P1 | Page on-call immediately |
| `SET LOCAL ROLE` failed | P1 | Refuse request; page |
| `permission denied` from DB for tenant_X_role | P2 | Investigate; may be a missing GRANT for a new table |
| Semgrep `tenant_isolation` rule violation merged to main | P3 | Backfill CI gate |
