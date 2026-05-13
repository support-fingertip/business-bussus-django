# Runbook — Quarterly tenant restore drill

**Status:** Skeleton (Phase 11 fills in real values)
**Cadence:** Quarterly
**Audience:** Platform engineering, DR lead

The purpose is to **prove** the backup-restore pipeline works for a
single tenant's data, end-to-end, in under the contracted RTO/RPO.

## Pre-conditions

- Backups have run successfully for at least 7 days.
- A "drill" target environment exists (parallel DB instance, isolated from prod).
- The picked tenant is informed (or pick a synthetic test tenant).

## Procedure

1. **Pick a tenant** — random selection from non-paying / internal test
   tenants; or pre-arranged with a customer for high-confidence drill.
2. **Snapshot expected state**
   - Record current `count(*)` from key tables in the tenant schema.
   - Record current `count(*)` from `public.users WHERE organization_id = $org_id`.
   - Record a few "canary" record IDs to spot-check after restore.
3. **Restore to drill environment**
   - From the most recent daily snapshot:
     ```bash
     ./scripts/restore_tenant.sh $org_id --to-env drill --snapshot $snapshot_id
     ```
   - Script restores: tenant schema, public-table rows for this org, S3 prefix, Redis namespace (best-effort).
4. **Apply RLS + role**
   - Apply the same provisioning DDL as a fresh tenant onboard, but skip
     data insertion since the restore has it.
5. **Verify**
   - `count(*)` matches the snapshot taken in step 2 (within ±1 row tolerance for in-flight writes).
   - Canary records visible and intact.
   - Cross-tenant probe still fails (the drill tenant's role can't read other schemas).
   - Application boots in drill env, admin can log in.
6. **Measure**
   - Wall-clock time from `restore_tenant.sh` start → "application boots in drill env".
   - Data freshness gap (snapshot timestamp vs. drill time).
   - Compare against contracted RTO/RPO. If slower → action item.
7. **Tear down**
   - Drop the drill database, role, S3 prefix.
   - File the drill report in `docs/drills/restore-YYYY-QQ.md`.

## Drill report template

```markdown
# Restore drill — YYYY Qn

- Tenant: $org_id
- Snapshot used: $snapshot_id (taken $timestamp)
- Restore started: $timestamp
- Application bootable: $timestamp
- **RTO measured:** Xh Ymin (target: 4h)
- **RPO measured:** Z hours (target: 1h)
- Anomalies: ...
- Action items: ...
```

## Failure modes — what to do if the drill fails

| Failure | Action |
|---|---|
| Snapshot doesn't exist or is corrupt | P1 — backup pipeline broken. Page on-call. |
| Restore times out / exceeds RTO | P2 — investigate; document gap; possibly upgrade DB or change snapshot strategy. |
| Data mismatch with snapshot expectations | P1 — backups are silently dropping data. Stop the world. |
| Cross-tenant probe succeeds in drill env | P1 — RLS / role policies broken. Stop the world. |
