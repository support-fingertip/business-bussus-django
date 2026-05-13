# Phase 6 adoption — Celery task migration (operator notes)

**Status:** All existing Celery tasks classified; foundation is now USED
**Branch:** `claude/sec-phase6-celery-adoption`

## What this branch does in plain English

The Phase 6 foundation (`api/celery_tasks/base.py`) introduced two
task base classes back in `claude/sec-phase5-7-foundation`:

  * **`TenantRequiredTask`** — refuses to run without `_tenant_ctx`
    in kwargs. Wraps the body in `with_tenant_schema()` so DB queries
    auto-scope. Use for any task that touches tenant data.

  * **`AdminTask`** — explicit opt-out for tasks that legitimately
    span multiple tenants (nightly sweeps, audit roll-ups). Marker
    class makes the cross-tenant intent obvious in PR review.

This branch audits every existing `@shared_task` in the codebase and
applies the right base class. Each migrated task is **one less leak
path** — a task running with the wrong tenant context now either
refuses (TenantRequiredTask) or is explicitly known to be admin
(AdminTask).

## What got migrated

| Task | Old base | New base | Why |
|---|---|---|---|
| `adminuser.tasks.log_user_login_async` | `@shared_task` | `TenantRequiredTask` | Writes to `public.session_log` + `public.user_login_history` — both Row-Level-Security-scoped on `organization_id` after Phase 4 part 2. Without a tenant context, the write would fail RLS (under FORCE) or insert a NULL `organization_id`. |
| `api.emailsend.tasks.send_notify_email_verification` | `@shared_task` | `AdminTask` | Iterates `public.users` across every tenant for the verification reminder sweep. Cross-tenant by design — AdminTask marks that intent explicitly. |
| `sf_integration.tasks.process_salesforce_sync` | `@shared_task` | `AdminTask` | Top-level scans `public.SalesforceSync` across orgs. Cross-tenant by design. (Inner loop has a separate gap — see below.) |

## What got LEFT alone (and why)

| Task | Status |
|---|---|
| `api.emailsend.tasks.process_due_email_campaigns` | Already protected via the older `@tenant_schema_required("tenant_schema")` decorator from `api/security/tenant_context.py`. Same isolation guarantee as `TenantRequiredTask` — pins `search_path` to the tenant schema for the body of the task. Don't double-migrate; the existing decorator works. New tasks should use `TenantRequiredTask` for consistency. |
| `version2.celery.debug_task` | Celery's example debug task — diagnostic only. On the `EXPLICIT_EXEMPT_TASKS` allowlist in `tests/security/test_celery_task_bases.py`. |

## What changed at the caller side

### `adminuser/LoginView.py`

Login is the one place that calls `log_user_login_async.delay()`. The
task now requires `_tenant_ctx`. The login flow runs BEFORE the tenant
middleware (the JWT doesn't exist yet at login start), so the caller
builds a `TenantContext` explicitly from the row it just looked up.

**Before:**
```python
log_user_login_async.delay(user_id=..., profile_id=..., ...)
```

**After:**
```python
from api.celery_tasks.base import serialize_ctx
from api.security.schema_authority import TenantContext

# After the user lookup, fetch the org's schema name
with connection.cursor() as c:
    c.execute("SELECT database_schema FROM public.organizations WHERE id = %s",
              [organization_id])
    schema = c.fetchone()[0]

ctx = TenantContext(
    org_id=str(organization_id),
    schema=schema,
    profile_id=str(profile_id),
)
log_user_login_async.apply_async(
    kwargs={"_tenant_ctx": serialize_ctx(ctx), "user_id": ..., ...},
)
```

One extra query at login time — acceptable since login is already
multi-statement. The added safety: the task can't accidentally
write to the wrong tenant's session_log row even if the worker has
stale connection state.

### `public/auth/login.py` (the OTHER login flow)

This one uses `threading.Thread`, NOT Celery, for the same purpose.
It writes directly to `session_log` / `user_login_history` from a
spawned Python thread. NOT in scope for Phase 6 (no Celery involved)
but flagged here because:

  * The thread doesn't carry tenant context either
  * Once Phase 4 part 3 flips FORCE on, this thread's writes will
    fail
  * Recommend migrating to Celery + `TenantRequiredTask` in a
    follow-up branch (or converting the thread to use
    `with_tenant_schema()` inline)

## Test coverage

`tests/security/test_celery_task_bases.py` — 5 tests:

1. `log_user_login_async` has `TenantRequiredTask` in its MRO.
2. `send_notify_email_verification` has `AdminTask` in its MRO.
3. `process_salesforce_sync` has `AdminTask` in its MRO.
4. Direct invocation of `log_user_login_async` without `_tenant_ctx`
   raises `RuntimeError` mentioning `_tenant_ctx`.
5. `EXPLICIT_EXEMPT_TASKS` allowlist for diagnostic tasks (debug_task).

Adding a new task to the codebase without the right base class fails
test #1-3 by absence. The CI gate catches it.

## Follow-up gaps (Phase 6+)

These were discovered during the audit but are out of scope for this
branch:

1. **`sf_integration.tasks.sync_salesforce_object` inner loop** — the
   top-level task is now `AdminTask`, but the inner loop's call to
   `copy_salesforce_data_to_app` writes into `sf_integration_<object>`
   tables which are per-tenant. The inner loop needs:
   ```python
   for sync_obj in sync_objects:
       with with_tenant_schema(sync_obj.organization.database_schema):
           sync_salesforce_object(sync_obj)
   ```
   This requires `SalesforceSync` to have an `organization_id` /
   `database_schema` column, which it doesn't today. **Separate
   branch.**

2. **`public/auth/login.py:log_user_login`** — runs in a Python
   thread, not Celery. Either migrate to Celery (using the same
   pattern as `adminuser/LoginView.py`) OR add an inline
   `with_tenant_schema()` block around the writes. **Separate branch.**

3. **Eventual: `app.Task = TenantRequiredTask`** — once every task in
   the codebase is explicitly classified, set this as the Celery
   default in `version2/celery.py`. A new `@shared_task` without
   explicit `base=` would then inherit `TenantRequiredTask` and
   fail-closed by default.

## Rollout

Unlike Phase 4 rollouts, this branch has **no operator action**
beyond merge + deploy:

1. Merge.
2. Deploy as normal.
3. Celery workers pick up the new base classes on restart.
4. The login flow's `apply_async` call passes `_tenant_ctx` from
   the org lookup — works immediately.
5. Watch worker logs for 24h for `RuntimeError: ... _tenant_ctx`
   messages. None should appear (only `log_user_login_async` is
   tenant-required, and its only caller is updated).

## Rollback

`git revert` of this branch is safe. Old caller invocations would
go back to the bare `@shared_task` signature; no caller side
changes needed beyond reverting LoginView.

## Verification

After deploy, on the next login, the Celery worker log should show:

```
[INFO] log_user_login_async[<task-id>]: Successfully logged login
for user u_xxx (org=org_yyy)
```

The `(org=org_yyy)` suffix is new — it confirms the TenantContext
was injected. If you see the old `Successfully logged login for user
u_xxx` without the org suffix, the caller didn't pass `_tenant_ctx`
and the task either crashed (RuntimeError) or fell through to a code
path that bypasses the new base (rollback didn't take fully).
