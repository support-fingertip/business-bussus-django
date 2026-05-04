# Phase 4.B wave 2 — dynamic-object gateway: UPDATE cutover

Wave 1 routed DELETE through the gateway. Wave 2 does the same for
the actual UPDATE SQL site in
``api/ORM/sqlFunctions/updateSQLFunction.py``.

Same flag (``USE_DYNAMIC_GATEWAY``) — flipping it enables both
DELETE and UPDATE through the gateway at once. Independent rollback
per cursor site is not provided; revert this branch if UPDATE needs
to roll back without DELETE.

**No new product surface.** Pure plumbing.

## Why "unchecked"

The legacy ``updateRawSQL`` mixes user-supplied fields with
system-stamped columns (``last_modified_by_id``,
``last_modified_date``, audit-trail bookkeeping). Some of those
columns aren't always in the per-tenant ``fields`` registry, so the
gateway's standard ``update()`` (which validates every patch key
against the registry) would reject them.

Wave 2 adds **``dynamic_table.update_unchecked()``** — same SQL
composition (``sql.Identifier`` for the table and every column
name, parameterised values), same identifier validation
(``validate_object_name`` + ``validate_field_name`` per key), but
no registry-membership check.

This is a deliberate, narrow bypass for system writes. Anything
that doesn't already reach the application's UPDATE pipeline goes
through the standard ``update()`` and gets full registry
enforcement.

## What changed

### `dynamic_table.update_unchecked()` — new gateway primitive

```python
def update_unchecked(
    request_or_schema,        # request OR schema string
    object_name: str,         # validated identifier
    *,
    record_id: str,           # required, non-empty
    patch: dict,              # required, non-empty
) -> int:                     # affected row count
```

Validates identifiers (object name + every patch key), composes
SQL via ``psycopg2.sql.Identifier``, runs in its own
``transaction.atomic`` (a savepoint inside any outer transaction).

### `updateSQLFunction._execute_update()` — dispatch chokepoint

The actual UPDATE statement in ``updateRawSQL`` (was at line ~573,
unchanged in shape) is now extracted into ``_execute_update``,
which dispatches between two helpers:

| Helper | What it does |
|---|---|
| ``_execute_update_raw(cursor, ...)`` | Byte-identical to pre-wave-2: uses the caller's existing cursor + outer transaction, composes the SET clause via ``sql.Identifier``. |
| ``_execute_update_orm(schema, ...)`` | Calls ``dynamic_table.update_unchecked``. Opens a fresh cursor on the same connection — Postgres savepoints live at the connection/transaction level, so the caller's outer ``transaction.atomic`` + ``SAVEPOINT sp_update_<idx>`` flow still rolls back this write on error. |

The public ``updateRawSQL`` is unchanged at the surface — same
arguments, same ``report`` shape. Only the actual UPDATE SQL
emission is dispatched.

## Feature flag (unchanged)

```bash
USE_DYNAMIC_GATEWAY=0   # default — legacy raw-cursor path
USE_DYNAMIC_GATEWAY=1   # gateway-backed path (waves 1+2: DELETE + UPDATE)
```

Per-call DEBUG log lines (new in this wave):
```
USE_DYNAMIC_GATEWAY.updateSQLFunction.execute_update.leads: ORM path
USE_DYNAMIC_GATEWAY.updateSQLFunction.execute_update.contact: raw-SQL path
```

## Rollout plan (incremental on top of wave 1)

If wave 1's flag flip is already soaking, wave 2 doesn't need
extra rollout — flipping ``USE_DYNAMIC_GATEWAY=1`` enables both
DELETE and UPDATE through the gateway. If you're staging from
zero:

1. **Stage 1 — deploy with flag OFF.**
2. **Stage 2 — enable in staging.** Hit a few PATCH endpoints that
   invoke ``updateRawSQL`` (any non-setup record edit). Watch
   logs for ``execute_update.<table>: ORM path`` lines. Verify
   updated rows look identical between the two paths.
3. **Stage 3 — canary tenant.**
4. **Stage 4 — full rollout.**
5. **Stage 5 — delete the raw helpers** after two release cycles.

## What to watch for

- ``InvalidIdentifierError`` from the gateway when raw path
  succeeds → a column in ``update_fields`` has a name that fails
  ``validate_field_name`` (legacy code accepted it; gateway
  doesn't). Investigate the column name; usually means a
  malformed metadata row leaked a non-identifier into the patch.
- Updated row count differs → savepoint coordination issue. Both
  paths run inside the outer transaction; if the gateway opens a
  new ``transaction.atomic`` it should still participate. Capture
  trace + check Postgres ``pg_stat_activity`` for orphan
  transactions.
- ``KeyError: 'name'`` from inside the gateway → the patch key is
  ``None`` or otherwise unhashable. Should be caught earlier in
  ``updateRawSQL`` but capture the trace if it surfaces.

## Rollback

``USE_DYNAMIC_GATEWAY=0`` and redeploy. The raw path is
byte-identical to pre-wave-2 code. Wave 1 (DELETE) reverts to raw
at the same time; if you want to keep wave 1 ON and roll back
just wave 2, revert this branch instead.

## Tests added

- ``tests/permissions/test_orm_dispatch_dynamic_gateway_wave2.py`` —
  9 tests:
  - ``update_unchecked`` rejects empty patch / empty record_id /
    unsafe object name / unsafe field name / empty schema (5)
  - ``_execute_update`` dispatches to raw when flag off and to ORM
    when flag on, forwarding all five arguments (2)
  - ``_execute_update_raw`` emits a ``psycopg2.sql.Composed`` query
    (never a plain string) and forwards parameters in order (1)
  - ``_execute_update_orm`` delegates to
    ``dynamic_table.update_unchecked`` with the right kwargs (1)

Tests skip cleanly when Django isn't installed, and they run in CI
via ``.github/workflows/structural-tests.yml``.

## Same hard "do NOT" rules

1. **Don't reach for ``update_unchecked`` from new code paths**
   without thinking about it. The standard ``update()`` is the
   default; ``unchecked`` is for system-stamped writes only.
2. **Don't drop the ``update_unchecked`` identifier validation.**
   The "unchecked" is *only* the registry-membership check —
   identifier validation (rejecting ``;``, spaces, etc.) is still
   enforced and must not be bypassed.
3. **Don't bypass the dispatch flag.** Call ``_execute_update``
   from ``updateRawSQL``; don't reach for ``_execute_update_orm``
   directly.

## What's next: Phase 4.B wave 3

Wave 3 converts INSERT (``createSQLFunction.post_data_sql``). That
file is the largest (~1412 lines, ~33 cursor sites). Same pattern:
extract the actual INSERT SQL into a small dispatch chokepoint
that delegates to ``dynamic_table.insert`` (or a new
``insert_unchecked`` if the same field-registry tension exists).

After wave 3: wave 4 SELECT (the largest, since it's the
``build_query`` path that drives almost every read in the app —
will need a different approach since it composes via PyPika rather
than ``cursor.execute``).

## Cumulative dual-path coverage after wave 2

| Phase | Layer | Cursor sites converted |
|---|---|---|
| 2.B | permissions.py | 5 |
| 3.C wave 1 | PageLayouts + workflow_executor | 11 |
| 3.C wave 2 | fetch_shared_records + emailsend + telephony | 6 |
| 4.B wave 1 | deleteSQLFunction | 1 |
| 4.B wave 2 | updateSQLFunction (the UPDATE chokepoint) | 1 |
| **Total** | | **24** |

## Branch tree (current)

```
main
└── ...
    └── phase4-b-dynamic-gateway-cutover
        └── phase4-b-wave2-update-cutover  ← THIS BRANCH
```
