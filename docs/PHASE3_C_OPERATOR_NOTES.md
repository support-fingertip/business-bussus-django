# Phase 3.C — Extend cursor→ORM cutover into BL files

Phase 2.B introduced the dual-path dispatch primitive for the
permissions layer. Phase 3.C reuses the same primitive (extended to
take a per-feature flag) to convert cursor sites in the BL layer that
hit Wave 3-5 tenant-modeled tables.

**No new product surface.** Pure cursor→ORM cutover, gated by a new
feature flag so the rollout is independent from the Phase 2.B one.

## What changed

### Dispatch primitive — one new keyword

`api/permissions/_orm_dispatch.py` now accepts a `flag` keyword on
both `is_orm_enabled()` and `dispatch()`. Default stays
`USE_ORM_FOR_PERMISSIONS` (Phase 2.B back-compat).

```python
# Phase 2.B (unchanged)
dispatch("foo", raw_impl, orm_impl)
# ↑ uses USE_ORM_FOR_PERMISSIONS

# Phase 3.C (new)
dispatch("foo", raw_impl, orm_impl, flag="USE_ORM_FOR_BL")
```

### Files converted

| File | Cursor sites converted | ORM models used |
|---|---|---|
| `api/BL/PageLayouts/page_layout.py` | 4 sites collapsed to 1 batch | `User` (api/models.py) |
| `api/workflows/workflow_executor.py` | **7 sites** | `Workflow`, `WorkflowNode`, `WorkflowEdge`, `EmailTemplate` (Wave 5), `UserGroupPublicGroup` (Wave 2 follow-up) |

#### PageLayouts/page_layout.py — 4 → 1 batch (always-on optimisation)

The previous code did N+1 user lookups inside a loop over page-layout
records (two `SELECT name FROM users WHERE id = %s` per record). The
new path collects all distinct IDs across every record and resolves
them in a single batch query. The dispatch picks raw SQL or
`User.objects` for the batch.

Even with the flag OFF, this is now a clean win — the legacy raw
path is also batched. No more N+1.

#### workflow_executor.py — 7 cursor sites converted

| Site | ORM equivalent |
|---|---|
| `workflow_query` (top-level workflow lookup) | `Workflow.objects.filter(trigger_type=..., module_name=...).values_list("id", "name")` |
| `start_node_query` | `WorkflowNode.objects.filter(workflow_id=..., node_type="Start").values_list("id", "label", "node_type", "data").first()` |
| `_fetch_edges` (helper) | `WorkflowEdge.objects.filter(source_id=...).values_list("id", "target_id")` |
| `_fetch_edge_by_handle` (helper) | `WorkflowEdge.objects.filter(source_id=..., source_handle=...).values_list(...).first()` |
| `_fetch_node` (helper) | `WorkflowNode.objects.filter(id=...).values_list(...).first()` |
| Email template lookup | `EmailTemplate.objects.filter(name=...).values_list("template_type", "subject", "body").first()` |
| Sub-group resolution loop | `UserGroupPublicGroup.objects.filter(user_group_id__in=...).values_list("public_group_id", flat=True)` |

The ~18 remaining `cursor.execute` calls in `workflow_executor.py`
are NOT convertible in this branch — they target dynamic
business-object tables (the actual records that workflows act on),
not Wave 3-5 setup tables. The `api/ORM/dynamic/` gateway (Phase 1
scaffold) handles those in a future phase.

### Files NOT converted

| File | Reason |
|---|---|
| `BL/Reports/get_reports.py` | Already routes through `get_permissions()` → no cursor calls; gets ORM benefit transitively from Phase 2.B |
| `BL/PageBuilder/get_pagebuilder.py` | Same — 0 cursor calls |
| `BL/dashboards/dashboard.py` | The 3 cursor calls read `information_schema.columns` — not a Wave 3-5 modeled table, can't be ORM'd |
| `BL/Listviews/GetListview.py` | Touches `task` table (not yet modeled — Wave 6 / Phase 3.B) |
| `api/emailsend/views.py` | Touches `email_provider_setup` (not yet modeled — Wave 6 / Phase 3.B) |

## Feature flag

```bash
USE_ORM_FOR_BL=0   # default — raw SQL paths
USE_ORM_FOR_BL=1   # all converted BL sites route to ORM paths
```

Independent of `USE_ORM_FOR_PERMISSIONS` — operators can roll out one
without touching the other.

Per-call DEBUG log lines:
```
USE_ORM_FOR_BL.workflow_executor.list_workflows: ORM path
USE_ORM_FOR_BL.workflow_executor.email_template_lookup: raw-SQL path
USE_ORM_FOR_BL.PageLayouts._resolve_user_names: ORM path
```

## Rollout plan

Same 5-stage pattern as Phase 2.B:

1. **Stage 1 — deploy with flag OFF** — code merges, behaviour
   unchanged. Even with the flag OFF, the PageLayouts N+1 fix is live.
2. **Stage 2 — enable in staging** for 1 week — run workflow execution
   smoke tests, page-layout list rendering, email-template send.
3. **Stage 3 — canary tenant** — flip the flag for one tenant, watch
   logs for any ORM-path errors.
4. **Stage 4 — full rollout** — flip globally.
5. **Stage 5 — delete the raw paths** after two release cycles.

## What to watch for

- `OperationalError: relation "<table>" does not exist` → tenant missing
  one of the Wave 3-5 tables. Check tenant provisioning ran
  `default_tables.sql` end-to-end.
- Workflow start node returning empty when raw path returns one →
  schema drift on `workflow_node.node_type` column type.
- `User.DoesNotExist` from PageLayouts → `users` table missing in
  tenant schema; should fall through to `public.users` via the
  `search_path public` fallback. If not, the tenant's search_path
  isn't set correctly — investigate `TenantSchemaMiddleware` for the
  tenant in question.

## Rollback

Set `USE_ORM_FOR_BL=0` and redeploy. Raw-SQL paths are unchanged
from before the cutover.

## Tests added

- `tests/permissions/test_orm_dispatch_bl.py`
  - `is_orm_enabled` honours the named flag (not just the default).
  - Flags are independent — `USE_ORM_FOR_PERMISSIONS=1` does NOT enable
    `USE_ORM_FOR_BL`.
  - PageLayouts user-name resolver returns the same `{id: name}` shape
    on either path.
  - Empty IDs returns empty dict (no SQL fired).
