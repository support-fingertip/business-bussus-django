# Phase 3.B — Final ORM Wave (telephony / audit / misc)

Phase 3.B finishes the tenant-model layer started in Phase 2 Wave 2
and continued through Phase 3. After this branch lands, **48 of 49
setup tables in `default_tables.sql` are Django-modeled (98%
coverage)**.

**No new product surface.** Pure structural work — Django ORM
representations for the last group of per-tenant setup tables.

## What landed

### 13 new tenant-scoped Django models

| Wave | File | Models |
|---|---|---|
| 6 — integration / telephony / email | `api/tenant_models/integration.py` | `TelephonyConfig`, `LandingNumber`, `TelephonyUser`, `CallActivity`, `EmailProviderSetup`, `UserGmailToken`, `UserOutlookToken` |
| 7 — audit / history | `api/tenant_models/audit.py` | `AuditTrailTrack`, `FieldHistoryLog`, `FieldTrackingConfig` |
| 8 — misc | `api/tenant_models/misc.py` | `Task`, `Notification`, `SharedRecord` |

Plus:
- `api/models.py` re-exports for app discovery
- `api/migrations/0007_phase3b_tenant_models.py` — state-only migration
- `tests/orm/test_tenant_models_registry_parity.py` — `EXPECTED_DB_TABLES` extended from 35 → 48 entries
- `docs/UNSOURCED_DDL.md` — `org_company` documented as broken-DDL (every column commented out)

## Why 13 models, not 14

The 14th candidate was `org_company`. Its `CREATE TABLE` block in
`default_tables.sql` is **fully commented out** — every column line
including the closing `);` is `--`. The table doesn't exist in
production tenants. Documented for follow-up in
`docs/UNSOURCED_DDL.md`.

## Cumulative tenant-model coverage

| | Before Phase 3.B | After Phase 3.B |
|---|---|---|
| Tenant-scoped Django models | 35 | **48** |
| Setup tables modeled | 71% (35/49) | **98%** (48/49) |

The one remaining unmodeled `default_tables.sql` table is
`org_company` — see above.

## Wave-specific notes

### Wave 6 — integration / telephony / email

- **`EmailProviderSetup.cred`** is encrypted at rest (Phase 0.8). The
  model exposes it as `JSONField(null=True, blank=True)` because the
  legacy DDL types it `jsonb`, but the actual stored value is a
  Fernet-encrypted ciphertext string. **Callers must decrypt via
  `api.security.token_encryption.decrypt_token()` before use** —
  reading the raw column directly is a bug.
- `UserGmailToken` and `UserOutlookToken` are **legacy** — superseded
  by `EmailProviderSetup` but still created at tenant provisioning.
  New code should write through `EmailProviderSetup`.
- `TelephonyConfig.display_fields` and `disposition_values` are
  Postgres `TEXT[]` arrays. The model uses
  `django.contrib.postgres.fields.ArrayField(TextField())` to match.
  Querying with `__contains` / `__overlap` works as expected.

### Wave 7 — audit / history

- `AuditTrailTrack` is append-only — no soft-delete columns. Writes
  go through `api.ORM.AuditLogs.audit_trail_logs.log_audit`.
- `FieldHistoryLog.changed_at` is `TIMESTAMPTZ NOT NULL` — must be
  populated by the writer (no DB default).
- `FieldTrackingConfig` enforces a `unique_together` on
  `(object_name, field_name)` — both at the model and DB level (per
  `default_tables.sql`).

### Wave 8 — misc

- **`Task.name`** uses a sequence-based DDL default
  (`'TASK-' || LPAD(nextval('task_id_seq')::text, 6, '0')`). The
  model treats it as `CharField(max_length=16, blank=True)`; the DB
  fills it on INSERT. **Don't pass `name` from the application** or
  you'll bypass the sequence.
- **`SharedRecord` is the per-RECORD sharing table** — DO NOT confuse
  with `SharingRecord` (per-OBJECT default access level). The two
  table names sound nearly identical and they're NOT the same. See
  `api/tenant_models/sharing.py` module docstring for the full
  disambiguation.
- `SharedRecord.access_mask` is a bitfield (1=READ / 2=WRITE /
  4=DELETE / 8=SHARE). The model exposes the constants
  `ACCESS_READ`, `ACCESS_WRITE`, `ACCESS_DELETE`, `ACCESS_SHARE` for
  callers building masks.
- `Notification` has CHECK constraints in DDL on `channel`, `type`,
  `status`, `priority`. The model mirrors them as Django `choices`
  for form-validation parity.

## Pre-deploy checklist

- [ ] **`python manage.py migrate api`** in staging — confirm `0007`
      runs as a no-op (zero DDL). Adapt
      `scripts/verify_managed_false_migration.py` to call
      `sqlmigrate api 0007_phase3b_tenant_models`.
- [ ] **Django shell smoke test** against a populated tenant:
      ```python
      python manage.py shell
      >>> from django.db import connection
      >>> connection.cursor().execute("SET search_path TO tenant_alpha, public")
      >>> from api.tenant_models import (
      ...     TelephonyConfig, AuditTrailTrack, Task, Notification, SharedRecord
      ... )
      >>> list(TelephonyConfig.objects.all()[:3])
      >>> list(AuditTrailTrack.objects.all()[:3])
      >>> list(Task.objects.all()[:3])
      >>> list(Notification.objects.all()[:3])
      >>> list(SharedRecord.objects.all()[:3])
      ```
- [ ] **Run `pytest tests/orm/test_tenant_models_registry_parity.py`**
      — the EXPECTED_DB_TABLES dict is now 48 entries. The test asserts
      every one is in the registry.
- [ ] **`SharedRecord` smoke test** — query a known-shared record and
      verify the bitmask helpers (`ACCESS_READ`, etc.) return the
      expected boolean tests.
- [ ] **EmailProviderSetup decryption test** — read one row, decrypt
      `cred` via `api.security.token_encryption.decrypt_token()`,
      confirm the JSON parses back to a recognisable provider
      payload. (If this fails, `OAUTH_TOKEN_ENC_KEY` may be missing
      or wrong — see Phase 0.8 operator notes.)

## Same hard "do NOT" rules

1. **Don't flip `managed = True`** — Django would try to recreate the
   tables.
2. **Don't add `db_constraint=True` retroactively** — legacy DDL drift
   across tenants.
3. **Don't use the new models from Celery tasks** without first
   opening `with_tenant_schema()` (Phase 2 risk-mitigation work
   added this).
4. **Don't read `EmailProviderSetup.cred` raw** — always decrypt via
   `api.security.token_encryption.decrypt_token()`.
5. **Don't pass `Task.name`** from the application — let the DB
   sequence fill it.

## What's now unblocked

Phase 3.C wave 2 can now finish the BL files that were waiting on
these models:

- `BL/Listviews/GetListview.py` → `Task` model (was blocking)
- `api/emailsend/views.py` → `EmailTemplate` (already there) +
  `EmailProviderSetup` (NOW available)
- `api/notifications/notify.py` → `Notification` model
- `api/permissions/FetchUsers/fetch_shared_records.py` →
  `SharedRecord` model (replaces the raw cursor.execute against
  `shared_records`)
- Audit log readers/writers throughout the codebase →
  `AuditTrailTrack`, `FieldHistoryLog`, `FieldTrackingConfig`
- Telephony views (`api/telephony/views.py`) → `TelephonyConfig`,
  `LandingNumber`, `TelephonyUser`, `CallActivity`

Each of these is a candidate for Phase 3.C wave 2 dual-path conversion
behind the existing `USE_ORM_FOR_BL` flag.

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
                                    └── phase3-orm-waves
                                        └── phase3-c-bl-orm-cutover
                                            └── phase3-b-final-orm-wave  ← THIS BRANCH
```
