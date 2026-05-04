# ADR 0003 — Tenant-scoped Django models with `managed = False`

**Status:** Accepted
**Date:** 2026-05-03
**Phase:** 2 (ORM Wave 2)

## Context

The platform is multi-tenant via PostgreSQL schemas: every tenant has
its own schema containing copies of ~80 setup tables (`profile`,
`object_permissions`, `field_permissions`, `sharing_records`, …). The
audit identified two structural problems:

1. **No Django ORM representation** for these tables — every read/write
   goes through hand-rolled raw SQL with inconsistent identifier
   validation, partial transaction handling, and no cross-call type
   safety.
2. **The dynamic-business-object tables** (custom objects defined at
   runtime via the `fields` metadata) genuinely cannot be Django
   models — their schemas don't exist at import time.

Phase 2 ORM Wave 2 needs to introduce ORM models for the **first** set
without disturbing the **second**, and without trying to take over
schema management for tables Django didn't create.

## Decision

Introduce Django models for the per-tenant setup tables under
`api/tenant_models/`, **all marked `Meta.managed = False`**.

Routing to the right tenant happens through a new
`TenantSchemaMiddleware` that runs `SET search_path TO <tenant>, public`
on the connection after Phase 1's `schema_authority.pin_request_tenant`
has resolved the request. Subsequent ORM queries
(`Profile.objects.get(...)`, `ObjectPermission.objects.filter(...)`)
automatically scope to the right tenant.

## Why `managed = False`?

| Concern | Resolution |
|---|---|
| Django wants to `CREATE TABLE` on first migrate | `managed = False` short-circuits this |
| Tables already exist in production tenants | `SeparateDatabaseAndState` migration wrapping `state_operations=[CreateModel(...)]` and `database_operations=[]` registers the model state without running DDL |
| Schema differs slightly across tenants (legacy DDL drift) | Models declare nullable / generous fields; per-tenant deltas are ignored when `managed=False` |
| Future schema changes | DO NOT flip to `managed=True`. Instead, run schema changes via the legacy `api/ORM/setup/ObjectManager/` flow (which already iterates tenants) and update the model fields in lockstep. |

## Why a separate `api/tenant_models/` package, not `api/models.py`?

`api/models.py` already holds the public-schema models (`Organization`,
`User`, `SessionLog`, `UserLoginHistory`). Mixing them with 12+ tenant-
scoped models would obscure which schema each model targets — a
real footgun when reading code.

The package re-exports each model from `api/tenant_models/__init__.py`
and `api/models.py` re-exports them again so Django's model discovery
under `INSTALLED_APPS = ['api', ...]` picks them up. Per ADR-0001 we do
NOT split into a separate Django app.

## Why `db_constraint=False` on every FK?

The legacy hand-rolled DDL doesn't always create FK constraints
consistently across tenants. A Django model declaring a strict FK
would pass validation against tenants that have the constraint and
silently mis-validate against ones that don't. `db_constraint=False`
keeps the relationship known to the ORM (for `select_related` /
`prefetch_related`) without imposing it at the DB level.

This is acceptable because the ORM enforces relationship integrity at
the application level and the schema-authority middleware ensures
queries are tenant-scoped. The audit-flagged orphan-row class of bug
will be addressed in Phase 4 (data migration + `CHECK` constraints).

## Why route through `search_path` instead of an explicit `using=` per query?

Django supports per-query database routing via the `using` parameter,
but that means every callsite must explicitly know the tenant —
exactly the antipattern the schema_authority work is replacing. Setting
`search_path` once per request keeps callsites tenant-naive: they call
`Profile.objects.get(id=...)` and the right tenant's table is queried.

The middleware resets `search_path TO public` on `process_response` so
the next caller picking up the same connection from the pool starts
clean.

## Migration plan for production

1. Deploy this branch; the `0005_phase2_tenant_models` migration runs
   as a no-op against the database (state-only).
2. The `TenantSchemaMiddleware` starts setting `search_path` on
   authenticated requests; existing raw-SQL paths continue to work.
3. Phase 2.B (next session) replaces `cursor.execute` calls in
   `api/permissions/permissions.py` with the equivalent ORM queries
   using the new models. This is gated by feature flags and
   regression-tested against the legacy paths.
4. Phase 4 audits & merges legacy duplicates (`sharing_records` vs
   `owd`), reconciles cross-tenant DDL drift, and decides whether to
   re-establish FK constraints.

## Alternatives Considered

| Option | Why rejected |
|---|---|
| `managed = True` and let Django own DDL | Existing production schemas would conflict; rolling out per-tenant migrations atomically across many schemas is its own subproject |
| Use `django-tenants` library | Already a dep but not actively used; adopting it requires reworking Postgres roles, search_path management, and migration tooling. Phase 5+ candidate |
| One big `api/models.py` mega-file | Hard to navigate, violates the single-responsibility intent of Phase 4 file-split |
| Separate Django app `api_tenant` | Forces FK relationships across apps (User → Profile, Organization → tenant tables) which adds migration ordering pain. Per ADR-0001 we keep apps flat. |
