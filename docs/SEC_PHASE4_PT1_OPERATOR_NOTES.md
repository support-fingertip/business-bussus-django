# Phase 4 part 1 — per-tenant Postgres roles (operator notes)

**Status:** Foundation shipped; rollout is operator-driven
**Branch:** `claude/sec-phase4-pt1-per-tenant-roles`

## What this branch does in plain English

Before this branch, tenant isolation was a *promise* the application
made: "every query I run honours `SET search_path`." If a query
forgot — say, a Celery task ran without going through the middleware
— it could read another tenant's data.

After this branch, the **database itself** stops cross-tenant reads.
Each tenant gets a Postgres role (`tenant_<schema>_role`) that has
permissions on its own schema only. The application assumes that role
on every request via `SET LOCAL ROLE`. If a buggy query tries to
read another tenant's table, Postgres returns `permission denied`.

Five things landed in this branch:

1. **`scripts/per_tenant_ddl/provision_tenant_role.sql`** — the SQL
   template that creates the role and grants for one tenant.

2. **`scripts/per_tenant_ddl/revoke_tenant_role.sql`** — the inverse,
   used during tenant offboarding.

3. **`python manage.py provision_tenant_role`** — a safe wrapper that
   substitutes the schema name into the template (no string-format
   SQL injection), iterates over every active org if needed, and
   supports `--dry-run` and `--revoke`.

4. **`api/security/tenant_schema_middleware.py`** — now issues
   `SET LOCAL search_path` AND `SET LOCAL ROLE` per request. Resets
   both on `process_response`.

5. **`version2/settings.py`** — `ATOMIC_REQUESTS=True` (so the
   `SET LOCAL` is bounded to the request) and `CONN_MAX_AGE=0` (so
   connections aren't reused with stale state during rollout).

## What this branch DOES NOT do

* It doesn't add Row-Level Security (RLS) to the shared tables in
  `public` (`users`, `organizations`, `user_login_history`,
  `lead_capture`). RLS for those is **Phase 4 part 2** — separate
  branch, coming next.

* It doesn't enable the **enforcement** by default. Until every prod
  tenant has been provisioned, the middleware runs in **tolerant
  mode**: if `SET LOCAL ROLE` fails because the role doesn't exist,
  it logs a WARNING and falls back to search_path-only enforcement.
  This is the safe rollout path. Once every tenant is provisioned,
  flip `ENFORCE_TENANT_ROLE=1` in the environment to make role
  failures a 503 (catches regressions where a new tenant didn't get
  provisioned).

## Rollout plan — step by step

### Step 1: Test in staging

1. Apply this branch in staging.
2. Run `python manage.py provision_tenant_role --all --dry-run` first
   to see what SQL would run.
3. Run `python manage.py provision_tenant_role --all` for real.
4. Smoke test: log in as a user, browse some records, edit one.
   Expected: no behaviour change. Logs may show one or two `SET LOCAL ROLE`
   lines per request.
5. Verify the cross-tenant probe blocks. From psql:
   ```sql
   SET LOCAL ROLE tenant_acme_role;
   SELECT count(*) FROM tenant_beta.profile;
   -- MUST raise: ERROR: permission denied for schema tenant_beta
   ```

### Step 2: Production rollout (during low-traffic window)

1. Deploy this branch to production.
2. Run `python manage.py provision_tenant_role --all`.
3. Tail logs for the next 24-48h. Watch for:
   * `SET LOCAL ROLE failed` warnings — these mean a tenant didn't
     get provisioned. Run the command again for that specific org.
   * Any `permission denied for schema` errors that surface as 500s
     — these are real cross-tenant queries that the old middleware
     was tolerating. Triage each one; fix the query.

### Step 3: Flip to enforce mode

After 1-2 weeks with zero `SET LOCAL ROLE failed` warnings in prod
logs, set `ENFORCE_TENANT_ROLE=1` in every production environment.
Now a missing role becomes a hard 503 — the database refuses to
serve any request that can't pin the right role.

### Step 4: Update the tenant-onboarding runbook

Add a step to `docs/runbooks/tenant_onboard.md`:

```bash
python manage.py provision_tenant_role --org <new_tenant_schema>
```

…between "create the tenant schema" and "smoke test".

### Step 5: Update the tenant-offboarding runbook

Add a step to `docs/runbooks/tenant_offboard.md`:

```bash
python manage.py provision_tenant_role --org <departing_tenant> --revoke
```

…before the schema is dropped.

## Rollback

If the rollout produces unexpected `permission denied` errors:

1. Revert the deployment of this branch.
2. The role grants and ATOMIC_REQUESTS / CONN_MAX_AGE settings revert
   with the deployment.
3. The roles themselves stay in Postgres — they're harmless until the
   middleware uses them.
4. If you want to remove the roles too:
   ```bash
   python manage.py provision_tenant_role --all --revoke
   ```

## Risk + cost

* **Performance**: `SET LOCAL` is cheap (~microseconds). The
  `ATOMIC_REQUESTS` wrapping is one BEGIN/COMMIT pair per request —
  negligible. `CONN_MAX_AGE=0` adds a connection-establishment cost
  per request, more meaningful (~5-10ms). Plan to introduce pgBouncer
  in transaction mode (10-risk item #7) once Phase 4 is stable; that
  combination gives back the connection-reuse savings without losing
  isolation.

* **Risk during rollout**: tolerant mode catches the common case
  (a tenant not yet provisioned). The dangerous case is a query that
  WAS working against the wrong tenant due to a search_path bug;
  Phase 4 now blocks that and the query surfaces as `permission denied`.
  Treat those as P2 incidents and fix the query, not the role.

## Verification — what "working" looks like

After Step 2, every request log should show:

```
SET LOCAL search_path TO tenant_acme, public
SET LOCAL ROLE tenant_tenant_acme_role
... (the actual query) ...
RESET ROLE
SET search_path TO public
```

Pick a random request and confirm the role was set. If you grep
production logs for `SET LOCAL ROLE failed`, the count should be
zero after Step 2 stabilises.

## What's still pending (the green-tick checklist)

See `docs/security/launch_readiness_plan.md` for the full plan. After
this branch ships, the remaining items for a multi-tenant green
tick are:

* [ ] Phase 4 part 2 — RLS on shared tables (`users`, `organizations`,
      `user_login_history`, `lead_capture`). Without RLS, two users
      from different orgs sharing the same Postgres role
      (`tenant_<schema>_role`) can still query each other if a
      query against `public.users` lacks an `organization_id` filter.
* [ ] Phase 9 — property-based cross-tenant tests + external pen test.
* [ ] A4 — DRF auth gate (URL audit reviewed, STRICT_AUTH=1 flipped).
* [ ] A8 — mass-assignment whitelist.
* [ ] 10-risk ops items (Sentry, healthz, statement_timeout, PgBouncer,
      backup drill, runbooks, load test, pen test, etc.).
* [ ] God-file split waves 2-11.
