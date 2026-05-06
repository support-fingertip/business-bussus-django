# God-file split — wave 1 (Task handler + registry pattern)

Phase 4 of the original 24-week plan called for splitting
`api/BL/blcontroller.py` (5,088 lines, 150 dispatch branches, one
god class) into per-domain handlers ≤400 lines each. That work
was deferred during the Phase 0-4 ORM cutover.

This branch starts the split. Wave 1 ships:

  * the **handler-registry pattern** (the chokepoint that lets
    blcontroller delegate to per-domain handlers)
  * the **first extracted handler** (Task — small, well-bounded)

**No new product surface.** Pure structural refactoring.
Behaviour is byte-identical to pre-wave-1.

## What changed

### New package — `api/BL/handlers/`

| File | What it holds |
|---|---|
| `_base.py` | `DomainHandler` ABC + `HANDLER_REGISTRY` + `register` decorator + `get_handler` lookup + `NotImplementedForVerb` sentinel |
| `task.py` | `TaskHandler` — concrete handler for `task` (GET + PATCH) |
| `__init__.py` | Re-exports + side-effect imports so handlers register at package load |

### `BusinessLogicHandler` now checks the registry first

Two new lookups in `api/BL/blcontroller.py`:

```python
# get_business_logic
result = self._try_registered_handler("get", **kwargs)
if result is not NotImplementedForVerb:
    return result
# ... legacy inline dispatch follows ...

# patch_business_logic
registered = self._try_registered_handler("patch", data.get("data"), **kwargs)
if registered is not NotImplementedForVerb:
    return registered
# ... legacy inline dispatch follows ...
```

For requests where `self.object_name == 'task'`:
- GET routes to `TaskHandler.get()` instead of the deleted inline branch (lines 1836-1852 in pre-wave-1 source)
- PATCH routes to `TaskHandler.patch()` instead of the deleted inline branch (lines 4438-4442 in pre-wave-1 source)

For every other `object_name`, `_try_registered_handler` returns the
sentinel and the legacy inline dispatch runs unchanged.

### What's NOT in wave 1

- **Task POST** — the legacy POST branch was at `another_object == 'task'`
  (creating a task as a child of a parent record). The registry
  is keyed on `self.object_name`, not `another_object`, so POST
  cannot route through it. That branch stays in legacy
  blcontroller.py until parent handlers (Lead, Contact, etc.)
  are extracted, at which point child-creation logic moves into
  the parent's handler file.
- **Other domains** — Recycle Bin, File, Dashboard, Listview,
  Report, Profile, etc. all stay in legacy. Future waves extract
  them one at a time.

## Line-count impact

| | Pre-wave-1 | Post-wave-1 |
|---|---|---|
| `blcontroller.py` | 5,088 | 5,105 |
| Net change | — | **+17** |

Yes — the file **grew** in wave 1. The registry-check infrastructure
costs ~30 new lines, and Task is only ~22 lines of dispatch code.
Wave 1's value is the **pattern**, not immediate line reduction.

Wave 2+ extracts net-negative: a handler covering 200 lines of
dispatch removes 200 lines from blcontroller and adds back only
the verb-stub overhead in the new handler file.

Target end-state per the original plan: `blcontroller.py` ≤200 lines
(down from 5,088).

## Behaviour parity contract

Both paths produce identical results:

  * **Task GET** — same field list, same `get_permissions` call,
    same `get_related_tasks` fallback when no id. The only
    difference is the file the code lives in.
  * **Task PATCH** — same `last_modified_by_id` / `last_modified_date`
    stamping, same `patch_permission` delegation.

If you observe a behaviour difference between pre-wave-1 and
post-wave-1 for `task` GET or PATCH, that's a bug in the extraction
— file an issue with the request payload that diverges.

## Rollout

Unlike the dual-path waves (Phase 2.B / 3.C / 4.B), this is **not**
gated behind a feature flag. The handler is the only path; the old
code is gone. The reasons:

  1. Behaviour is byte-identical (no runtime risk that needs a
     gradual rollout)
  2. Adding a flag would mean keeping two copies of every
     extracted method indefinitely — precisely what we're trying
     to escape
  3. Rollback is `git revert` of this branch, which is
     well-isolated (one new package + ~20 lines in blcontroller)

If a regression surfaces in production after deploy, revert the
branch.

## Tests

`tests/bl/test_handler_registry.py` — 15 unit tests covering:

  * `NotImplementedForVerb` sentinel: falsy, identity-comparable,
    repr is diagnostic
  * `DomainHandler` base class: every verb returns the sentinel by
    default
  * `register` decorator: wires by `OBJECT_NAMES`, rejects classes
    without `OBJECT_NAMES`, rejects duplicate registration on the
    same name, allows idempotent re-registration of the same class
  * `TaskHandler`: registered at import, declares `("task",)`,
    overrides `get` and `patch` only

Tests use `pytest.importorskip("django")` and skip cleanly without
Django (matching the parity-test pattern). They run in CI via the
structural-tests workflow.

## Pre-deploy checklist

- [ ] **Smoke test Task GET** in staging — open a record-detail
      page that loads tasks. Verify the task list renders and
      individual task fields look identical to pre-wave-1.
- [ ] **Smoke test Task PATCH** in staging — edit a task's
      status / due date. Verify the change persists and the
      `last_modified_*` columns update.
- [ ] **Run `pytest -m unit -v`** — all 15 new tests should pass
      in a Django-installed environment (skip cleanly otherwise).
- [ ] **Watch error logs** for 24h after deploy for any
      `KeyError`, `AttributeError`, or `TypeError` mentioning
      `TaskHandler` / `_try_registered_handler` / `task` paths.

## Same hard "do NOT" rules

1. **Don't import `TaskHandler` from outside the handlers package.**
   Callers go through `BusinessLogicHandler` and the registry. The
   handler is an implementation detail.
2. **Don't bypass the registry by hand-rolling another
   `_try_registered_handler` variant.** All four verbs use the same
   helper; future waves will add the POST/DELETE wiring there too.
3. **Don't re-add the deleted Task GET / PATCH branches to
   blcontroller.py.** The handler is the only path now.
4. **Don't extract a domain whose POST is in `another_object`
   context** without first extracting the PARENT. The registry's
   `self.object_name` keying makes POST in `another_object` mode
   un-routable through the current pattern.

## What's next: wave 2+

Future waves extract handlers in increasing order of size. Suggested
order (smallest, most isolated first):

| Wave | Domain | Estimated dispatch lines |
|---|---|---|
| 2 | RecycleBin (`bin`) | ~80 |
| 3 | File (GET + PATCH + DELETE) | ~150 |
| 4 | Notifications | ~60 |
| 5 | Email Templates | ~40 |
| 6 | WhatsApp | ~120 |
| 7 | Telephony | ~150 |
| 8 | Dashboard | ~250 |
| 9 | Setup (the big one — has many sub-dispatches) | ~600 |
| 10 | Lead Conversion (multi-step transaction) | ~150 |
| 11+ | Remaining business objects (lead/contact/account/...) |

Each wave is its own branch, its own PR, its own deploy. Land
serially, not in parallel — they all touch `blcontroller.py`.

After wave 11+: blcontroller.py should be ≤200 lines (a thin
router that just calls `_try_registered_handler` for each verb
and raises if no handler is found).

## Branch tree (current)

```
main
└── godfile-split-wave1-handler-registry  ← THIS BRANCH
```
