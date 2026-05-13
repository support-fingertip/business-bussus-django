# Phase 8.A8 — Mass-assignment whitelist (operator notes)

**Status:** Pattern shipped; migration of remaining sites is incremental
**Branch:** `claude/sec-phase8-mass-assignment-whitelist`

## What this branch does in plain English

The SECURITY_AUDIT_REPORT graded this HIGH: many places in
`api/BL/blcontroller.py` build database inserts with patterns like:

```python
create_data = {**payload, 'created_by_id': user_id, 'created_date': now}
```

The `**payload` spread takes every key the user sent in the JSON
request body. The four system fields layered on top *correctly*
override their named keys — but any OTHER key the user invents
goes straight into the INSERT. An attacker can:

* Set `id` to a chosen value (collide with another tenant's row)
* Set `owner_id` to claim ownership of a record
* Set `organization_id` to another tenant (RLS catches it now, but
  defence in depth)
* Toggle `is_deleted` to undelete a soft-deleted row of their own
* Set `is_staff = true` to escalate privilege (in models that have it)

This branch ships the **fix pattern** + refactors **one representative
call site** (the `task` POST at ~line 2830) as the example. The
remaining call sites get migrated incrementally — the operator notes
below list them.

## What got built

| File | Plain-English purpose |
|---|---|
| `api/BL/allowed_fields.py` | The new module. Reads the per-tenant `fields` table for the allowed-write list per object, caches it (5-min TTL), and exposes `sanitize_create_payload` / `sanitize_update_payload`. |
| `api/BL/blcontroller.py` (one site) | `another_object == 'task'` POST now uses `sanitize_create_payload`. The `**payload` spread + system-field-layering pattern is replaced by the safe wrapper. |
| `tests/security/test_mass_assignment.py` | 25 tests: denylist enforcement, allow-list filtering, system-field layering, 7 classic attack payloads (id/owner_id/organization_id/is_deleted/is_staff/is_superuser/created_by_id), update vs. create flows. |

## The pattern, in 4 lines

**Before:**

```python
create_data = {
    **request_payload,           # ← attacker controls every key here
    'created_by_id': user_id,
    'created_date': now,
}
post_data_sql(object_name, create_data, ...)
```

**After:**

```python
from api.BL.allowed_fields import sanitize_create_payload

safe_data, _dropped = sanitize_create_payload(
    request_payload,
    schema=schema_from_request,
    object_name=object_name,
    user_id=user_id,
)
post_data_sql(object_name, safe_data, ...)
```

The wrapper:
1. Looks up the per-tenant `fields` metadata for `object_name`.
2. Drops every key in `request_payload` that isn't on the allow-list.
3. Drops every key in `SYSTEM_FIELDS_DENYLIST` (id, owner_id, organization_id, is_deleted, etc.) — even if it's on the tenant's allow-list (defence in depth against a misconfigured tenant).
4. Layers the platform's system fields (`created_by_id`, `last_modified_by_id`, `created_date`, `last_modified_date`) on top.
5. Returns `(safe, dropped)` so the caller can choose to silently drop OR send a 400 to the client.

## Call sites still to migrate

This branch refactored ONE representative site as the pattern (the
`task` POST around line 2830). Every other site in
`api/BL/blcontroller.py` that builds `create_data = {**something, ...}`
needs the same treatment. Inventory:

```bash
grep -n "\\*\\*create_data\\|\\*\\*data,\\|{\\*\\*payload" api/BL/blcontroller.py
```

Expected hits (line numbers approximate, will drift as the file changes):

* ~2841 — `task` POST — **DONE in this branch**
* ~2842 — modified_data for `task` (continuation)
* ~2875 — `file` POST
* ~3017 — `app` POST
* ~3079 — `dashboard_folders`
* ~3091 — `dashboard_component`
* ~3133 — `dashboard`
* ~3153 — `page_builder`
* ~3260 — `page_layouts`
* ~3272 — `path_builder`
* ~3275 — `user_group`
* ~3278 — `campaign`
* … plus another dozen across the 5,000-line file

Each migration is a small refactor (~5 lines), but there are 15-20 of
them and each needs eyes on it to confirm the `object_name` passed to
`sanitize_create_payload` matches what `fields` table expects. Budget
6-8h to do all of them after this branch lands.

## Migrating one site — checklist

For each remaining mass-assignment site:

1. Identify the `object_name` for the operation (it's usually
   `self.object_name`, but for child-object creates it can be the
   `another_object`).
2. Import the helper at the top of the file (or inline `from api.BL.allowed_fields import sanitize_create_payload`).
3. Replace the `{**payload, system_fields}` literal with a call to
   `sanitize_create_payload(payload, schema=..., object_name=..., user_id=..., now=...)`.
4. If the original code had additional defaults (e.g. `status = 'Open'`
   when the user didn't supply one), keep those — apply them AFTER
   the sanitisation pass.
5. Run the test suite for that object's flow.

## What happens during the migration window

A site that hasn't been migrated yet still has the audit's HIGH
finding. The pattern is in place, the helper is tested, and the
representative site demonstrates the correct shape. Each unmigrated
site is **independent** risk — they don't compound.

The `fields` metadata table + `is_modifiable` flag is the source of
truth for the allow-list. Per-tenant administrators control it; the
platform's denylist is the safety net for cases where a tenant
accidentally flags a system field modifiable.

## Cache + DDL invalidation

`get_allowed_create_fields` has a 5-minute TTL — sufficient for the
security fix. Per-DDL-path invalidation hooks (in
`ObjectManager.add_field` / `drop_field`) are a follow-up perf
optimisation: when a tenant admin adds a new custom field, the
cache invalidates immediately instead of waiting 5 minutes.

## Verification — what "working" looks like

After this branch ships, the `task` POST flow does this for a payload
with an injected `owner_id`:

```python
# Attacker POSTs:
{"subject": "Hi", "status": "Open", "owner_id": "user_attacker", "id": "rec_takeover"}

# DB INSERT executes with:
{
    "subject": "Hi",
    "status": "Open",
    "created_by_id": "user_legit",       # platform value
    "last_modified_by_id": "user_legit", # platform value
    "created_date": "2026-05-13 ...",    # platform value
    "last_modified_date": "...",         # platform value
}
# `owner_id` and `id` are DROPPED. A log line records them so monitoring
# can spot enumeration probing.
```

Try it in staging:

```bash
curl -X POST https://staging.bussus.com/api/leads/task \
    -H "Authorization: Bearer $JWT" \
    -d '{"subject":"x","status":"Open","id":"hijack","owner_id":"attacker"}'
```

Then in DB:

```sql
SELECT id, owner_id, created_by_id FROM task WHERE subject = 'x';
-- id should NOT be "hijack" (it should be a server-generated prefixed ID)
-- owner_id should NOT be "attacker"
-- created_by_id should be the JWT user's id
```

If the test passes, the pattern works. Migrate the remaining sites
the same way.

## Pre-deploy checklist

- [ ] All 25 tests in `tests/security/test_mass_assignment.py` pass
- [ ] Staging smoke test with attacker payload (above) → fields dropped
- [ ] No new INSERT errors in staging logs (the sanitiser is a strict subset of what used to land — if the user supplied a field that the metadata doesn't list, that field is now dropped instead of inserted, which can break INSERTs whose tables expect that column to be NOT NULL)
- [ ] (After staging soak) repeat for production
