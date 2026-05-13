# Phase 4 part 2 — Row-Level Security on shared tables (operator notes)

**Status:** Code shipped; rollout is operator-driven
**Branch:** `claude/sec-phase4-pt2-rls-shared-tables`
**Builds on:** `claude/sec-phase4-pt1-per-tenant-roles` (merge that first)

## What this branch does in plain English

Phase 4 part 1 gave each tenant its own Postgres role with permissions
on its own schema only. That stops cross-tenant access to tables
inside the per-tenant schemas — `tenant_acme.leads`, `tenant_acme.contacts`,
etc.

But five tables in the `public` schema hold rows from EVERY tenant in one
table:

* `public.organizations`       — one row per customer
* `public.users`               — every customer's users
* `public.user_login_history`  — every login attempt
* `public.session_log`         — every active session
* `public.lead_capture`        — Facebook lead-ad configs

Without extra protection, tenant A's role could `SELECT * FROM public.users`
and see every customer's users. **Row-Level Security (RLS)** plugs that
gap. After this branch:

1. Each of these tables has an `organization_id` column.
2. An RLS policy on each table adds `WHERE organization_id = <current
   tenant>` to every query — Postgres enforces it.
3. The middleware sets `app.current_org_id` on every request so the
   policy knows which tenant is asking.

If tenant A's role tries to read tenant B's user row, the query returns
**zero rows** — the row exists in the table but RLS hides it. INSERT
and UPDATE that try to write another tenant's `organization_id` get a
`new row violates row-level security policy` error.

## What got built

| File | Plain-English purpose |
|---|---|
| `api/migrations/0012_add_organization_id_to_shared_tables.py` | Adds the `organization_id` column to `session_log` + `user_login_history`. Nullable so the migration is instant. |
| `api/management/commands/backfill_organization_id.py` | Fills the new column from `users.organization_id` via batched UPDATEs. Idempotent + dry-run. |
| `api/migrations/0013_enable_rls_shared_tables.py` | Turns RLS on and creates the per-table policies. Reversible — running `migrate api 0012` undoes it. |
| `scripts/per_tenant_ddl/enable_rls_shared_tables.sql` | The same DDL in script form, for ops engineers who prefer to run it via psql + verify before letting Django apply it. |
| `api/security/tenant_schema_middleware.py` | Now also `SET LOCAL app.current_org_id` on every request, and `RESET app.current_org_id` on the way out. |
| `tests/security/test_rls_middleware.py` | Unit tests proving the middleware sets and resets the org-id session variable. |
| `tests/security/test_rls_property_isolation.py` | Hypothesis property tests proving cross-tenant access fails. Requires a live test DB (skips cleanly otherwise). |

## Rollout plan — step by step

### Pre-flight (1 day)

1. Merge `claude/sec-phase4-pt1-per-tenant-roles` first. Without it,
   there's no tenant role for the middleware to assume.
2. Confirm every active org has a provisioned role:
   ```bash
   python manage.py provision_tenant_role --all
   ```
3. Verify with `python manage.py check_deploy` that prod cookie/HSTS
   settings haven't regressed.

### Step 1 — apply migration 0012 (add columns) in staging

Single `ALTER TABLE ADD COLUMN ... NULL` per table. Postgres handles
this without a table rewrite — runs in milliseconds even on multi-
million-row tables.

```bash
python manage.py migrate api 0012_add_organization_id_to_shared_tables
```

Verify:

```sql
\d session_log
\d user_login_history
-- Both should now show organization_id varchar(64).
```

### Step 2 — backfill organization_id (staging)

```bash
# Preview first
python manage.py backfill_organization_id --dry-run

# Then for real (batched, idempotent)
python manage.py backfill_organization_id

# Verify no NULL rows remain
psql $DATABASE_URL -c "SELECT count(*) FROM session_log WHERE organization_id IS NULL;"
psql $DATABASE_URL -c "SELECT count(*) FROM user_login_history WHERE organization_id IS NULL;"
```

If either count is non-zero, the leftover rows are orphans (user
deleted, or `user_id` is NULL). Triage them — usually safe to delete:

```sql
-- These are session log entries with no resolvable owning user; safe to remove.
DELETE FROM session_log
WHERE organization_id IS NULL
  AND (user_id IS NULL OR user_id NOT IN (SELECT id FROM users));
```

### Step 3 — apply migration 0013 (enable RLS) in staging

```bash
python manage.py migrate api 0013_enable_rls_shared_tables
```

Verify policies exist:

```sql
SELECT schemaname, tablename, policyname, cmd
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename, policyname;
```

Should show one `tenant_isolation` policy per table.

### Step 4 — smoke test in staging

Browse the app as a normal user. **Expected**: no behaviour change.
You see your data, not other tenants' data. Two specific things to
verify:

* Login works (the login query runs as the main role, which BYPASSES
  RLS because we haven't FORCEd yet).
* Loading the home page shows your records, not another tenant's.

Run the property test suite:

```bash
pytest tests/security/test_rls_property_isolation.py -m tenant_isolation
```

200 random trials per test, each verifying a tenant A role can't read
a tenant B row through `public.users` / `public.session_log` / etc.

### Step 5 — production rollout (low-traffic window)

1. Apply migration 0012 to prod.
2. Run `backfill_organization_id` (chunked; can run during normal
   traffic — non-blocking UPDATEs).
3. Apply migration 0013.
4. Watch error logs for 24-48h.

What to watch for:
* `new row violates row-level security policy` — a bug in app code
  that's writing with the wrong org_id. Fix the caller; don't disable
  RLS.
* Queries returning empty results that used to return data — a code
  path that wasn't running through `TenantSchemaMiddleware`. Fix the
  call site (use `with_tenant_schema(...)` from `api.security.tenant_context`).

### Step 6 (optional, after 2 weeks soak) — FORCE ROW LEVEL SECURITY

Once Phase 4 part 2 is stable, the final tightening flips FORCE on.
With FORCE, even the table OWNER (the main app role) is subject to
the policy. That's belt-and-suspenders for ops paths — a management
command that forgets to set `app.current_org_id` will return zero
rows instead of every tenant's rows.

This is a separate migration (`0014_force_rls_shared_tables.py` —
not in this branch). Before applying it, audit every management
command + Celery task to make sure they either:
  * Set `app.current_org_id` before querying these tables, or
  * Are explicitly cross-tenant admin tasks that run as a role with
    BYPASSRLS (a Postgres role attribute).

## Rollback

If something breaks in prod after Step 3-5:

```bash
# Roll back the RLS enable
python manage.py migrate api 0012

# (The column is harmless; leave it. If you must remove:)
python manage.py migrate api 0011
```

Migration 0013 has a `reverse_sql` that DISABLEs RLS + DROPs the
policies. Rollback is fast (milliseconds).

Roll back BEFORE flipping FORCE on. After FORCE, even the main role
is subject to the policy — rolling back from there requires careful
ordering (drop FORCE first, then policies).

## Risk + cost

* **Performance**: RLS adds one WHERE clause per query against these
  tables. The `organization_id` column is indexed (the migration adds
  `db_index=True`), so the cost is one extra index scan — negligible
  compared to the rest of any view's work.
* **Risk during rollout**: queries that didn't go through the
  middleware (background jobs, management commands) will see empty
  results from these tables once RLS is on. The `bussus_app` main
  role BYPASSES until FORCE is flipped, so management commands keep
  working — but per-request queries via the tenant role are subject
  to the policy immediately.
* **Login flow**: the dispatcher's login path runs queries against
  `public.users` to find the user by email. The login flow runs as
  the main role (it happens BEFORE the middleware pins a tenant), so
  it BYPASSES the policy — which is correct. Once the user is
  authenticated and the middleware pins their tenant, subsequent
  queries on `public.users` are filtered.

## Verification — what "working" looks like

For any tenant role:

```sql
SET LOCAL ROLE tenant_acme_role;
SET LOCAL app.current_org_id = 'org_acme';

SELECT count(*) FROM public.users;
-- Returns count for org_acme only.

SET LOCAL app.current_org_id = 'org_beta';
SELECT count(*) FROM public.users;
-- Returns 0 (no rows for org_beta in this tenant's view).

RESET ROLE;
```

A hourly cron in production runs this exact query and pages on-call
if either result is wrong. Hook it into your monitoring (Datadog /
Cloudwatch synthetics).

## What's left for the green tick after this branch

See `docs/security/launch_readiness_plan.md` for the full plan. After
Phase 4 part 2 lands, the remaining items for a multi-tenant green
tick are:

* [ ] Phase 9 part 2 — run the property test in CI on every PR that
      touches `api/security/`, `api/migrations/`, or any tenant-aware
      code path.
* [ ] Phase 9 part 3 — external pen test scoped to tenant isolation.
* [ ] A4 — DRF auth-gate (the URL audit is done; the engineering
      branch follows after review).
* [ ] A8 — Mass-assignment whitelist.
* [ ] Phase 5 adoption — convert hot `.objects.filter()` paths to
      `.for_tenant(ctx)` and raw cursors to `tenant_cursor(ctx)`.
* [ ] Phase 6 adoption — convert existing Celery tasks to
      `TenantRequiredTask`.
* [ ] The 10-risk ops list — Sentry, healthz endpoints, statement
      timeout, PgBouncer, backup drill, runbooks.
* [ ] Final tightening — `0014_force_rls_shared_tables.py` once
      ops paths are audited.
