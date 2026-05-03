# Phase 2.B — `cursor.execute` → ORM Cutover

Phase 2.B converts five raw-SQL functions in
`api/permissions/permissions.py` to dual-path implementations behind a
single feature flag. **Default is OFF** — operators flip the flag to
enable the ORM path after they've soaked enough traffic on the legacy
path to confirm the two are equivalent.

## What changed

| Function | Cursor sites converted | ORM model used |
|---|---|---|
| `get_object_details` | 1 | `PlatformObject` |
| `profile_has_admin_access` | 1 | `Profile` |
| `check_permission` | 1 | `ObjectPermission` |
| `get_field_metadata` | 1 (large JOIN) | `FieldPermission.select_related("field")` |
| `get_object_access_level` (new shared helper) | **3** sites in `get_permissions` / `patch_permission` / `delete_permission` collapsed | `SharingRecord` |

That's **7 cursor.execute calls** removed from the dispatch surface in
total (3 of them by extracting the shared helper).

What's intentionally NOT converted in this branch:

| Site | Why kept as raw SQL |
|---|---|
| `get_all_fields_for_table` | Reads `information_schema.columns` — not a tenant table |
| `_lock_record_for_update` | Generic dynamic-business-object table; covered by `api/ORM/dynamic` work in a later phase |
| `delete_permission` workflow-trigger SELECT | Generic dynamic-business-object table read |

## Feature flag

```bash
USE_ORM_FOR_PERMISSIONS=0   # default — raw SQL paths
USE_ORM_FOR_PERMISSIONS=1   # all five wrappers route to ORM paths
```

The flag is read on every dispatch call (no module-level caching), so
flipping it via env-var reload (or a config-management refresh) takes
effect for the next request without restart.

Per-call DEBUG log lines record which path executed:
```
permissions.check_permission: ORM path
permissions.get_object_details: raw-SQL path
```
Filter on these in your log dashboard to confirm rollout coverage.

## Rollout plan

### Stage 1 — soak in staging (1 week)
1. Deploy this branch with `USE_ORM_FOR_PERMISSIONS=0` (default).
   Code merges; behaviour unchanged.
2. Run integration tests / smoke flows. Confirm logs show `raw-SQL path`
   on every permission-check.

### Stage 2 — ORM enabled in staging (1 week)
3. Set `USE_ORM_FOR_PERMISSIONS=1` in staging only.
4. Run the same integration / smoke flows. Diff the application logs
   for any permission-related errors.
5. Run the permission-matrix tests (`pytest tests/permissions/`).
6. Spot-check production-like volume: load test 1000 concurrent users.

### Stage 3 — ORM enabled in one production tenant (1 week)
7. Enable the flag on a single canary tenant by overriding the env var
   in that tenant's deployment. (Today this means a separate deployment
   per tenant — Phase 5 introduces per-tenant feature flags.)
8. Watch the application logs and Sentry for the canary tenant. Look
   for any `permissions.*: ORM path` log lines paired with errors.

### Stage 4 — full rollout
9. Flip the flag globally. All permission checks now go through the
   Wave 2 ORM models.

### Stage 5 — delete the raw paths (1 release after stage 4)
10. Once two release cycles have passed with no ORM-path regressions,
    delete `_*_raw` impls and the `_orm_dispatch` indirection.
    Keep `get_object_access_level` as a regular function.

## Prerequisites

- **TenantSchemaMiddleware must be active in production** (Phase 2 ORM
  Wave 2). The ORM paths defensively re-issue `SET search_path` per
  call, but the middleware is the canonical source.
- **Phase 2 Wave 2 migration `0005_phase2_tenant_models` must be
  applied** in every tenant. The migration is state-only and runs as
  a no-op against the actual DB (verified by
  `scripts/verify_managed_false_migration.py`).
- **`pytest tests/permissions/` must pass** before each rollout stage.

## What to watch for

- **`OperationalError: relation "<table>" does not exist`** during
  ORM-path testing → indicates a tenant whose schema is missing one
  of the Wave 2 tables. Run `\dt` on the tenant schema to confirm.
- **Empty result sets where the raw path returned data** → schema
  drift between tenants (one tenant has the column, another doesn't).
  Check the model's field nullability.
- **`MultipleObjectsReturned`** on `.first()` → unique-constraint
  drift. The Wave 2 models declare `unique_together` but legacy DDL
  doesn't always enforce it. The ORM tolerates duplicates via
  `.first()` but a dashboard alert should fire.

## Rollback

Set `USE_ORM_FOR_PERMISSIONS=0` and redeploy. The raw-SQL paths are
unchanged from Phase 2.A, so the legacy behaviour is restored
immediately. No DB state is affected — both paths read the same tables.

## Tests added

- `tests/permissions/test_orm_dispatch.py` — flag truthiness, raw-vs-ORM
  routing, argument-passing contract, post-processing (especially the
  `get_field_metadata` row → dict transform that must work identically
  for both paths).
