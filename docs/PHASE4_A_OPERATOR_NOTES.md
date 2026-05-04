# Phase 4.A — DDL reconciliation

Phase 4.A closes the two known DDL gaps from
`docs/UNSOURCED_DDL.md` and adds tooling so future drift gets
caught before it bites.

**No new product surface.** Pure structural / operational work —
canonical DDL added, two new managed=False models registered,
operator tool to find drift, structural test to catch model↔DDL
inconsistencies in CI.

## What landed

### Two DDL gaps closed

| Gap | Resolution |
|---|---|
| `org_company` — every DDL line `--`-prefixed in `default_tables.sql` | DDL un-commented + `OrgCompany` model + migration 0008 |
| `lead_capture` — no DDL anywhere; queried from raw cursor | Canonical DDL in new `sqlfiles/shared_tables.sql` (public schema) + `LeadCapture` model + migration 0009 |

#### `org_company` resolution detail

The `CREATE TABLE IF NOT EXISTS org_company (...)` block in
`default_tables.sql` was complete in column shape — every line
just had a leading `--`. We un-commented the block as-is:

```sql
CREATE TABLE IF NOT EXISTS org_company (
    id VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('oRgN_', LEFT(gen_random_uuid()::text, 12)),
    company_name VARCHAR(255) NOT NULL,
    ...
    deleted_by_id VARCHAR(64) REFERENCES users(id) ON DELETE SET NULL
);
```

Newly-provisioned tenants will now get the table. Existing tenants
that have been running without it stay unaffected — the model is
`managed = False` so Django won't try to create the table during
migrate. **No code currently queries `org_company`** — adding it is
purely defensive infrastructure.

If you want existing tenants to also have `org_company`, run a
per-tenant `CREATE TABLE IF NOT EXISTS` migration using the block
from `default_tables.sql:993-1023`.

#### `lead_capture` resolution detail

Inferred column shape from
`files/fields_inserts_no_id.sql:2206-2284` (the field registry —
the strongest evidence we have for the canonical column list)
plus the runtime query at `facebook/leadwebhook.py:159` (which
confirms `page_access_token`, `field_mapping`, `created_by_id`,
and `lead_form_id` columns at minimum).

`lead_capture` is a SHARED table — lives in the `public` schema
and rows are scoped by `organization_id`, NOT by per-tenant
`search_path`. See `api/ORM/sqlFunctions/getQueryBuilder.py:26`
(`SHARED_TABLES = {"organizations", "lead_capture",
"user_login_history"}`). For that reason the canonical DDL went
into a NEW file `sqlfiles/shared_tables.sql` rather than
`default_tables.sql` (per-tenant) or `tables.sql` (per-tenant
business objects).

**Operator action** — before applying `sqlfiles/shared_tables.sql`
to a production public schema that may already have a
`lead_capture` table, introspect the live shape and reconcile
any drift:

```sql
-- On production:
SET search_path TO public;
\d lead_capture
-- Compare to sqlfiles/shared_tables.sql; if columns differ,
-- update the canonical file (production is authoritative).
```

### `LeadCapture` and `OrgCompany` models

Both are `managed = False` — Django doesn't run DDL for them.
Operators apply DDL by hand. Reasons we kept them unmanaged:

- `org_company` may not exist in production tenants today.
  Flipping `managed = True` would have Django try to create it on
  every fresh DB, which is fine, but it would also try to mirror
  any future schema changes — which is dangerous given the
  per-tenant DDL drift we already know exists.
- `lead_capture` likely exists in production with a divergent
  shape (we inferred ours from the field registry, not from the
  live DB). Flipping `managed = True` would have Django think
  the live shape is wrong and try to "fix" it.

Future Phase 4.B work (dynamic-object gateway cutover) does not
require flipping `managed = True` — the ORM works fine against
unmanaged tables.

### Tenant model coverage

| | Before Phase 4.A | After Phase 4.A |
|---|---|---|
| Tenant-scoped Django models | 48 | **49** (added `OrgCompany`) |
| Per-tenant setup tables modeled | 98% (48/49) | **100% (49/49)** |
| Shared/public tables modeled | 2/3 | **3/3** (added `LeadCapture`) |

### `scripts/ddl_introspection.py` — operator tool

CLI tool with three subcommands. Run from the repo root with
Django settings configured:

```bash
# Dump information_schema.columns for one tenant
python scripts/ddl_introspection.py dump --schema tenant_alpha

# Dump all tenants
python scripts/ddl_introspection.py dump > tenant_columns_2026Q1.json

# Compare one tenant against canonical Django model field types
python scripts/ddl_introspection.py compare --schema tenant_alpha

# Compare ALL tenants
python scripts/ddl_introspection.py compare

# Find consensus column shape per modeled table across tenants
python scripts/ddl_introspection.py consensus
```

Exit codes:
  - `0` — no drift (or dump completed)
  - `1` — drift detected
  - `2` — script could not run (DB connection failure, Django
    boot failure, etc.)

The `compare` subcommand uses a loose Django→Postgres type map
(`_DJANGO_TO_PG_TYPE` in the script). Missing entries surface as
"drift" the operator can either fix in the map or accept.

The `consensus` subcommand is the long-tail audit — for each
modeled table, it reports how many tenants have the table, and
for each column the most-common Postgres type plus the full
distribution. Useful for detecting the "one tenant is on the old
shape" case.

### `tests/orm/test_canonical_ddl_drift.py` — structural test

3 unit tests, no DB required:

1. **Every modeled table has canonical DDL** — fails if a model
   was added without a `CREATE TABLE` block in
   `default_tables.sql`, `tables.sql`, or
   `sqlfiles/shared_tables.sql`.
2. **Every model field has a canonical column** — fails if a
   field's `db_column` doesn't appear in the canonical DDL block
   for its table (catches "renamed column in model but not in
   SQL").
3. **DDL files exist and are non-empty** — sanity guard for the
   parser.

Tests skip cleanly when Django isn't installed (matching the
parity-test pattern). Wire into CI to catch drift on every PR.

### Migrations 0008 + 0009

Both are state-only (`SeparateDatabaseAndState` with empty
`database_operations`) — applying them runs zero DDL. They
register the new models in Django's state graph so the rest of
the codebase can import / query them through the ORM.

The existing `scripts/verify_managed_false_migration.py` only
verifies migration 0005. Future work: extend it to verify 0006-0009
all run as no-ops too.

## Pre-deploy checklist

- [ ] **`python manage.py migrate api`** in staging — confirm
      0008 and 0009 both run as no-ops (zero DDL).
- [ ] **Run `pytest tests/orm/test_tenant_models_registry_parity.py`**
      — `EXPECTED_DB_TABLES` is now 49 entries.
- [ ] **Run `pytest tests/orm/test_canonical_ddl_drift.py`** — all
      three tests should pass.
- [ ] **Run `python scripts/ddl_introspection.py compare`** against
      a populated staging environment — 0 drift expected for the
      48 Phase 2/3 tables. Drift on `org_company` is expected for
      tenants provisioned before Phase 4.A. Drift on `lead_capture`
      is the one to investigate before flipping ORM access on.
- [ ] **`sqlfiles/shared_tables.sql` smoke test** — apply to a
      throwaway local `public` schema, verify no syntax errors and
      the indexes are created.
- [ ] **For each existing tenant** that needs `org_company`,
      decide and apply the un-commented DDL.

## Same hard "do NOT" rules

1. **Don't flip `managed = True` on `OrgCompany` or `LeadCapture`**
   without first running `compare` against every production tenant.
   Drift exists; Django will try to "fix" it.
2. **Don't skip the production introspection step for `lead_capture`**
   before applying `sqlfiles/shared_tables.sql`. The field registry
   is our best evidence but it isn't authoritative.
3. **Don't add a new model without DDL** — `test_canonical_ddl_drift.py`
   will fail in CI, but it's better to land them together.

## Branch tree (current)

```
main
└── analyze-app-architecture-FL7ha
    └── ...
        └── phase3-b-final-orm-wave
            └── phase3-c-wave2-bl-cutover
                └── phase4-a-ddl-reconciliation  ← THIS BRANCH
```

## What's next: Phase 4.B

Phase 4.B is the dynamic-object gateway cutover — wire
`api/ORM/dynamic/` into `blcontroller.py`'s record CRUD so custom-
object queries stop going through raw cursors. Phase 4.A is a
prerequisite: the introspection tool is how we'll verify each
tenant's business-object tables (accounts, contact, leads, etc.)
match the canonical shapes before flipping the ORM path on.
