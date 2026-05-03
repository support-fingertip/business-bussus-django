# Phase 2 — Operator Notes

Phase 2 closes the highest-leverage authz correctness gaps the audit
flagged. No user-visible features change. Six things land:

| # | Change | Risk |
|---|---|---|
| 2.A.1 | **Default-deny** on missing `sharing_records` row (was Public Read Write) | **Behavioural** — see migration note below |
| 2.A.2 | Hardcoded admin role list → `ADMIN_ROLES` constant (deduped `'superadmin'`) | None — same roles, cleaner |
| 2.A.3 | Whitelist for `permission_type` / `access_type` in permission check | None — typos now fail loudly |
| 2.A.4 | `apply_audit_fields` **force-overwrites** `owner_id` / `created_by_id` / `last_modified_by_id` | **Security** — see note |
| 2.A.5 | TOCTOU fix on update + delete: `SELECT … FOR UPDATE` inside `transaction.atomic()` | None — adds row lock |
| 2.A.6 | Per-tenant object-name whitelist in dispatcher | **Behavioural** — see migration note |
| 2.C | Per-request `statement_timeout` (30s default, 120s reports, 600s exports) | None — bounds runaways |

## ⚠️ Behavioural change — 2.A.1 default-deny

Before Phase 2: when an object had no row in `sharing_records`, it was
implicitly **Public Read Write** — every authenticated user could read
and write it. This was an audit-flagged default-allow drift.

After Phase 2: the same condition defaults to **Private**. Records are
only visible/writable to the owner, the owner's subordinates, and
explicit shares.

**Migration before deploy:**
```sql
-- Per tenant schema, identify objects relying on the old default and
-- explicitly opt them in (or leave Private if you wanted it):
SET search_path TO <tenant_schema>;
SELECT o.id, o.name, o.label
FROM object o
LEFT JOIN sharing_records sr ON sr.object_id = o.id
WHERE o.setup = FALSE AND sr.access_level IS NULL;

-- For each row that should remain Public Read Write:
INSERT INTO sharing_records (object_id, access_level)
VALUES ('<object_id>', 'Public Read Write');
```

If you're unsure, audit the list with the affected tenant before
deploying. The audit's recommendation is "default-deny is the correct
posture; treat anything that breaks under the new default as a finding."

## ⚠️ Security change — 2.A.4 force-overwrite

Before Phase 2: `apply_audit_fields` used `setdefault`, so a client
could POST `{"owner_id": "victim_user", ...}` and the platform would
honor it.

After Phase 2: `owner_id`, `created_by_id`, `last_modified_by_id` are
ALWAYS overwritten with the authenticated user's id. Any client-
supplied value for these fields is dropped, and a `WARNING` log line is
emitted with `extra={"clobbered": [...], "user_id": ...}`.

**Watch for:** legitimate admin tooling that previously relied on
client-supplied `owner_id` to assign ownership during data import. Such
tooling must now go through a dedicated owner-transfer endpoint (Phase 4
will add this). For the duration of Phase 2 it's safe to grep your
logs for `dropping client-supplied audit fields` to discover such
callsites and migrate them.

## ⚠️ Behavioural change — 2.A.6 object-name whitelist

The dispatcher now rejects `<str:object_name>` / `<str:another_object>`
URL captures that aren't on the per-tenant allowlist. Source of truth:

  - Static reserved BL routes (in `api/security/object_whitelist.py:RESERVED_ROUTES`)
  - The tenant's `object` registry rows (`setup=FALSE`)

Anything else returns **404** (deliberately not 403 — we don't confirm
table existence to anonymous probing).

**Watch for:** any custom integration that hits a route name not in
either bucket. Add it to `RESERVED_ROUTES` (if it's a BL command name)
or register it in the `object` registry (if it's a real custom-object
table).

If the metadata loader fails (DB outage etc.), the whitelist
intentionally **fails open** with a loud `ERROR` log rather than 404ing
every request — outages must not become availability incidents.

## New environment variables

| Name | Default | Purpose |
|---|---|---|
| `DB_STATEMENT_TIMEOUT_DEFAULT_MS` | `30000` | Per-request Postgres statement timeout for non-report endpoints |
| `DB_STATEMENT_TIMEOUT_REPORT_MS` | `120000` | Bucket for `/report` and `/dashboard` paths |
| `DB_STATEMENT_TIMEOUT_EXPORT_MS` | `600000` | Bucket for `/export` and `/data_export` paths |

Set any to `0` to disable that bucket's limit (incident-response
escape hatch — use sparingly).

## Pre-deploy checklist

- [ ] Run the `sharing_records` migration query above in **every** tenant
      schema; explicitly add Public Read Write rows for the objects you
      want to remain world-accessible.
- [ ] Grep production logs for `dropping client-supplied audit fields`
      after a 24-hour window post-deploy; confirm no legitimate
      admin/import tools are tripping the warning.
- [ ] Verify the object-name whitelist accepts your in-house custom
      objects — hit `/v2/api/<your_object_name>` against staging and
      confirm 200 / 401 (not 404).
- [ ] Confirm `statement_timeout` doesn't kill legitimate report queries:
      tail the slow-query log for 24 hours, raise the bucket if needed.
- [ ] Run `pytest tests/` — Phase 2 adds permission-matrix tests under
      `tests/permissions/`.

## Known follow-ups (later phases)

- Replace 70+ `kwargs.get('schema')` callsites with `request.tenant_schema`
  (Phase 2 wave 2).
- Begin Django ORM Wave 1/2 — `Object`, `Field`, `Profile`,
  `*Permission`, `SharingRecord`, `OWD` models. This eliminates the
  remaining `cursor.execute` calls in `permissions.py`.
- Bulk owner-transfer endpoint (so admins have an explicit way to
  reassign `owner_id` post-2.A.4).
- PgBouncer + read replicas (Phase 2.C wave 2 — needs ops coordination).
