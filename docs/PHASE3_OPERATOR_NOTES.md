# Phase 3 — ORM Waves 3–5 Operator Notes

Phase 3 extends the Phase 2 Wave 2 pattern (managed=False tenant
models) to three more functional groups: UI/layout, reporting, and
workflow. Plus two Wave 2 follow-up models that were missed
originally (`UserGroupProfile`, `UserGroupPublicGroup`).

**No new product surface.** This is purely structural — Django ORM
representations for tables that already exist per-tenant from
`default_tables.sql` + `public/utils/organisation.py` provisioning.

## What landed

### 25 new tenant-scoped Django models

| Wave | File | Models |
|---|---|---|
| 2 follow-up | `api/tenant_models/authz.py` | `UserGroupProfile`, `UserGroupPublicGroup` |
| 3 — UI / layout | `api/tenant_models/ui.py` | `App`, `PageLayout`, `SearchLayout`, `Listview`, `PageBuilder`, `PageComponent`, `PageBuilderAssignment`, `LayoutAssignment`, `HomepageAssignment`, `FieldMapping` |
| 4 — reporting | `api/tenant_models/reporting.py` | `Report`, `ReportFolder`, `ReportFolderSharing`, `Dashboard`, `DashboardComponent`, `DashboardFolder`, `DashboardFolderSharing`, `DashboardAssignment` |
| 5 — workflow | `api/tenant_models/workflow.py` | `Workflow`, `WorkflowNode`, `WorkflowEdge`, `PathBuilder`, `EmailTemplate` |

Plus:
- `api/models.py` re-exports the new models so the `api` app discovers them
- `api/migrations/0006_phase3_tenant_models.py` — state-only migration (`SeparateDatabaseAndState` + empty `database_operations`); applies as a no-op against a real DB
- `tests/orm/test_tenant_models_registry_parity.py` — `EXPECTED_DB_TABLES` extended to cover all 35 modeled tables (Wave 2 + Wave 3 + Wave 4 + Wave 5)

## Cumulative tenant-model coverage

| | Before Phase 3 | After Phase 3 |
|---|---|---|
| Tenant-scoped models | 10 | **35** |
| Setup tables in `default_tables.sql` | 49 | 49 |
| Coverage | 20% (10/49) | **71%** (35/49) |

Remaining 14 unmodeled `default_tables.sql` tables (all Wave 6+ candidates):
- Integration / telephony: `telephony_config`, `landing_numbers`, `telephony_user`, `callactivity`, `email_provider_setup`, `user_gmail_tokens`, `user_outlook_tokens`
- Audit / history: `audit_trail_track`, `field_history_log`, `field_tracking_config`
- Misc: `task`, `notifications`, `shared_records`, `org_company`

These come in Phase 3.B (a follow-up session).

## Pre-deploy checklist

- [ ] **`python manage.py migrate api`** in staging — confirm the migration applies as a no-op (zero DDL run). Use `scripts/verify_managed_false_migration.py` updated for `0006`:

  ```bash
  # Tweak the script to call `sqlmigrate api 0006_phase3_tenant_models`
  # then assert the same no-DDL invariant.
  ```

- [ ] **Django shell smoke test** against a populated tenant:

  ```python
  python manage.py shell
  >>> from django.db import connection
  >>> connection.cursor().execute("SET search_path TO tenant_alpha, public")
  >>> from api.tenant_models import Listview, Report, Workflow
  >>> list(Listview.objects.all()[:3])
  >>> list(Report.objects.all()[:3])
  >>> list(Workflow.objects.all()[:3])
  ```

- [ ] **Run `pytest tests/orm/test_tenant_models_registry_parity.py`** — confirms all 35 `db_table` names match the registry.

- [ ] **Audit FK constraint drift in production tenants** before Phase 3.B's
  `cursor.execute → ORM cutover` work. Some tenants have legacy DDL where
  FKs aren't enforced. Phase 3 declares all FKs with `db_constraint=False`
  for compatibility; Phase 4's DDL-reconciliation wave decides whether to
  re-establish them.

## Same hard "do NOT" rules as Wave 2

1. **Don't flip `managed = True`** — Django would try to recreate the
   tables.
2. **Don't add `db_constraint=True` retroactively** — legacy DDL drift
   will mis-validate.
3. **Don't use the new models from Celery tasks** without first
   opening `with_tenant_schema()` (Phase 2 risk-mitigation work
   added this for exactly this scenario).

## What enables next

After Phase 3 lands, the Phase 2.B-style `cursor.execute → ORM`
cutover can extend beyond `permissions.py`:

- BL files like `Reports/get_reports.py`, `Listviews/GetListview.py`,
  `PageBuilder/get_pagebuilder.py`, `dashboards/dashboard.py`,
  `PageLayouts/page_layout.py` — all fetch from tables now modeled
  here.
- Workflow execution (`api/workflows/workflow_executor.py`) can read
  `WorkflowNode` / `WorkflowEdge` via ORM instead of hand-rolled SQL
  in the executor.
- Email send (`api/emailsend/views.py`) can read `EmailTemplate` via
  ORM instead of `cursor.execute` against `email_templates`.

These are Phase 3.B candidates, gated by the same
`USE_ORM_FOR_PERMISSIONS` flag (or per-callsite flags as the team
prefers).

## Branch tree (current)

```
main
└── analyze-app-architecture-FL7ha
    └── phase0-security-stabilization
        └── phase1-foundations
            └── phase2-authz-correctness
                └── phase2-orm-wave2
                    └── phase2-risk-mitigation
                        └── phase2-b-orm-cutover
                            └── phase2-c-schema-kwarg-refactor
                                └── phase2-c-wave2
                                    └── phase3-orm-waves  ← THIS BRANCH
```
