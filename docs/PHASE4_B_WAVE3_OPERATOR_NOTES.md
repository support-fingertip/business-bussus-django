# Phase 4.B wave 3 — dynamic-object gateway: INSERT cutover

Wave 1 routed DELETE; wave 2 routed UPDATE; wave 3 does the same
for the main INSERT SQL site in
``api/ORM/sqlFunctions/createSQLFunction.py:post_data_sql``
(the per-record ``INSERT ... RETURNING *`` path at ~line 1100).

Same flag (``USE_DYNAMIC_GATEWAY``) — flipping it now enables
DELETE + UPDATE + INSERT through the gateway at once.

**No new product surface.** Pure plumbing.

## Scope of this wave

createSQLFunction.py has 3 distinct INSERT pipelines:

| Pipeline | Site | This wave? | Why / Why not |
|---|---|---|---|
| Single-row INSERT in ``post_data_sql`` | ~line 1100 | **YES** | The hot path for record creation. Already used ``sql.Identifier``; gateway adds canonical chokepoint. |
| Bulk INSERT via ``execute_values`` in ``bulk_insert_with_report`` | ~line 1156 | NO | Uses ``psycopg2.extras.execute_values`` — different API surface from the gateway's per-row ``insert``. Future wave needs a bulk primitive. |
| Bulk INSERT via ``execute_values`` "fast" path | ~line 1248 | NO | Same as above. |
| Child-record INSERT in ``insert_related_child_records`` | ~line 761 | NO | Ancillary to the main INSERT and only reached if ``child_tables`` is non-empty. Future wave. |

Wave 3 only touches the main single-row INSERT chokepoint. Bulk
INSERTs need a separate ``insert_many`` primitive on the gateway —
candidate work for wave 3.5 if bulk-create endpoints turn out to
benefit from dispatch routing.

## What changed

### `dynamic_table.insert_unchecked()` — new gateway primitive

Mirrors wave 2's ``update_unchecked``:

```python
def insert_unchecked(
    request_or_schema,        # request OR schema string
    object_name: str,         # validated identifier
    payload: dict,            # required, non-empty
) -> dict:                    # the inserted row (RETURNING *)
```

Validates identifiers (object name + every payload key), composes
SQL via ``psycopg2.sql.Identifier``, runs in its own
``transaction.atomic`` (a savepoint inside any outer transaction).

### `createSQLFunction._execute_insert()` — dispatch chokepoint

The single-row INSERT at line ~1100 is now extracted into
``_execute_insert``, dispatching between two helpers:

| Helper | What it does |
|---|---|
| ``_execute_insert_raw(cursor, ...)`` | Byte-identical to pre-wave-3: composes ``INSERT ... RETURNING *`` via ``sql.Identifier``, runs on the caller's existing cursor. Returns ``dict(zip(description, fetchone()))``. |
| ``_execute_insert_orm(schema, ...)`` | Calls ``dynamic_table.insert_unchecked``. Opens a fresh cursor on the same connection — Postgres transactions are connection-level, so the caller's outer ``transaction.atomic`` still wraps the INSERT. |

The public ``post_data_sql`` is unchanged at the surface — same
arguments, same return shape (``{"success": True, "data": [...],
"message": ...}``). Only the actual INSERT SQL emission is dispatched.

The post-INSERT JSON parsing loop (lines ~1109-1114, fixing up
``json``/``jsonb`` columns that Postgres returns as strings) and
the child-record cascade (line 1119) are unchanged — they run on
both paths.

## Feature flag (unchanged)

```bash
USE_DYNAMIC_GATEWAY=0   # default — legacy raw-cursor paths
USE_DYNAMIC_GATEWAY=1   # gateway-backed (waves 1+2+3: DELETE + UPDATE + INSERT)
```

Per-call DEBUG log lines (new in this wave):
```
USE_DYNAMIC_GATEWAY.createSQLFunction.execute_insert.leads: ORM path
USE_DYNAMIC_GATEWAY.createSQLFunction.execute_insert.contact: raw-SQL path
```

## Rollout plan (incremental on top of waves 1+2)

If waves 1+2 are already soaking, wave 3 doesn't need extra
rollout — flipping ``USE_DYNAMIC_GATEWAY=1`` now also routes
INSERT through the gateway. Hit a few POST endpoints that invoke
``post_data_sql`` (any non-setup record create) and verify rows
look identical between the two paths.

Same 5-stage pattern as the prior waves. By Stage 4, you have
DELETE + UPDATE + INSERT all through the gateway; SELECT remains
on the legacy build_query path until wave 4.

## What to watch for

- ``InvalidIdentifierError`` from the gateway when raw path
  succeeds → a column key in ``cleaned_item`` has a name that
  fails ``validate_field_name``. Investigate the column name (often
  a metadata-driven JSON-typed column with non-identifier characters).
- ``UniqueViolation`` only on the ORM path → the savepoint that
  the gateway opens inside the outer transaction is being released
  while the outer transaction tries to roll back. Capture trace
  + check ``pg_stat_activity`` for orphan savepoints.
- Inserted-row dict missing keys that the raw path returned →
  ``RETURNING *`` should return the same column set on both paths;
  if they differ, the table has different ``DEFAULT`` semantics
  per-tenant. Run ``scripts/ddl_introspection.py compare`` to find
  the divergent tenants.
- JSON columns that come back as strings on the ORM path but
  parsed dicts on the raw path → no, the JSON parsing loop runs
  AFTER ``_execute_insert`` returns and applies to both paths
  identically. If you see this, the loop is being skipped — verify
  ``type_map`` is populated for the table.

## Rollback

``USE_DYNAMIC_GATEWAY=0`` and redeploy. The raw path is
byte-identical to pre-wave-3 code. Waves 1+2 revert at the same
time; if you want to keep them on and roll back just wave 3,
revert this branch.

## Tests added

- ``tests/permissions/test_orm_dispatch_dynamic_gateway_wave3.py`` —
  8 tests:
  - ``insert_unchecked`` rejects empty payload / unsafe object name
    / unsafe field name / empty schema (4)
  - ``_execute_insert`` dispatches to raw when flag off and to ORM
    when flag on, forwarding all four arguments (2)
  - ``_execute_insert_raw`` emits a ``psycopg2.sql.Composed`` query
    (never a plain string) and returns ``dict(zip(description,
    fetchone()))`` (1)
  - ``_execute_insert_orm`` delegates to
    ``dynamic_table.insert_unchecked`` with the right kwargs (1)

Tests skip cleanly without Django and run in CI via the structural
tests workflow.

## Same hard "do NOT" rules

1. **Don't reach for ``insert_unchecked`` from new code paths**
   without thinking about it. The standard ``insert()`` is the
   default; ``unchecked`` is for system-stamped writes only.
2. **Don't drop the ``insert_unchecked`` identifier validation.**
   The "unchecked" is *only* the registry-membership check.
3. **Don't bypass the dispatch flag.** Call ``_execute_insert``
   from ``post_data_sql``; don't reach for ``_execute_insert_orm``
   directly.
4. **Don't add a bulk-INSERT primitive opportunistically.** Bulk
   needs its own design (``execute_values`` semantics, partial
   failure handling, RETURNING from many rows). Land it as a
   separate wave once we have a bulk-create soak case.

## What's next: Phase 4.B wave 4

Wave 4 converts SELECT — the ``build_query`` path in
``api/ORM/sqlFunctions/getQueryBuilder.py``. That's the largest
surface (every list / detail page in the app reads through it),
and the SQL composition uses **PyPika**, not raw ``cursor.execute``.

Approach options for wave 4:
- (a) Extend the gateway's ``select`` to accept the PyPika query
  shape; route through the existing primitive.
- (b) Add a ``select_raw`` primitive to the gateway that takes a
  pre-composed ``psycopg2.sql.Composed`` query and parameters;
  wrap PyPika's output in it.
- (c) Leave the read path on PyPika and only dispatch the
  ``cursor.execute`` of the final query through the gateway as a
  thin executor.

(c) is probably the lowest-risk shape — same pattern as waves 1-3.

After wave 4: the gateway will be the canonical chokepoint for
all four CRUD operations on dynamic-object tables.

## Cumulative dual-path coverage after wave 3

| Phase | Layer | Cursor sites converted |
|---|---|---|
| 2.B | permissions.py | 5 |
| 3.C wave 1 | PageLayouts + workflow_executor | 11 |
| 3.C wave 2 | fetch_shared_records + emailsend + telephony | 6 |
| 4.B wave 1 | deleteSQLFunction | 1 |
| 4.B wave 2 | updateSQLFunction (UPDATE) | 1 |
| 4.B wave 3 | createSQLFunction (single-row INSERT) | 1 |
| **Total** | | **25** |

## Branch tree (current)

```
main
└── ...
    └── phase4-b-wave2-update-cutover
        └── phase4-b-wave3-insert-cutover  ← THIS BRANCH
```
