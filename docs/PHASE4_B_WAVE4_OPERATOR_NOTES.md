# Phase 4.B wave 4 — dynamic-object gateway: SELECT cutover

The final wave of the Phase 4.B CRUD cutover. Wave 1 routed
DELETE; wave 2 routed UPDATE; wave 3 routed INSERT; wave 4 does
the same for the SELECT execution site in
``api/ORM/sqlFunctions/getQueryBuilder.py:fetch_data_raw_sql``.

After this wave, **all four CRUD operations** on dynamic-object
tables flow through the gateway when ``USE_DYNAMIC_GATEWAY=1``.

**No new product surface.** Pure plumbing.

## Why "select_raw" instead of extending `select()`

The existing gateway ``select()`` builds SQL itself from a fields
list + structured where dict. The build_query path **already**
composes its SQL via PyPika — re-routing it through ``select()``
would mean recomposing the same query in two different ways and
trying to keep them in sync. Brittle and pointless.

Wave 4 takes a different shape: **``select_raw(schema, query,
params)``** — a thin executor that accepts a pre-composed query
(string or ``psycopg2.sql.Composed``) and just runs it. The
gateway's value here is **not** SQL composition (PyPika handles
that safely upstream); it's making the gateway the canonical
chokepoint for cross-cutting concerns:

  * schema-pin enforcement (currently the legacy path also does
    this — but in 4 different functions; the gateway centralises
    it)
  * future statement timeouts (one place to add them)
  * future metric emission, retry policy, etc.

Same approach we picked for the wave 3 operator notes' "Approach
options" — **option (c)**: leave the read path on PyPika, only
dispatch the cursor.execute through the gateway.

## What changed

### `dynamic_table.select_raw()` — new gateway primitive

```python
def select_raw(
    request_or_schema,        # request OR schema string
    query,                    # str (PyPika output) OR sql.Composed
    params=None,              # iterable of bind values
) -> list[dict]:              # rows as [{column: value}, ...]
```

Schema-pin enforcement (``_resolve_schema``) runs first, then the
cursor opens, search_path is set, the pre-composed query is
executed, and rows come back as a list of dicts.

Identifier validation is **not** performed on the SQL itself —
the caller is responsible for SQL safety. ``select_raw`` is a
trust-the-caller primitive (PyPika is the trust boundary
upstream). Anyone reaching for ``select_raw`` from new code
should already understand this.

### `getQueryBuilder._execute_select()` — dispatch chokepoint

The cursor work in ``fetch_data_raw_sql`` (was at lines ~206-211)
is now extracted into ``_execute_select``, dispatching between
two helpers:

| Helper | What it does |
|---|---|
| ``_execute_select_raw(schema, sql, params)`` | Byte-identical to pre-wave-4: opens a cursor, sets search_path, executes the SQL, returns ``(columns, rows)`` so the caller can do the column-type post-processing. |
| ``_execute_select_orm(schema, sql, params)`` | Calls ``dynamic_table.select_raw`` and unpacks its list-of-dicts return into ``(columns, rows)``. Uses the first row's ``dict.keys()`` to derive column names — Python 3.7+ guarantees dict ordering matches insertion (and the gateway preserves cursor.description ordering). |

Both helpers return ``(columns, rows)`` so the surrounding JSON-
parsing + datetime-tz post-processing in ``fetch_data_raw_sql``
works identically on either path.

The public ``fetch_data_raw_sql`` is unchanged at the surface —
same args, same return (a list of dicts with JSON parsed and
naive datetimes attached to UTC).

## Feature flag (unchanged)

```bash
USE_DYNAMIC_GATEWAY=0   # default — legacy raw-cursor paths
USE_DYNAMIC_GATEWAY=1   # gateway-backed (waves 1-4: D / U / I / S)
```

Per-call DEBUG log lines (new in this wave):
```
USE_DYNAMIC_GATEWAY.getQueryBuilder.execute_select: ORM path
USE_DYNAMIC_GATEWAY.getQueryBuilder.execute_select: raw-SQL path
```

Note: unlike waves 1-3 (which include the table name in the log
line), wave 4's log line is the same string regardless of which
table is queried. SELECT in this codebase often joins multiple
tables; there isn't a single "table" to attribute the call to.
If per-table observability is needed during the soak, add the
``base_table_name`` to the dispatch ``name`` upstream — but
that's a wave 4.5 ask.

## Rollout plan (incremental on top of waves 1-3)

If waves 1-3 are already soaking, wave 4 doesn't need extra
rollout — flipping ``USE_DYNAMIC_GATEWAY=1`` now also routes
SELECT through the gateway. The hot path here is **every list
endpoint** in the app, so the soak window matters more than for
the previous waves:

1. **Stage 1 — deploy with flag OFF.**
2. **Stage 2 — enable in staging for at least 1 week.** Hit a
   variety of list / detail / search endpoints. Watch logs for
   ``execute_select: ORM path`` lines and any unexpected errors.
   Compare row counts and field shapes between staging-with-flag
   and a parallel staging-without-flag.
3. **Stage 3 — canary tenant for at least 3 days.** SELECT errors
   are user-visible (broken list pages); we want a long enough
   window to catch the rare-tenant edge case.
4. **Stage 4 — full rollout.**
5. **Stage 5 — delete the raw helpers** after **three** release
   cycles (one more than the prior waves; reads have the largest
   blast radius).

## What to watch for

- ``Empty list[dict]`` from the ORM path when raw path returned
  rows → the dict-key derivation in ``_execute_select_orm`` only
  reads the first row's keys. If the gateway ever returns an empty
  list when there *should* be rows, the column list is empty and
  the post-processor short-circuits. Capture trace + check the
  gateway's cursor.description vs the raw path's output.
- Different column ordering between paths → Python 3.7+ guarantees
  dict ordering matches insertion, and the gateway uses
  ``cursor.description`` to insert in order. If you see a column-
  order divergence, log the raw path's ``cursor.description`` and
  the gateway's first-row dict keys side-by-side.
- ``OperationalError: relation "X" does not exist`` only on ORM
  path → search_path isn't pinning the way the raw path did.
  Check ``TenantSchemaMiddleware`` for the request, and the
  ``schema`` argument that ``fetch_data_raw_sql`` received. The
  gateway's ``_set_search_path`` runs the same SQL, so this
  should only happen if ``schema`` itself differs.
- JSON columns coming back as strings on one path but parsed
  dicts on the other → the JSON parsing happens in
  ``fetch_data_raw_sql`` AFTER ``_execute_select`` returns.
  Should never differ. If it does, the gateway is parsing JSON
  on its way out (it shouldn't be) — verify ``select_raw`` is the
  thin executor and not doing extra work.

## Rollback

``USE_DYNAMIC_GATEWAY=0`` and redeploy. The raw path is byte-
identical to pre-wave-4 code. Waves 1-3 revert at the same time;
if you want to keep them on and roll back just wave 4, revert
this branch.

## Tests added

- ``tests/permissions/test_orm_dispatch_dynamic_gateway_wave4.py`` —
  10 tests:
  - ``select_raw`` rejects empty schema string + request without
    pinned schema; accepts schema string (3)
  - ``_execute_select`` dispatches to raw when flag off and to ORM
    when flag on, forwarding all three arguments and returning
    ``(columns, rows)`` (2)
  - ``_execute_select_orm`` unpacks gateway list-of-dicts into
    the ``(columns, rows)`` tuple shape, including empty-result
    handling (2)
  - ``fetch_data_raw_sql`` post-processing (JSON parsing, naive-
    datetime UTC attachment, aware-datetime passthrough) works
    correctly when fed from a stubbed ``_execute_select`` (3)

Tests skip cleanly without Django and run in CI via the structural
tests workflow.

## Same hard "do NOT" rules

1. **Don't trust the caller's SQL inside ``select_raw``.** The
   primitive is "trust the caller" because PyPika is the trust
   boundary upstream. Don't hand a user-supplied SQL string to
   ``select_raw`` from new code without thinking about who built
   it.
2. **Don't bypass ``_execute_select`` from inside
   ``fetch_data_raw_sql``.** If you find yourself reaching for a
   raw cursor there, you're undoing the wave 4 work.
3. **Don't change the ``(columns, rows)`` return shape** without
   updating both helpers AND the caller's post-processing loop.
4. **Don't extend ``select_raw`` with composition logic.** It's
   a thin executor by design — anything that needs to *build*
   SQL is in PyPika or in the gateway's ``select()`` primitive,
   never in ``select_raw``.

## Phase 4.B is now complete

After this wave, all four CRUD primitives are dual-pathed behind
``USE_DYNAMIC_GATEWAY``:

| Op | Site | Wave |
|---|---|---|
| DELETE | ``deleteSQLFunction.delete_data_sql`` | 1 |
| UPDATE | ``updateSQLFunction.updateRawSQL`` (UPDATE chokepoint) | 2 |
| INSERT | ``createSQLFunction.post_data_sql`` (single-row INSERT) | 3 |
| SELECT | ``getQueryBuilder.fetch_data_raw_sql`` | 4 |

The gateway is the canonical chokepoint for dynamic-object SQL
on the four hot paths. Future hardening (statement timeouts,
metric emission, retry policy) lands in the gateway and applies
uniformly to all four operations.

## What's NOT done

The following sites still bypass the gateway and would need
follow-up waves:

  * **Bulk INSERT** via ``execute_values`` in
    ``createSQLFunction.bulk_insert_with_report`` (~lines 1156,
    1248). Needs an ``insert_many`` primitive on the gateway
    with partial-failure semantics.
  * **Child-record INSERT** in
    ``createSQLFunction.insert_related_child_records`` (~line 761).
    Currently only reached when a payload has child tables.
  * **Complex SELECT** via ``complexGetSql.build_complex_query``
    (the report builder). It returns its own SQL string; the
    chokepoint at ``fetch_data_raw_sql`` already routes it
    through wave 4 if the upper layer hands it off, but the
    direct callers haven't been audited.
  * **Setup-table CRUD** through ``permissions.py``'s
    ``post_permission`` / ``patch_permission`` /
    ``delete_permission`` — those go through Phase 2.B's ORM
    dispatch (``USE_ORM_FOR_PERMISSIONS``), a separate flag with
    its own rollout.

These are not blockers for declaring Phase 4.B complete. They
are listed so future cleanup can start from a known scope.

## Cumulative dual-path coverage after wave 4

| Phase | Layer | Cursor sites converted |
|---|---|---|
| 2.B | permissions.py | 5 |
| 3.C wave 1 | PageLayouts + workflow_executor | 11 |
| 3.C wave 2 | fetch_shared_records + emailsend + telephony | 6 |
| 4.B wave 1 | deleteSQLFunction | 1 |
| 4.B wave 2 | updateSQLFunction (UPDATE) | 1 |
| 4.B wave 3 | createSQLFunction (single-row INSERT) | 1 |
| 4.B wave 4 | getQueryBuilder (SELECT) | 1 |
| **Total** | | **26** |

## Branch tree (current)

```
main
└── ...
    └── phase4-b-wave3-insert-cutover
        └── phase4-b-wave4-select-cutover  ← THIS BRANCH
```
