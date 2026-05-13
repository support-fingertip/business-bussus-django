# Runbook — Onboard a new tenant

**Status:** Skeleton (Phase 11 fills in real values)
**Audience:** Platform engineering, on-call

## Pre-conditions

- Customer has signed the contract + DPA.
- Customer has a unique `org_id` allocated (10-char prefix-suffix).
- Encryption KEK and per-environment secrets configured.

## Steps

1. **Allocate tenant identifiers**
   - `org_id` (assigned by sales tooling)
   - `database_schema` (slugified `<org_id>` or `tenant_<org_id>`)
   - `tenant_<schema>_role` (Postgres role name)

2. **Create the public-schema row**
   ```sql
   INSERT INTO public.organizations (id, name, database_schema, is_active, created_date)
   VALUES ($org_id, $customer_name, $schema_name, TRUE, now());
   ```

3. **Provision DDL**
   ```bash
   ./scripts/provision_customer.sh $org_id $schema_name
   ```
   This script (created in Phase 4):
   - `CREATE SCHEMA $schema_name`
   - `CREATE ROLE tenant_${schema_name}_role NOLOGIN`
   - Grants USAGE + table privileges only on this tenant's schema
   - Grants narrow access to whitelisted shared tables
   - Applies `sqlfiles/objects.sql`, `setup_fields.sql` into the new schema
   - Applies RLS policies on `lead_capture` etc. for this tenant

4. **Derive per-tenant DEK**
   - `python manage.py provision_tenant_dek $org_id`
   - Stores the wrapped DEK reference in secrets manager.

5. **Create the customer admin user**
   ```bash
   python manage.py create_tenant_admin $org_id --email admin@customer.com
   ```
   - Emails the admin a one-time signup link.

6. **Set up Redis namespace**
   - No action needed if using prefix wrapper; verify via `tenant_cache.tenant_get(ctx, "_provision_test")`.

7. **Set up object storage**
   - Create `s3://prod-bussus/tenants/$org_id/` prefix.
   - Apply IAM policy template restricting writes to that prefix.

8. **Verify isolation**
   - Run cross-tenant probe: as `tenant_${schema}_role`, attempt `SELECT 1 FROM <other_tenant_schema>.<any_table>` → must fail with `permission denied`.
   - Run RLS probe: set `app.current_org_id` to a different org, query `public.users` → must return 0.

9. **Smoke test**
   - Log in as the new admin in staging-like env.
   - Create a record, read it back, delete it.

10. **Announce**
    - Tag the customer's record in monitoring/alerting tools.
    - Add to status-page subscriber list if applicable.

## Rollback

If onboarding fails mid-way:
- `python manage.py rollback_tenant $org_id` (created in Phase 11):
  drops schema, role, S3 prefix, secrets-manager entries, public-org row.

## Verification checklist

- [ ] `public.organizations` row exists with `is_active=TRUE`
- [ ] Schema exists with all setup tables seeded
- [ ] `tenant_<schema>_role` has expected grants (compare against template)
- [ ] DEK is provisioned and unwrappable
- [ ] Storage prefix exists with correct IAM
- [ ] Cross-tenant probe failed (as expected)
- [ ] Admin can log in
