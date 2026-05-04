# Phase 4.B wave 1 — dynamic-object gateway: DELETE cutover

Phase 4.B is the long-promised cutover of the dynamic-object CRUD
pipeline (custom-business-object tables) onto the
``api/ORM/dynamic/`` gateway built in Phase 1. Wave 1 is the
smallest, lowest-risk slice: **DELETE only**, behind the new
``USE_DYNAMIC_GATEWAY`` flag.

UPDATE / INSERT / SELECT come in subsequent waves (4.B.2-4) once
this one has soaked.

**No new product surface.** Pure plumbing — the legacy raw-cursor
DELETE path stays in place; a new gateway-backed DELETE path
runs alongside it; a flag picks which one executes.

## What changed

### Gateway: removed the redundant self-gate

Phase 1 had the gateway raise ``DynamicGatewayDisabled`` unless
``USE_DYNAMIC_GATEWAY=1``. That self-gate is gone — routing is
now the dispatch helper's job (same pattern as Phase 2.B and
3.C). The gateway is a regular library; callers reach it through
``api.permissions._orm_dispatch`` with
``flag="USE_DYNAMIC_GATEWAY"``.

What this means in practice:

  * Direct imports of ``dynamic_table`` no longer raise — they just
    work. Useful for tests and operator scripts.
  * The previous safety contract (don't accidentally enter an
    untested path) now lives in the dispatch helper. Same protection,
    one fewer place for it to drift.

### Gateway: ``_resolve_schema`` accepts string or request

The Phase 1 gateway insisted on a Django ``request`` object so it
could read ``request.tenant_schema``. The SQL function modules
(``deleteSQLFunction.py`` etc.) don't have a request — they get
the schema from kwargs and pass it down explicitly.

``_resolve_schema(request_or_schema)`` now accepts either:
  * a request object with ``.tenant_schema`` set (HTTP path)
  * a non-empty schema string (SQL function module path)

Empty/missing still raises ``PermissionError`` so a missing pin
fails loudly.

### deleteSQLFunction: dual-path

| Function | What it does |
|---|---|
| ``_delete_data_raw`` | Legacy raw-cursor path — byte-identical to pre-Phase 4.B (soft-delete probe via information_schema, then UPDATE or DELETE through ``psycopg2.sql.Identifier``). |
| ``_delete_data_orm`` | Same external behaviour, but the actual UPDATE / DELETE SQL goes through the gateway primitives. The information_schema probe still runs once up front to detect soft-delete columns (the gateway only knows the metadata registry, not the live column list). |
| ``delete_data_sql`` | Public function. Dispatches between the two via ``_orm_dispatch`` with ``flag="USE_DYNAMIC_GATEWAY"``. |

Both paths preserve the legacy contract:

  * raise if the table doesn't exist
  * raise if any record_id doesn't exist (ORM path keeps an
    explicit existence check; the gateway's ``update`` would
    silently no-op on a no-match, which would mask a bad client
    request)
  * soft-delete when ``is_deleted`` column exists and ``permanent``
    is False; hard-delete otherwise
  * stamp ``deleted_by_id`` and ``deleted_date`` if those columns
    exist
  * return ``{"success": True, "message": "Deleted N record(s)."}``

## Feature flag

```bash
USE_DYNAMIC_GATEWAY=0   # default — legacy raw-cursor path
USE_DYNAMIC_GATEWAY=1   # gateway-backed path (wave 1: DELETE only)
```

Independent of ``USE_ORM_FOR_PERMISSIONS`` (Phase 2.B) and
``USE_ORM_FOR_BL`` (Phase 3.C) — operators can roll out one
without touching the others.

Per-call DEBUG log lines (one per delete call):
```
USE_DYNAMIC_GATEWAY.deleteSQLFunction.delete_data_sql.leads: ORM path
USE_DYNAMIC_GATEWAY.deleteSQLFunction.delete_data_sql.contact: raw-SQL path
```

## Rollout plan

Same 5-stage pattern as the prior dual-path waves:

1. **Stage 1 — deploy with flag OFF** — code merges, behaviour
   unchanged.
2. **Stage 2 — enable in staging for 1 week** — exercise the soft-
   delete and hard-delete paths against a populated tenant. Watch
   logs for any ``ORM path`` exceptions; the dispatch helper
   doesn't mask them.
3. **Stage 3 — canary tenant** — flip the flag for one tenant.
4. **Stage 4 — full rollout**.
5. **Stage 5 — delete the raw path** after two release cycles.

## What to watch for

- ``Table 'X' does not exist`` from the ORM path when raw path
  succeeds → schema-pin drift; the gateway's ``_resolve_schema``
  is reading a stale value. Verify ``TenantSchemaMiddleware`` is
  pinning correctly for the request.
- ``UnknownObject: 'X' is a setup table`` → wave-1 caller passed
  a setup table (e.g. ``listviews``) into the gateway. Setup tables
  go through Django ORM, not the dynamic gateway. Bug in the
  caller; investigate the ``object_name`` value.
- Soft-delete columns that exist on the raw probe but not on the
  ORM probe → race condition (column added between calls). Will
  self-heal on next request.
- ``No data found with ID X to delete`` from ORM path when raw
  path didn't raise → search_path drift between the existence
  check and the gateway call (gateway opens a fresh cursor). Both
  use ``SET LOCAL`` so this should be impossible inside the same
  transaction; if seen, capture the trace.

## Rollback

``USE_DYNAMIC_GATEWAY=0`` and redeploy. The raw path is
byte-identical to the pre-cutover code.

## Tests added

- ``tests/permissions/test_orm_dispatch_dynamic_gateway.py`` — 10
  tests:
  - ``USE_DYNAMIC_GATEWAY`` flag independence (3) — setting other
    flags does NOT enable it; it routes correctly when set.
  - ``delete_data_sql`` dispatches to raw when flag off, to ORM
    when flag on, forwards arguments unchanged, and short-circuits
    on missing schema before either impl runs (3).
  - ``_resolve_actor_id`` adapts ``dict`` / object / ``None`` /
    dict-without-id input shapes (4).
- ``tests/orm/test_dynamic_gateway.py`` — refreshed: removed the
  ``DynamicGatewayDisabled`` tests (the self-gate is gone), added
  ``_resolve_schema`` tests covering both request and string input.

Tests use ``pytest.importorskip("django")`` so they skip cleanly
in stripped CI environments.

## Same hard "do NOT" rules

1. **Don't mask exceptions** — the dispatch helper deliberately
   re-raises from the ORM path. Bugs there must be loud.
2. **Don't bypass the flag** — call ``delete_data_sql`` from
   callers, not ``_delete_data_orm`` directly. Going through the
   public function preserves logging and rollout-tracking.
3. **Don't extend the gateway's API for this wave** — the gateway
   primitives are intentionally narrow. Anything that doesn't fit
   (cascading deletes, audit-trail emit, etc.) goes in the dual-
   path wrapper, not in the gateway.
4. **Don't enable USE_DYNAMIC_GATEWAY in production until staging
   has soaked DELETE for at least a week.** The gateway is new
   code; it's never been exercised at production scale.

## What's next: Phase 4.B wave 2

Wave 2 converts UPDATE (``updateSQLFunction.update_data_sql``).
That function is much larger (~28 cursor sites vs 7 here, ~630
lines of code) — same dispatch pattern but the parity surface is
bigger.

After wave 2: wave 3 INSERT, wave 4 SELECT (the largest, since
it's the build_query path that drives almost every read in the
app).

## Branch tree (current)

```
main
└── ...
    └── phase4-a-ddl-reconciliation
        └── phase4-b-dynamic-gateway-cutover  ← THIS BRANCH
```

## Cumulative dual-path coverage after wave 1

| Phase | Layer | Cursor sites converted |
|---|---|---|
| 2.B | permissions.py | 5 |
| 3.C wave 1 | PageLayouts + workflow_executor | 11 |
| 3.C wave 2 | fetch_shared_records + emailsend + telephony | 6 |
| 4.B wave 1 | deleteSQLFunction | 1 (the public function) |
| **Total** | | **23** |
