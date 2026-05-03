# Tables with DDL outside source control

A few per-tenant tables are queried by the running platform but have
no `CREATE TABLE` in any of the canonical DDL files (`default_tables.sql`,
`tables.sql`, `public/utils/organisation.py`, or any app's
`models.py`). They presumably exist in production tenants because of:

- Manual DDL applied during initial deployment
- Earlier migration files that have since been cleaned up
- A provisioning step we haven't found

This file tracks what we know so an operator can reconcile.

## `lead_capture`

**Queried at:** `facebook/leadwebhook.py:159`

```sql
SELECT page_access_token, field_mapping, created_by_id
FROM lead_capture
WHERE lead_form_id = %s
LIMIT 1
```

**Inferred column shape (minimum):**
- `lead_form_id` — Facebook lead form id (PK or unique?)
- `page_access_token` — long-lived FB page token
- `field_mapping` — JSON or text mapping from FB form fields to our object fields
- `created_by_id` — FK to public.users

**Operator action:** introspect a production tenant to capture the
canonical schema, add a `CREATE TABLE lead_capture (...)` block to
`default_tables.sql`, and check this entry off.

```sql
-- On a production tenant:
SET search_path TO <tenant_schema>;
\d lead_capture
-- Copy the resulting column list into default_tables.sql.
```

## Why we left these alone for Phase 2

The Phase 2 risk-mitigation work added the `lead_capture` row to the
registry (so the dispatcher whitelist accepts it) but **did not** add
DDL — adding DDL without knowing the canonical column shape risks
shadowing the real table next time a tenant is provisioned.

Phase 4's "DDL reconciliation" wave will dump every tenant's
`information_schema.columns`, find the consensus shape, and bring the
canonical DDL into source control.
