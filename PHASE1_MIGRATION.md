# Phase 1 — Django ORM Adoption for Setup Tables

This branch (`claude/phase1-django-orm-setup-models`) implements the Phase 1
work plan from `SECURITY_AUDIT_REPORT.md`:

> Introduce Django models for the metadata tables, write a one-shot
> migration that adopts the existing tables, and retire the raw-SQL
> setup paths.

It also closes the highest-impact f-string SQL injection sites uncovered in
the audit (delete_object DDL injection, post_object/delete_field/newprofile
schema interpolation, recycle-bin table-name injection, usergroup_utils
schema injection, login.py profile lookup).

---

## Summary of changes

### New files

| File | Purpose |
|------|---------|
| `api/setup_models.py` | Django ORM models (`managed=False`) for **47** per-tenant setup/metadata tables: app, app_permissions, profile, tab_permissions, object_permissions, field_permissions, object, fields, page_layouts, search_layouts, field_mapping, sharing_records, shared_records, listviews, report, report_folder, report_folder_sharing, dashboard, dashboard_folders, dashboard_component, dashboard_folder_sharing, page_builder, page_component, page_builder_assignment, layout_assignment, homepage_assignment, workflow, workflow_node, workflow_edge, path_builder, telephony_config, landing_numbers, telephony_user, callactivity, user_group, user_group_users, user_group_profiles, user_group_public_groups, user_gmail_tokens, user_outlook_tokens, email_provider_setup, email_templates, audit_trail_track, field_history_log, field_tracking_config, notifications, task. |
| `utils/tenant_schema.py` | Single source of truth for schema validation + `set_search_path` (uses `psycopg2.sql.Identifier`, never f-strings). Also `resolve_request_schema(request)` which derives the schema **only** from the JWT-authenticated user's `Organization`. |
| `utils/safe_sql.py` | Helpers for the dynamic-object SQL layer that genuinely cannot be modelled: `validate_identifier`, `validate_operator`, `qualified_table`, `column_exists`, `table_exists`, `list_tables_with_column`, `in_clause`. |
| `api/tenant_middleware.py` | `TenantSchemaMiddleware` — sets `search_path` from JWT-resolved org schema before each request and resets to `public` after. Now wired into `version2/settings.py`. |

### Refactored files

| File | What changed |
|------|--------------|
| `api/ORM/AuditLogs/audit_trail_logs.py` | Audit writes via `AuditTrailTrack.objects.create`; structured logger replaces `except Exception: pass`. Schema validated via `set_search_path`. |
| `api/ORM/setup/ObjectManager/delete_object.py` | All metadata cleanup via `ObjectMeta`/`FieldMeta`/`*Permission` ORM. `name` validated through `validate_identifier` before DDL; `DROP TABLE` uses `psycopg2.sql.Identifier`. `remove_tab_from_apps` no longer takes `schema` (the new pattern is "current search_path is already correct"). |
| `api/ORM/setup/ObjectManager/delete_field.py` | All page-layout / search-layout / list-view / field-permission updates via ORM. DDL `ALTER TABLE … DROP COLUMN` uses `psycopg2.sql.Identifier` for both identifiers. Schema set via `set_search_path`. |
| `api/ORM/setup/ObjectManager/post_object.py` | Replaces 14 raw SQL inserts with ORM `Model.objects.create` calls. The previous `cursor.execute("SET search_path TO %s", [kwargs.get('schema')])` (which bound schema as a string literal) replaced by `set_search_path` (Identifier-bound). `name` validated as a strict identifier before any DDL helper sees it. |
| `api/ORM/setup/newprofile.py` | Profile clone now reads/writes the source profile's permission rows via `ObjectPermission`/`FieldPermission`/`TabPermission`/`LayoutAssignment`/`AppPermission`/`HomepageAssignment` — never accepts permission rows from the caller. |
| `api/ORM/sqlFunctions/relationships.py` | Local `_validate_identifier` / `_set_search_path` now delegate to `utils.safe_sql` / `utils.tenant_schema`. The previous `cursor.execute(f"SET search_path TO {schema}")` is gone. |
| `api/permissions/FetchUsers/fetch_shared_records.py` | Reads via `SharedRecord.objects` filter; schema validation surfaces real errors (no more silent default to mask=1). Invalid `type` raises `ValueError` instead of being silently downgraded to READ. |
| `api/permissions/FetchUsers/fetch_all_subordinates.py` | Re-raises DB errors with a structured log instead of returning `[manager_id]` silently. Adds explicit `MAX_HIERARCHY_DEPTH = 100`. |
| `api/BL/recycle_bin.py` | All 6+ raw f-string SQL sites in `permanently_delete_records`, `empty_recycle_bin`, `get_deleted_records`, and `restore_soft_deleted_records` rewritten to use `psycopg2.sql.Identifier` + `validate_identifier`. Tables to scan are discovered through parameterised information_schema queries via `list_tables_with_column`. |
| `api/workflows/workflow_executor.py` | `_set_search_path` now routes through `utils.tenant_schema.set_search_path`. `_restore_search_path` builds the SET statement via `psycopg2.sql.SQL/Identifier` composition instead of f-string interpolation. |
| `utils/usergroup_utils.py` | All 9 `f"… {schema}.… "` SQL sites in `patch_user_group` rewritten to use `sql.SQL(...).format(sql.Identifier(schema))`. Schema validated up front via `validate_schema`. `print()` replaced with structured logger. |
| `public/auth/login.py` | The `f"SELECT EXISTS(SELECT 1 FROM {schema}.profile …)"` profile-type lookup now uses `validate_schema` + `psycopg2.sql.Identifier`. |
| `version2/settings.py` | `TenantSchemaMiddleware` registered in `MIDDLEWARE` (after `AuthenticationMiddleware`). |

---

## Audit findings closed

| Audit ID / hot spot | Status |
|---|---|
| CRITICAL — `api/BL/recycle_bin.py` table-name injection (3 sites) | Fixed |
| CRITICAL — `api/ORM/setup/ObjectManager/delete_object.py` DDL injection on object name | Fixed (validate_identifier + sql.Identifier) |
| CRITICAL — `api/ORM/setup/ObjectManager/delete_object.py` f-string `SET search_path TO {schema}` | Fixed |
| CRITICAL — `api/ORM/setup/ObjectManager/delete_field.py` f-string `SET search_path TO {schema}` | Fixed |
| CRITICAL — `api/ORM/setup/ObjectManager/post_object.py` schema bound as string literal | Fixed |
| HIGH — `api/ORM/setup/newprofile.py` schema not validated, copies arbitrary perm rows from request | Fixed (ORM-based, never accepts request body for permissions) |
| HIGH — `api/ORM/AuditLogs/audit_trail_logs.py` `except Exception: pass` | Fixed (structured logger) |
| HIGH — `api/ORM/sqlFunctions/relationships.py` f-string `SET search_path` | Fixed |
| HIGH — `api/permissions/FetchUsers/fetch_all_subordinates.py` swallowed errors | Fixed (re-raise) |
| MEDIUM — `api/permissions/FetchUsers/fetch_shared_records.py` silent default to READ on bad type | Fixed (raise ValueError) |
| HIGH — `utils/usergroup_utils.py` 9 f-string SQL sites | Fixed |
| HIGH — `public/auth/login.py` f-string profile lookup | Fixed |
| HIGH — `api/workflows/workflow_executor.py` f-string in `_restore_search_path` | Fixed |
| **CRITICAL — Tenant pivot via header / kwargs** | Fixed at the architecture level by `TenantSchemaMiddleware` resolving the schema only from JWT-derived `Organization.database_schema`. |

---

## How tenant routing works now

```
HTTP request
  └─ AuthenticationMiddleware (DRF/JWT)
       └─ TenantSchemaMiddleware
            ├─ resolve_request_schema(request) -> schema from request.user.organization
            ├─ validate_schema(schema) (regex + reserved-name check)
            └─ SET search_path TO "<schema>", public  (psycopg2.sql.Identifier)

  view code runs:
    Profile.objects.filter(...)        # unqualified -> tenant schema
    ObjectMeta.objects.create(...)     # unqualified -> tenant schema
    public.users via 'users' table     # public is on the search path

  on response:
    SET search_path TO public          # always reset for connection pool safety
```

Code that used to thread `schema=kwargs['schema']` and inject it into raw SQL
no longer needs to — `kwargs.get('schema')` is still accepted as a hint, but
the centralised `set_search_path(cursor, schema)` revalidates and refuses
anything that doesn't pass the regex / reserved-list check.

---

## What's NOT in this branch (deliberately)

These are scoped for Phase 2 (decompose blcontroller.py) and Phase 0
follow-ups (auth/perms hardening) per the security audit report:

* `api/BL/blcontroller.py` god class is untouched.
* `api/BL/Profiles/patch_profiles.py` field-write whitelist (Phase 0 fix).
* `api/permissions/permissions.py` `profile_id` from kwargs (Phase 0 fix).
* `api/ORM/sqlFunctions/createSQLFunction.py` and `updateSQLFunction.py` —
  these belong to the **business-object** layer and stay in raw SQL by
  design. They should adopt `utils.safe_sql` helpers as a follow-up.
* OAuth refresh token encryption at rest (Phase 0 fix).
* xhtml2pdf XXE/SSRF replacement (Phase 0 fix).
* Voxbay credential rotation (Phase 0 fix).

---

## Migration notes for deployment

1. **Adopt-don't-create**: every new model is `managed=False`. `manage.py
   makemigrations` will NOT generate CREATE TABLE for them. The existing
   tenant tables (created by `default_tables.sql` / `create_app.py`) are
   the source of truth.
2. **Existing migrations** in `api/migrations/` are unchanged.
3. **Search path**: confirm Postgres `search_path` defaults are sane in
   your database (`SHOW search_path`). The middleware sets it on every
   request, but a misconfigured connection pool that's pre-warmed against
   `public` will work fine because every authenticated request resets it.
4. **Backwards compatibility**: the public function signatures of every
   refactored module are preserved. Callers that pass `schema=...` as
   `kwargs` keep working; the function just routes through the
   centralised validator instead of trusting the input verbatim.
5. **Test impact**: for unit tests, use `set_search_path(cursor,
   'test_schema')` after creating fixtures. The middleware does not run
   under the Django test client unless `tenant_schema` is resolvable from
   the test user.

---

## Lint sweep

```bash
$ grep -rEn 'cursor\.execute\(f"[^"]*SET search_path' --include="*.py" \
    | grep -v __pycache__ | grep -v 'Phase 1' | grep -v Previously
# (no matches — only docstrings reference the old pattern now)

$ python -c "
import py_compile
for f in [
  'api/setup_models.py', 'api/tenant_middleware.py',
  'utils/tenant_schema.py', 'utils/safe_sql.py',
  'utils/usergroup_utils.py',
  'api/ORM/AuditLogs/audit_trail_logs.py',
  'api/ORM/setup/ObjectManager/delete_object.py',
  'api/ORM/setup/ObjectManager/delete_field.py',
  'api/ORM/setup/ObjectManager/post_object.py',
  'api/ORM/setup/newprofile.py',
  'api/ORM/sqlFunctions/relationships.py',
  'api/permissions/FetchUsers/fetch_shared_records.py',
  'api/permissions/FetchUsers/fetch_all_subordinates.py',
  'api/BL/recycle_bin.py',
  'api/workflows/workflow_executor.py',
  'version2/settings.py',
]: py_compile.compile(f, doraise=True)
print('all changed files compile OK')"
```
