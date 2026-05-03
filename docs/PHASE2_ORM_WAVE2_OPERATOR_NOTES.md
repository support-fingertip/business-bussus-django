# Phase 2 ORM Wave 2 — Operator Notes

ORM Wave 2 introduces Django models for 12 of the per-tenant setup
tables (the authorization-layer ones plus the platform-metadata
backbone). Nothing in production behaviour changes yet — this is the
foundation Phase 2.B (the cursor.execute → ORM cutover) builds on.

## What landed

| Component | Files |
|---|---|
| `TenantSchemaMiddleware` — sets `search_path` per request after schema_authority pins the tenant | `api/security/tenant_schema_middleware.py` |
| 12 unmanaged Django models | `api/tenant_models/` (5 files) |
| Re-export from `api/models.py` so the `api` app discovers them | `api/models.py` |
| State-only migration (no DDL) | `api/migrations/0005_phase2_tenant_models.py` |
| Wire-up in `settings.MIDDLEWARE` | `version2/settings.py` |
| Parity tests + middleware tests | `tests/orm/test_tenant_models_registry_parity.py`, `tests/security/test_tenant_schema_middleware.py` |
| ADR-0003 explaining the `managed = False` pattern | `docs/adrs/0003-tenant-models-managed-false.md` |

## Models added

| Python class | `db_table` | Purpose |
|---|---|---|
| `PlatformObject` | `object` | Object registry (renamed from `Object` to avoid Python builtin clash) |
| `Field` | `fields` | Field/column definitions per object |
| `Profile` | `profile` | Per-tenant profiles |
| `Role` | `roles` | Role hierarchy |
| `UserGroup` | `user_group` | Named user groupings |
| `UserGroupUser` | `user_group_users` | Junction (group ↔ user) |
| `ObjectPermission` | `object_permissions` | Per-(object, profile) CRUD grants |
| `FieldPermission` | `field_permissions` | Per-(field, profile) field-level grants |
| `TabPermission` | `tab_permissions` | Per-(object, profile) tab visibility |
| `AppPermission` | `app_permissions` | Per-(app, profile) visibility |
| `SharingRecord` | `sharing_records` | Per-object sharing posture |
| `OrganizationWideDefault` | `owd` | Org-wide default access table |

## Pre-deploy checklist

- [ ] Run `python manage.py migrate api` in staging — confirm migration
      `0005_phase2_tenant_models` applies as a no-op (it should NOT
      run any DDL against your tenant tables).
- [ ] Hit any authenticated endpoint and confirm logs show
      `SET search_path TO <tenant>, public` running once per request.
      (Enable `LOG_LEVEL=DEBUG` temporarily, or add a one-line `print`
      to `TenantSchemaMiddleware.process_view` for the smoke test.)
- [ ] Run `pytest tests/orm/test_tenant_models_registry_parity.py` —
      this catches model-vs-registry drift early.
- [ ] Verify a Django shell query works against a tenant:
      ```python
      python manage.py shell
      >>> from django.db import connection
      >>> cursor = connection.cursor()
      >>> cursor.execute("SET search_path TO tenant_alpha, public")
      >>> from api.tenant_models import Profile
      >>> list(Profile.objects.all()[:5])
      ```

## Important: what NOT to do

1. **Do NOT flip any of these models to `managed = True`.** The
   per-tenant schemas already exist; Django doesn't own them. Running
   `manage.py migrate` with `managed=True` would attempt to recreate
   the tables, which fails in any tenant that already has them.

2. **Do NOT add FK `db_constraint=True` retroactively.** The legacy
   hand-rolled DDL doesn't always create FK constraints consistently;
   declaring strict constraints would mis-validate against drifted
   tenants. Phase 4 will audit and re-establish FK constraints
   centrally.

3. **Do NOT use these models from background workers without
   pinning the schema first.** Celery tasks must explicitly call
   `connection.cursor().execute("SET search_path TO %s, public", [schema])`
   (or use a future `with_tenant_schema()` context manager — Phase 2.B
   adds this) before issuing ORM queries. The middleware ONLY pins
   inside the request lifecycle.

## New environment variables

None. ORM Wave 2 introduces no new env vars.

## Known follow-ups (Phase 2.B and later)

- **Phase 2.B — cursor.execute → ORM cutover.** Replace the raw-SQL
  calls in `api/permissions/permissions.py` (9 sites) with ORM queries
  using these models. Feature-flagged behind `USE_ORM_FOR_PERMISSIONS=1`
  with byte-for-byte regression tests.
- **Phase 2.C — Wave 2 of Wave 2** ✶ (TODO):
    - `PermissionSet` and `PermissionSetAssignment` (richer than `Profile`)
    - `SharingRule` (criteria-based sharing — distinct from `SharingRecord`)
    - `UserGroupProfile` and `UserGroupPublicGroup` (registry gaps)
- **Phase 3 — UI / layout / reporting / workflow waves.** ~30 more models.
- **Phase 4 — DDL reconciliation.** Compare per-tenant schemas, surface
  drift, decide whether to add the missing FK constraints, indexes, etc.
- **Background-task tenant context.** Celery tasks currently rely on
  callers passing schema in kwargs. Add a `@with_tenant_schema(schema)`
  decorator that calls the same `SET search_path` sequence.

## Pattern reference for Phase 2.B authors

```python
# Old:
with connection.cursor() as cur:
    cur.execute("SET search_path TO %s", [schema])
    cur.execute(
        sql.SQL("SELECT 1 FROM object_permissions WHERE object_id = %s "
                "AND profile_id = %s AND {} = TRUE").format(sql.Identifier(action)),
        [object_id, profile_id],
    )
    has_perm = cur.fetchone() is not None

# New (assumes TenantSchemaMiddleware has pinned the request):
from api.tenant_models import ObjectPermission

# Action whitelist still applies — see VALID_PERMISSION_TYPES.
has_perm = ObjectPermission.objects.filter(
    object_id=object_id, profile_id=profile_id,
    **{action: True},
).exists()
```

The whitelist gate (`VALID_PERMISSION_TYPES`) stays — it now protects
the kwargs spread instead of the SQL identifier.
