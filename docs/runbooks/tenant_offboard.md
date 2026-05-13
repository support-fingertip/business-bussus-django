# Runbook — Offboard a tenant

**Status:** Skeleton (Phase 11 fills in real values)
**Audience:** Platform engineering, on-call

## Pre-conditions

- Customer contract terminated OR data retention period expired.
- Legal hold check completed — confirm with counsel.
- DSAR (data export) delivered to customer if requested.

## Phase A — Disable (immediate, customer-facing)

1. `UPDATE public.organizations SET is_active = FALSE WHERE id = $org_id;`
2. Revoke active JWT refresh tokens for users in this org.
3. Add `org_id` to `OFFBOARDED_TENANTS` cache key set so middleware refuses requests.
4. Notify customer admin via email (template: "Account deactivated").

## Phase B — Data export (within 30 days)

If customer requested DSAR:

1. `python manage.py export_tenant_data $org_id --output s3://bucket/exports/$org_id/`
2. Encrypt the export with a one-time key shared out-of-band with the customer.
3. Deliver, confirm receipt, log delivery.

## Phase C — Retention window

- Default: retain data for the period specified in the contract (commonly 30-90 days).
- Backups age out per the backup retention policy.

## Phase D — Hard delete

After retention window expires (and after counsel approval if applicable):

1. **Application-layer**
   ```bash
   python manage.py purge_tenant $org_id --confirm-org-id $org_id --i-understand
   ```
   This script:
   - Drops the tenant schema (`DROP SCHEMA $schema CASCADE`).
   - Deletes rows from public tables (`users`, `lead_capture`, etc.) WHERE `organization_id = $org_id`.
   - Deletes Redis keys under `tenant:$org_id:*`.
   - Deletes object-storage prefix `tenants/$org_id/`.
   - Deletes secrets-manager entries for this tenant.
   - Drops `tenant_<schema>_role`.
   - Deletes the `organizations` row.

2. **Verify**
   - `SELECT count(*) FROM information_schema.schemata WHERE schema_name = $schema;` → 0
   - `SELECT count(*) FROM public.users WHERE organization_id = $org_id;` → 0
   - `SELECT count(*) FROM pg_roles WHERE rolname = $role_name;` → 0

3. **Backups**
   - Mark backups containing this tenant for accelerated expiry where allowed.
   - For backups in legal-hold buckets: tombstone with the offboard reference.

4. **Audit log**
   - Append a final audit entry to a central long-term store (NOT the tenant DB, which is gone).
   - Include: `org_id`, deletion-confirmed timestamp, operator id, contract reference.

## Verification checklist

- [ ] Tenant schema dropped
- [ ] Public rows for this org gone
- [ ] DB role dropped
- [ ] Redis keys gone
- [ ] Storage prefix gone
- [ ] Secrets entries gone
- [ ] Cross-tenant probe: confirm no orphan references in other tenants
- [ ] Final audit entry written
- [ ] Customer confirmation sent (if requested)
