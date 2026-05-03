# Phase 2 Risk Mitigation — Operator Notes

Mitigations for the five risks called out in the Phase 2 review. No
new product surface; pure hardening.

| # | Risk | Mitigation |
|---|---|---|
| 1 | `managed=False` migration silently emits DDL | `scripts/verify_managed_false_migration.py` — CI assert |
| 2 | `apply_audit_fields` force-overwrite breaks legitimate admin flows | `allow_owner_override=True` keyword-only escape hatch |
| 3 | Object-name whitelist 404s in-house custom objects | `scripts/check_object_whitelist.py` — pre-deploy reconciliation |
| 4 | Celery / Channels run with the wrong `search_path` | `api/security/tenant_context.py` — `with_tenant_schema()` + `@tenant_schema_required` |
| 5 | `dashboard_folder` (singular) and `lead_capture` flags | Singular row deleted; `lead_capture` documented |

## Risk #4 — Tenant context for background work (the silent footgun)

### What changed

`api/security/tenant_context.py` is the new module. Two primitives:

```python
# Context manager — for arbitrary code (Channels consumers, mgmt commands)
from api.security.tenant_context import with_tenant_schema
with with_tenant_schema("tenant_alpha"):
    Profile.objects.get(...)   # auto-scoped

# Decorator — for Celery tasks
from api.security.tenant_context import tenant_schema_required
@shared_task
@tenant_schema_required()
def my_task(tenant_schema, *args, **kwargs):
    ...                         # body runs with search_path pinned
```

Re-entrant: nested `with_tenant_schema` calls restore the parent's
schema on exit, not `public`. The current schema is exposed via
`get_current_schema()`.

### Existing tasks updated

- `api/emailsend/tasks.py::process_due_email_campaigns` now
  **REQUIRES** `tenant_schema` as the first argument. The previous
  signature took only `request` and silently ran against `public`;
  callers (Celery beat, `apply_async`) must pass tenant explicitly.

- `api/emailsend/tasks.py::send_notify_email_verification` —
  documented as schema-agnostic (queries `public.users` with explicit
  qualification).

- `sf_integration/tasks.py::process_salesforce_sync` — entry point
  unchanged (reads from `public`-scoped `SalesforceSync`); a NOTE
  comment explains that downstream calls touching tenant-scoped tables
  must open their own `with_tenant_schema()`.

### Pre-deploy

- [ ] **Re-enable Celery beat schedule** for
      `process_due_email_campaigns` only via a per-tenant fan-out task.
      The current schedule in `version2/celery.py:31-33` is still
      commented out — uncomment **only** after wiring up a scheduler
      that enumerates `public.organizations` and calls
      `process_due_email_campaigns.delay(tenant_schema=org.schema)` per
      tenant.
- [ ] Confirm any in-house background scripts pin tenant before
      touching tenant tables (grep for direct `Profile.objects` /
      `ObjectPermission.objects` usage outside views).

## Risk #2 — `allow_owner_override` escape hatch

### What changed

`apply_audit_fields(data, mode='create', allow_owner_override=False, **kwargs)`

The flag is **keyword-only** — can't be smuggled in through a
`**request.data` spread.

When `True`:
- `owner_id` keeps the caller-supplied value (if present);
- `created_by_id` and `last_modified_by_id` are still force-overwritten
  — audit-trail integrity is preserved;
- An INFO-level log line records the transfer with the user who
  performed it (`extra={"transferred": [...], "by_user_id": ...,
  "new_owner_id": ...}`).

### Where to use it

Internal flows that legitimately reassign ownership:
- Bulk owner-transfer admin endpoint (Phase 4 candidate)
- CSV / data-import wizard
- Lead-conversion handoff (already creates owned-by-current records;
  override needed only for explicit handoff)

**Never** expose the flag through HTTP request kwargs. The current
permissions layer call sites do not propagate it.

### Pre-deploy

- [ ] Grep production logs for the new INFO line
      `"admin owner override applied"` after one week. Confirm every
      hit corresponds to a known admin/import flow.

## Risk #3 — Whitelist reconciliation

### Tool: `scripts/check_object_whitelist.py`

Run once per tenant before deploying Phase 2.A.6:

```bash
TENANT_SCHEMA=tenant_alpha python manage.py shell \
    -c "exec(open('scripts/check_object_whitelist.py').read())"
```

Output lists:
- Tables physically present in the tenant schema that would 404
  (need a registry row or RESERVED_ROUTES entry);
- Registry rows with no matching real table (probably stale);
- Real tables with no registry row (might or might not be a problem;
  check the 404 list above to be sure).

Exit code 0 = clean, 1 = there are tables that would 404.

## Risk #1 — Migration verification

### Tool: `scripts/verify_managed_false_migration.py`

Wire into CI:

```bash
DJANGO_SETTINGS_MODULE=version2.settings \
    python scripts/verify_managed_false_migration.py
```

Asserts that `manage.py sqlmigrate api 0005_phase2_tenant_models`
produces only header / `BEGIN` / `COMMIT` / blank / comment lines —
i.e. no actual DDL would run. Catches a future change that
accidentally flips `managed=True` or drops the
`SeparateDatabaseAndState` wrapper.

## Risk #5 — Two outstanding flags resolved

### `dashboard_folder` (singular)

**Resolution:** deleted. The actual table everyone uses is
`dashboard_folders` (plural; `default_tables.sql:356`,
`sqlfiles/mockdata/reports.sql:58`). Zero runtime queries against the
singular form. The plural form was already added in the Phase 2
ORM Wave 2 cleanup; the singular registry row was a leftover.

The `phase2_registry_cleanup.py` script + the corresponding
`phase2_registry_cleanup.sql` migration both pick this up
(`'dashboard_folder'` added to `DELETIONS_VESTIGIAL`).

### `lead_capture`

**Resolution: documented, not auto-fixed.** Used at
`facebook/leadwebhook.py:159` (`SELECT page_access_token,
field_mapping, created_by_id FROM lead_capture WHERE lead_form_id = %s`)
but no `CREATE TABLE` exists in any source-controlled file. The
table presumably exists per-tenant from a manual DDL apply that was
never committed.

`docs/UNSOURCED_DDL.md` captures the inferred shape and the operator
action: introspect a production tenant, capture the canonical schema,
and add `CREATE TABLE lead_capture (...)` to `default_tables.sql`. The
registry row was kept (not deleted) since the table is queried.

Phase 4's "DDL reconciliation" wave will sweep the entire schema
delta across tenants and bring all unsourced DDL into source control.

## Final state of the cross-check

| Verdict | Before risk-mitigation | After risk-mitigation |
|---|---|---|
| OK | 88 | 88 |
| OK — Django/Celery framework | 10 | 10 |
| OK — custom (dynamic DDL) | 8 | 8 |
| **GAP — DDL exists, registry row missing** | **1** | **1** *(facebookleadwebhooks — Django model commented out; pre-existing)* |
| **VESTIGIAL — registered but no DDL** | **2** | **1** *(`lead_capture` — documented in UNSOURCED_DDL.md)* |
