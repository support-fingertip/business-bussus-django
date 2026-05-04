# Phase 3.C Wave 2 — BL cutover for files unblocked by Phase 3.B

Phase 3.C wave 1 converted the BL files that hit Wave 3-5 setup tables.
Wave 2 finishes the cutover for the BL files that were waiting on the
Phase 3.B model wave (integration / audit / misc).

**No new product surface.** Pure dual-path cursor → ORM cutover behind
the existing `USE_ORM_FOR_BL` flag — same primitive, same flag, same
rollout playbook.

## What changed

### Three more files now have dual-path cutover

| File | Cursor sites converted | ORM models used |
|---|---|---|
| `api/permissions/FetchUsers/fetch_shared_records.py` | 1 site | `SharedRecord` (Phase 3.B Wave 8) |
| `api/emailsend/views.py` | **3 functions, 4 sites** | `EmailTemplate` (Wave 5) + `EmailProviderSetup` (Phase 3.B Wave 6) |
| `api/telephony/views.py` | 1 site (the bare `FROM landing_numbers`) | `LandingNumber` (Phase 3.B Wave 6) |

#### `fetch_shared_records.py` — `SharedRecord` ORM with bitmask post-filter

The legacy query used `(access_mask & %s) != 0` directly in SQL. Django
ORM has no portable bitwise-AND filter operator — the cleanest approach
is to read the `(user_id, object_name)` rows (a small fan-in by index)
and post-filter the bitmask in Python.

The existing CASE clause that returned `'read/write' | 'read'` is also
done in Python on the ORM path. Both paths produce the same shape:

```python
[{"record_id": ..., "owner_id": ..., "access_type": "read"|"read/write"}, ...]
```

The `expires_at IS NULL OR expires_at > now()` predicate maps to a
Django `Q(expires_at__isnull=True) | Q(expires_at__gt=now)` filter.

#### `emailsend/views.py` — three functions converted

| Function | ORM equivalent |
|---|---|
| `get_sendgrid_template_id_from_db(hash)` | `EmailTemplate.objects.filter(sendgrid_template_hash=hash).values_list("sendgrid_template_id", flat=True).first()` |
| `save_sendgrid_template_id_to_db(hash, id)` | `.filter(Q(hash__isnull=True) \| Q(hash=hash)).order_by("id").first()` then `.update(...)` |
| `get_user_email_provider(user_id)` | `EmailProviderSetup.objects.filter(user_id=user_id).values_list("provider", flat=True).first()` |

**`save_sendgrid_template_id_to_db` semantic note:** the legacy SQL
`UPDATE` had a subquery that picked the FIRST template row matching
`(hash IS NULL OR hash = ...)` ordered by id, and stamped that single
row. The ORM path mirrors that — `.order_by("id").first()` to find the
target id, then `.update(...)` on the singleton. The two-step makes the
behaviour explicit (only one row gets stamped, deterministically).

#### `telephony/views.py` — bare `FROM landing_numbers` query

Single site at `telephony_route` (line ~452). The lookup returns at
most one row by `(telephony_id, landing_number)`. Both paths return a
`list[dict]` so the callsite's `result[0]['group_id']` keeps working.

The legacy `run_query()` helper (which sets `search_path` only when
explicitly given a schema) is reused for the raw path; the ORM path
relies on `TenantSchemaMiddleware` having pinned the tenant for the
request.

### Files unchanged in this wave

| File | Reason not converted |
|---|---|
| `api/notifications/notify.py` | No cursor sites — already pure-Python; no migration needed |
| Audit log readers/writers | Need a deeper read of write paths — out of scope for the dispatch wiring; a follow-up wave will convert them with audit-trail-specific tests |
| `api/telephony/views.py` (other sites) | Most of the other queries hit `users`, `org_organizations`, `object`, `tabs` — public-schema tables, NOT per-tenant Wave 6 tables. ORM cutover for those belongs in a different wave (cross-schema query authority) |

## Feature flag

```bash
USE_ORM_FOR_BL=0   # default — raw SQL paths
USE_ORM_FOR_BL=1   # all wave-1 + wave-2 BL sites route to ORM paths
```

The flag is **the same one** as Phase 3.C wave 1. Flipping it enables
both waves at once. If a wave-2 site needs to be rolled back
independently, revert this branch — the wave-1 conversions live in
earlier commits and aren't touched here.

Per-call DEBUG log lines (new in this wave):
```
USE_ORM_FOR_BL.fetch_shared_records: ORM path
USE_ORM_FOR_BL.emailsend.get_sendgrid_template_id_from_db: ORM path
USE_ORM_FOR_BL.emailsend.save_sendgrid_template_id_to_db: raw-SQL path
USE_ORM_FOR_BL.emailsend.get_user_email_provider: ORM path
USE_ORM_FOR_BL.telephony.landing_number_lookup: ORM path
```

## Rollout plan

Same 5-stage pattern. If wave 1 has already soaked, wave 2 can follow
the same flag flip — there's no extra rollout step needed.

1. **Stage 1 — deploy with flag OFF** — code merges, behaviour
   unchanged.
2. **Stage 2 — enable in staging** — run targeted smoke tests:
   - Share a record with a user, hit a list endpoint that calls
     `fetch_shared_records`. Verify the shared row appears.
   - Send an email through SendGrid that triggers the template-cache
     path. Verify a SendGrid template id is stamped on a row.
   - Configure a user with `email_provider_setup`. Verify
     `get_user_email_provider` resolves it.
   - Place a Voxbay test call into a configured landing number and
     watch `telephony_route` route to a group user.
3. **Stage 3 — canary tenant**.
4. **Stage 4 — full rollout**.
5. **Stage 5 — delete raw paths** after two release cycles.

## What to watch for

- `SharedRecord.DoesNotExist` from per-record permission checks → the
  shared row probably has a stale `expires_at` from the DB clock skew;
  compare `now()` between Postgres and the Django process.
- `EmailTemplate` row not stamped after a send → ORM path's
  `Q(hash__isnull=True) | Q(hash=hash)` filter is more restrictive than
  the legacy SQL — verify there's at least one matching row before the
  send.
- `EmailProviderSetup` lookup returning `None` when raw returned a
  provider → row exists in a different tenant schema; check
  `TenantSchemaMiddleware` is pinning correctly for the request.
- `LandingNumber` lookup returning empty when raw returned one →
  `+1234567` vs `1234567` formatting drift on `landing_number` column.
  Both paths use exact-string match.

## Rollback

`USE_ORM_FOR_BL=0` and redeploy — raw paths are byte-identical to the
pre-cutover code. No data migration was performed; the flag is purely
read-path routing.

## Tests added

- `tests/permissions/test_orm_dispatch_bl_wave2.py` — 10 tests across
  the three converted modules.
  - `fetch_shared_records`: raw vs ORM routing, `_build_combined_mask`
    bitmask construction (read=1, write=2, delete=4, share=8,
    `read/write`=3, etc.).
  - `emailsend`: each of the three converted functions routes via
    the flag; `get_user_email_provider` raises when both paths return
    None.
  - `telephony`: the raw helper returns `run_query`'s list-of-dicts
    shape (so the callsite's `result[0]['group_id']` keeps working);
    the ORM helper wraps `.first()` in `[row]` or returns `[]`.

Tests use `pytest.importorskip("django")` and `django.setup()` so they
skip gracefully in stripped CI environments without Django installed
(matching the existing parity-test pattern).

## Same hard "do NOT" rules

The Phase 2.B and Phase 3.C wave 1 invariants still apply:

1. **Don't mask exceptions** — the dispatch helper deliberately
   re-raises from the ORM path. Bugs there must be loud.
2. **Don't bypass the flag** by importing `_*_orm` directly from
   another caller — go through the public function so logging and
   rollout-tracking stay consistent.
3. **Don't delete the raw helpers** until at least two release cycles
   after rollout; we want a quick rollback path.

## Cumulative coverage after Phase 3.C wave 2

| Layer | Cursor sites converted to dual-path |
|---|---|
| Phase 2.B (permissions.py) | 5 |
| Phase 3.C wave 1 (PageLayouts + workflow_executor) | 11 |
| Phase 3.C wave 2 (this branch) | 6 |
| **Total** | **22** |

## Branch tree (current)

```
main
└── analyze-app-architecture-FL7ha
    └── ...
        └── phase3-orm-waves
            └── phase3-c-bl-orm-cutover
                └── phase3-b-final-orm-wave
                    └── phase3-c-wave2-bl-cutover  ← THIS BRANCH
```
