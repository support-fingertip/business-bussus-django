# Dual-path soak runbook

Across Phases 2.B, 3.C, and 4.B we stacked **26 dual-path cursor sites**
behind **three independent feature flags**. Every dual-path site has
shipped to `main` with the flag **off** — the legacy raw-SQL path runs
in production today.

This runbook is the single source of truth for turning those flags on.
Read it end-to-end before flipping anything.

## The three flags

| Env var | Phase | Sites | What it controls |
|---|---|---|---|
| `USE_ORM_FOR_PERMISSIONS` | 2.B | 5 | `permissions.py` setup-table CRUD via Django ORM |
| `USE_ORM_FOR_BL` | 3.C waves 1+2 | 17 | BL files using Wave 3-5 + Phase 3.B tenant models |
| `USE_DYNAMIC_GATEWAY` | 4.B waves 1-4 | 4 | Dynamic-object CRUD (D/U/I/S) via the gateway |

The flags are **independent** — flipping one doesn't affect the others.
Per-wave operator notes have site-specific detail; this runbook
sequences the rollout across all three.

## Pre-flight checklist (run once, before staging)

Before any flag is flipped, regardless of which one:

- [ ] **Branch parity** — confirm staging is on a build that includes
      Phase 2.B + 3.C + 4.B (all phases through `claude/phase4-b-wave4-select-cutover`).
      If staging is behind, soak the older flags only on the older
      build.
- [ ] **Migrations applied** — `python manage.py migrate api` runs as
      a no-op for 0005-0009. Migration `0008` (org_company) and
      `0009` (lead_capture) are state-only; they should emit zero
      DDL. If staging shows DDL, reconcile before continuing.
- [ ] **Structural tests pass** — the GitHub Actions workflow
      `Structural tests` is green on `main`. The drift test, the
      parity test, and every dispatch-wiring test must pass.
- [ ] **Tenant schemas have the Phase 3.B/4.A tables** — run
      `python scripts/ddl_introspection.py compare` against staging.
      Drift on `org_company` is expected for older tenants
      (acceptable — no code queries it). Drift anywhere else is a
      blocker.
- [ ] **Dispatch logging is captured** — verify the application's log
      collector (Sentry / DataDog / CloudWatch) is recording lines
      from logger `api.permissions._orm_dispatch`. The default level
      is DEBUG; set `SOAK_LOG_LEVEL=INFO` during the soak so the
      lines show up in standard log streams.
- [ ] **Operator has rollback access** — confirm whoever's flipping
      flags can also revert env vars without a deploy (e.g. via
      ECS task definition env, Kubernetes ConfigMap, or whatever
      controls the runtime env).

## Recommended rollout order

The flags are independent, but they have **different blast radii**.
Roll them out in increasing-risk order so a problem caught on flag N
doesn't muddy the soak signal for flag N+1.

```
1. USE_ORM_FOR_PERMISSIONS (Phase 2.B)
       ↓ smallest surface, oldest code
2. USE_ORM_FOR_BL (Phase 3.C)
       ↓ medium surface, both reads + writes
3. USE_DYNAMIC_GATEWAY (Phase 4.B)
       ↓ largest surface, every CRUD op on dynamic-object tables
```

Each flag goes through five stages. Don't proceed to the next stage
unless the exit criteria are met.

---

## Stage 1 — Pre-soak verification (per flag)

Goal: prove the new code path works at all, with no traffic.

```bash
# Spin up a test container with the flag on; run unit tests.
docker run --rm -e USE_ORM_FOR_PERMISSIONS=1 \
    -e DJANGO_SETTINGS_MODULE=version2.settings \
    your-image pytest -m unit -v
```

Exit criteria:
- All unit tests pass with the flag on.
- The dispatch tests for the flag actually exercise both paths
  (you'll see `ORM path` log lines for the dispatch sites in test
  output).

---

## Stage 2 — Staging soak (per flag, **at least 1 week**)

Goal: prove the new path matches the old path under realistic load.

1. Set `<FLAG>=1` in staging env.
2. Set `SOAK_LOG_LEVEL=INFO` so dispatch logs hit production log
   streams.
3. Run regression smoke tests against staging:
   - **For `USE_ORM_FOR_PERMISSIONS`:** hit a few endpoints that
     read/write the `object`, `fields`, `profile`, `sharing_records`
     tables. Verify the responses match what staging-without-flag
     produced.
   - **For `USE_ORM_FOR_BL`:** trigger a workflow execution; render
     a page-layout list view; share a record with a user and verify
     it appears in their feed; send an email through SendGrid;
     route a Voxbay test call into a configured landing number.
   - **For `USE_DYNAMIC_GATEWAY`:** hit a list endpoint (SELECT),
     edit a record (UPDATE), create a record (INSERT), delete a
     record (DELETE). Verify rows look identical between flag-on
     and flag-off staging instances.
4. Watch logs for ANY exception from the new path. The dispatch
   helper deliberately doesn't mask them, so they'll show up
   clearly in error monitoring.
5. Run the regression suite for at least one full week, at staging's
   normal load profile.

Exit criteria for Stage 2:
- Zero new exceptions from the dispatch sites that weren't already
  present on the legacy path.
- Functional parity confirmed by spot-checks across the relevant
  endpoint surface.
- Performance is within ±20% of the legacy path. (The new paths
  generally aren't faster — the goal is "not noticeably slower",
  not optimisation.)

If any criterion fails, set `<FLAG>=0` in staging, fix the issue,
re-deploy, and start Stage 2 over.

---

## Stage 3 — Canary tenant (per flag, **at least 3 days**)

Goal: prove the new path matches the old path on real production
data.

1. Pick **one** tenant — preferably an internal/test tenant, not a
   paying customer. Note its `database_schema` value.
2. Apply the flag at the tenant level (depends on your deploy
   tooling: `ENVIRONMENT_VARIABLES.tenant_<schema>.USE_*` or similar).
   If your stack doesn't support per-tenant env, deploy a separate
   container/instance just for that tenant.
3. Run for at least 3 days at production load.
4. Watch the same metrics as Stage 2: error rate, latency, log
   lines from the dispatch sites.

Exit criteria:
- Zero ORM-path exceptions across the 3-day window.
- Error rate within ±0.1% of the rest of the fleet.
- Latency within ±10% of the rest of the fleet.

Failure response: set the canary's flag to 0; investigate; consider
running the staging soak again on the affected wave.

For `USE_DYNAMIC_GATEWAY` specifically: extend Stage 3 to **5 days**
because SELECT errors are user-visible (broken list pages).

---

## Stage 4 — Full rollout (per flag)

Goal: enable the new path for every tenant.

1. Set `<FLAG>=1` globally.
2. Watch logs for 24h.
3. After 24h with no anomalies, the rollout is complete.

If anomalies appear, set `<FLAG>=0` globally — the legacy path is
byte-identical and rollback is instant.

---

## Stage 5 — Delete the raw paths (per flag, **after two release cycles**)

Goal: remove the dead code so the codebase no longer has two
implementations to maintain.

For `USE_DYNAMIC_GATEWAY` specifically: wait **three** release cycles
(reads have the largest blast radius — give them extra time before
removing the rollback path).

Per-flag deletion checklist (file-by-file as you delete):

  * `_<name>_raw` helper functions
  * The dispatch wrapper itself (the `_dispatch_path(...)` call)
  * Any `_resolve_actor_id` style adapters that only the raw path
    needed
  * Update operator notes to mark the flag as "retired"

Don't delete the dispatch primitive (`api/permissions/_orm_dispatch.py`)
itself — future cutovers will reuse it.

---

## What to monitor during every stage

### Log signals (high precision, low recall)

The dispatch helper emits a structured log line per call:

```
USE_ORM_FOR_PERMISSIONS.get_object_details: ORM path
USE_ORM_FOR_BL.workflow_executor.list_workflows: raw-SQL path
USE_DYNAMIC_GATEWAY.deleteSQLFunction.delete_data_sql.leads: ORM path
```

The format is `<flag>.<dispatch_name>: <path>`. Parse-friendly:
``\b(USE_ORM_FOR_PERMISSIONS|USE_ORM_FOR_BL|USE_DYNAMIC_GATEWAY)\.[\w.]+: (ORM path|raw-SQL path)\b``.

Default level is DEBUG. Set `SOAK_LOG_LEVEL=INFO` during the soak so
the lines hit production log streams without flipping the entire
application's log level.

### Error signals

The dispatch helper does NOT mask exceptions — bugs in the new path
propagate to the caller exactly as they would in the legacy path.
Exceptions are caught by the calling code's existing error handling
(typically a `print(...)` + raise from the BL layer, surfaced to the
client as a 500). Watch for:

  * New exception types that didn't appear pre-flag
  * Exception messages mentioning `dynamic_table`, `_orm_dispatch`,
    `_execute_*`, `update_unchecked`, `insert_unchecked`,
    `select_raw` — these strings appear only in the new path
  * `OperationalError: relation "X" does not exist` — schema-pin
    drift; the new path didn't pin the search_path correctly

### Performance signals

For each dispatch site, watch p50/p95/p99 latency. If a site jumps
>20% on the ORM path, investigate before continuing the rollout.

The expected pattern: similar p50, slightly higher p95/p99 on the
ORM path due to additional cursor work (e.g. metadata loads,
information_schema probes). If you see the opposite — much higher
p50 — there's likely an N+1 or repeated metadata fetch.

---

## Quick reference: flag-to-site mapping

For when you need to know exactly which site fires when which flag is on.

### `USE_ORM_FOR_PERMISSIONS` (5 sites — Phase 2.B)

  * `api/permissions/permissions.py:get_object_details`
  * `api/permissions/permissions.py:profile_has_admin_access`
  * `api/permissions/permissions.py:check_permission`
  * `api/permissions/permissions.py:get_object_access_level`
  * `api/permissions/permissions.py:get_field_metadata`

See `docs/PHASE2_B_OPERATOR_NOTES.md` for the per-site detail.

### `USE_ORM_FOR_BL` (17 sites — Phase 3.C)

Wave 1 (11 sites):
  * `api/BL/PageLayouts/page_layout.py:_resolve_user_names` (4 N+1 → 1 batch)
  * `api/workflows/workflow_executor.py` — 7 cursor sites: workflow lookup,
    start node, edges, edges-by-handle, node fetch, email template, sub-group resolution

Wave 2 (6 sites):
  * `api/permissions/FetchUsers/fetch_shared_records.py:fetch_shared_records`
  * `api/emailsend/views.py:get_sendgrid_template_id_from_db`
  * `api/emailsend/views.py:save_sendgrid_template_id_to_db`
  * `api/emailsend/views.py:get_user_email_provider`
  * `api/telephony/views.py:telephony_route` (landing-number lookup)

See `docs/PHASE3_C_OPERATOR_NOTES.md` and
`docs/PHASE3_C_WAVE2_OPERATOR_NOTES.md`.

### `USE_DYNAMIC_GATEWAY` (4 sites — Phase 4.B)

  * `api/ORM/sqlFunctions/deleteSQLFunction.py:delete_data_sql` (wave 1)
  * `api/ORM/sqlFunctions/updateSQLFunction.py:_execute_update` (wave 2)
  * `api/ORM/sqlFunctions/createSQLFunction.py:_execute_insert` (wave 3)
  * `api/ORM/sqlFunctions/getQueryBuilder.py:_execute_select` (wave 4)

See `docs/PHASE4_B_WAVE{1,2,3,4}_OPERATOR_NOTES.md`.

---

## Tooling

### `python scripts/dispatch_status.py`

Reads the three flag env vars, prints their state and what each
controls. Use this on every staging instance to verify the flag
state matches what you intended.

```
$ python scripts/dispatch_status.py
==============================================
Dual-path dispatch flag status
==============================================
USE_ORM_FOR_PERMISSIONS  =  ON   (5 sites controlled)
USE_ORM_FOR_BL           =  ON   (17 sites controlled)
USE_DYNAMIC_GATEWAY      =  off  (4 sites controlled)

SOAK_LOG_LEVEL           =  INFO

Recommended rollout order:
  1. USE_ORM_FOR_PERMISSIONS  ✓ on
  2. USE_ORM_FOR_BL           ✓ on
  3. USE_DYNAMIC_GATEWAY      → next
```

### `python scripts/ddl_introspection.py compare`

Already-existing tool from Phase 4.A. Use before any production
flag flip to confirm the canonical Django models and the live
table shapes still match.

### Structural tests CI

`.github/workflows/structural-tests.yml` runs on every PR and on
push to `claude/**`. It catches drift between models / canonical
DDL / dispatch wiring before code ever reaches staging.

---

## Rollback authority

Any of the following is sufficient to roll back any flag at any
stage:

  * Anomalous error rate (>0.5% over 5 minutes)
  * p95 latency regression >50% on any dispatch site
  * A single uncaught exception from a dispatch wrapper that wasn't
    caught upstream
  * Customer-facing report of a bug that correlates with a recent
    flag flip

Rollback procedure:
  1. Set `<FLAG>=0` in the affected environment.
  2. The application picks up the new env on next request — no
     deploy required.
  3. File an incident ticket with the dispatch logs from the 10
     minutes before rollback.

---

## When the soak is complete

After all three flags reach Stage 5 (raw paths deleted), the work
is done:

  * 26 cursor sites permanently route through the ORM / gateway
  * The legacy raw-SQL paths are gone
  * Future hardening (statement timeouts, metric emission, retry
    policy) lands in the gateway and applies uniformly

At that point, the dispatch helper itself can stay — it's the
canonical pattern for any future cutover.

---

## Branch tree (where this runbook lives)

```
main
└── ...
    └── phase4-b-wave4-select-cutover
        └── soak-runbook-and-tooling  ← THIS BRANCH
```

After this branch, no new feature work should be opened until at
least one flag has reached Stage 4 in production. **The soak is
the project right now.**
