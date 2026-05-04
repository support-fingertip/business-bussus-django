# Tables with DDL outside source control

A few platform tables are queried by the running platform but, before
Phase 4.A, had no `CREATE TABLE` in any of the canonical DDL files
(`default_tables.sql`, `tables.sql`, `public/utils/organisation.py`,
or any app's `models.py`). They presumably exist in production
tenants because of:

- Manual DDL applied during initial deployment
- Earlier migration files that have since been cleaned up
- A provisioning step we haven't found

This file tracks the historic state and the resolution.

## ✅ `lead_capture` — RESOLVED in Phase 4.A

**Queried at:** `facebook/leadwebhook.py:159`

```sql
SELECT page_access_token, field_mapping, created_by_id
FROM lead_capture
WHERE lead_form_id = %s
LIMIT 1
```

**Original status:** No `CREATE TABLE` block anywhere; queried
against the `public` schema as a SHARED table (see
`api/ORM/sqlFunctions/getQueryBuilder.py:SHARED_TABLES`).

**Phase 4.A resolution:**
- Canonical DDL added to **`sqlfiles/shared_tables.sql`** (NOT
  `default_tables.sql` — `lead_capture` is shared/public, not
  per-tenant). Column shape inferred from
  `files/fields_inserts_no_id.sql:2206-2284` (the field registry —
  the strongest evidence we have for the canonical column list).
- `LeadCapture` Django model added in
  `api/tenant_models/shared.py` with `managed = False` so the ORM
  knows the table without trying to own its DDL.
- Migration `0009_phase4a_lead_capture.py` registers the model in
  Django state (state-only — no DDL run).

**Operator action remains:** before applying the new DDL to a
production public schema that already has a `lead_capture` table,
introspect the existing shape and reconcile any drift. The
canonical file is the *target*; production is *authoritative*. If
they disagree, update the canonical file.

```sql
-- On production:
SET search_path TO public;
\d lead_capture
-- Compare to sqlfiles/shared_tables.sql.
```

## ✅ `org_company` — RESOLVED in Phase 4.A

**Original status:** **DDL was broken in source control.** The
`CREATE TABLE IF NOT EXISTS org_company (...)` block in
`default_tables.sql` (around line 980) had every column line
commented out — including the closing `);`. The end result was that
either the statement was malformed and silently skipped, or it
attempted to create an empty-column table which Postgres rejected.

The `org_company` table did NOT exist in newly-provisioned tenants.

**Phase 4.A resolution:**
- DDL block in `default_tables.sql` un-commented (the column shape
  was always complete — every line was just `--`-prefixed).
- `OrgCompany` Django model added to
  `api/tenant_models/misc.py` with `managed = False`.
- Migration `0008_phase4a_org_company.py` registers the model in
  Django state.
- No code currently queries `org_company` — adding the model is
  purely defensive (newly-provisioned tenants will get the table;
  existing tenants are unaffected).

**Operator action:** for each existing tenant, decide whether to
apply the un-commented DDL retroactively. If yes, run a
per-tenant `CREATE TABLE IF NOT EXISTS` migration using the block
from `default_tables.sql:993-1023`. If no, leave existing tenants
alone — the model has `managed = False` so Django won't complain.

## Why we left these alone for Phase 2/3

The Phase 2 risk-mitigation work added the `lead_capture` row to
the registry (so the dispatcher whitelist accepts it) but **did
not** add DDL — adding DDL without knowing the canonical column
shape risked shadowing the real table next time a tenant was
provisioned. Same reasoning for `org_company` (we didn't know if
the broken-DDL block reflected the real shape or stale code).

Phase 4.A took both items on after the broader registry work was
complete and we had stronger evidence for both shapes (the field
registry insert blocks for `lead_capture`, the complete-but-
commented DDL for `org_company`).

## What's next: tenant introspection

The Phase 4.A operator tool `scripts/ddl_introspection.py` dumps
`information_schema.columns` per tenant and reports drift between
production and the canonical DDL. Run it before / after any
phased rollout to catch tables where the canonical files diverged
from the on-disk truth.
