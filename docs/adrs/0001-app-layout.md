# ADR 0001 — Keep flat `api/` layout (don't pre-split apps)

**Status:** Accepted
**Date:** 2026-05-03
**Phase:** 1 (Foundations)

## Context

The audit (Phase 0 master plan, "Cross-cutting themes / Wrong segmentation") flagged the `api/` Django app as a god-folder containing:

- BL handlers (24 files, including a 5,087-line `blcontroller.py`)
- Permissions layer (`api/permissions/`, 1,013 lines)
- ORM helpers (`api/ORM/`, 26 files)
- Cross-cutting modules (`workflows/`, `formulas/`, `notifications/`, `telephony/`, `emailsend/`, `pdfgen/`)
- Django app definition (`models.py`, `migrations/`, `apps.py`)

Phase 1 considered splitting `api/` into multiple Django apps along functional lines:

```
platform/    — object, fields, tables_metadata, columns_metadata
authz/       — profile, *_permissions, sharing_*, owd
ui/          — app, tabs, page_layouts, listviews, components
reporting/   — reports, dashboard, file
workflow/    — workflow, *_node, *_edge, flows
audit/       — audit_trails, field_history_log
```

## Decision

**Keep `api/` flat for the duration of the stabilization plan.** Do not split into multiple Django apps.

## Rationale

1. **Migration cost.** Splitting apps means moving every model, every `app_label`, every `db_table`, every migration history, every import path. With ~80 setup tables to migrate to Django ORM in Phases 2–4, doing the split simultaneously triples the regression surface.
2. **Foreign-key constraints across apps.** `Object` references `Profile`, `Profile` references `User`, `User` references `Organization`, `SharingRecord` references `Object`. Cross-app FKs work in Django but make migration ordering brittle.
3. **`AUTH_USER_MODEL = 'api.User'`** is hard-coded in `version2/settings.py:161`. Moving `User` to a different app requires either a fake-rename migration (high-risk on prod data) or keeping the legacy `api.User` alias, which defeats the split's tidiness.
4. **The actual structural problem isn't the Django app — it's the BL god-file.** Phase 4 splits `blcontroller.py` into per-domain handlers under `api/BL/object_handlers/`. That gives the team the navigation benefit they wanted from the split, without paying the migration cost.

## Consequences

**Accepted:**
- `api/` continues to host every Django model.
- New code organizes by sub-package (`api/BL/`, `api/ORM/`, `api/permissions/`, `api/security/`, `api/health/`, `api/ORM/dynamic/`) rather than by Django app.
- `api/security/` and `api/health/` are sub-packages, not separate Django apps.

**Deferred:**
- A future refactor (post-stabilization, post-product-feature-freeze) may split `api/` once the platform is stable and the team has bandwidth for migration-history archaeology.

## Alternatives Considered

| Option | Why rejected |
|---|---|
| Split now into `platform/authz/ui/...` | Triples Phase 2–4 migration risk; AUTH_USER_MODEL move is a one-shot data migration that's hard to roll back |
| Keep flat but rename internally only | Doesn't solve the navigation problem and adds churn |
| Move only `api/security/` to its own app | Pointless overhead — it has no models |
