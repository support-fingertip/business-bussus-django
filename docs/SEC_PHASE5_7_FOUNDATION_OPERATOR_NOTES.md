# Security Phases 3 / 5 / 6 / 7 / 8 — foundation modules

**Branch:** `claude/sec-phase5-7-foundation`
**Base:**   `claude/godfile-split-wave1-handler-registry`
**Status:** Foundation only — adoption is incremental from here.

This branch lands the **primitives** that Phases 2-9 of
`docs/security/launch_readiness_plan.md` need, without yet
migrating any call sites. The primitives are safe to merge on
their own because:

  * Every new module is **additive** — nothing the existing code
    relies on changes behaviour.
  * The one model change (`SessionLog.access_token` →
    `EncryptedCharField`) is backward-compatible via
    `decrypt_token`'s legacy plaintext passthrough.
  * The handler-registry change passes a new optional `ctx`
    parameter that legacy handlers ignore.

## What landed in this branch

### Phase 5 — application boundary

| File | Purpose |
|---|---|
| `api/db/tenant_cursor.py` | The only sanctioned way to run raw SQL in tenant code. Re-verifies `search_path` matches `ctx.schema` before yielding the cursor. |
| `api/tenant_models/_base.py` (rewritten) | Adds `TenantManager` with `for_tenant(ctx)`. Every `TenantModel.objects` now exposes this entrypoint. Naked `.objects.filter()` still works (Phase 5 enforces migration via Semgrep). |
| `api/BL/handlers/_base.py` (extended) | `DomainHandler.__init__` now takes `ctx=None`. Wave-1 `TaskHandler` inherits unchanged. |
| `api/BL/blcontroller.py` (extended) | `_try_registered_handler` builds a `TenantContext` from the pinned request and passes it to the handler. `_build_tenant_ctx` helper. |

### Phase 6 — background work

| File | Purpose |
|---|---|
| `api/celery_tasks/__init__.py` | New package |
| `api/celery_tasks/base.py` | `TenantRequiredTask` (refuses to run without `_tenant_ctx`), `AdminTask` (explicit cross-tenant opt-out), `serialize_ctx` helper |

### Phase 7 — cache namespacing

| File | Purpose |
|---|---|
| `CacheService/tenant_cache.py` | `tenant_get` / `tenant_set` / `tenant_delete` / `tenant_get_many` / `purge_tenant`. Every key is prefixed `tenant:<org_id>:<key>`. |

### Phase 3 — encryption at rest (one table done end-to-end)

| File | Purpose |
|---|---|
| `api/security/encrypted_fields.py` | `EncryptedCharField` / `EncryptedTextField` — drop-in field types that encrypt-on-write and decrypt-on-read. Idempotent. |
| `api/models.py` | `SessionLog.access_token` and `.refresh_token` switched to `EncryptedCharField(1024)`. |
| `api/migrations/0010_encrypt_session_log_tokens.py` | Schema migration — bumps max_length 500 → 1024; no DB rewrite. |
| `api/management/commands/encrypt_legacy_session_tokens.py` | One-shot backfill: re-encrypts pre-rollout plaintext rows. Idempotent. |

### Phase 8.1 — file upload validation

| File | Purpose |
|---|---|
| `utils/file_validation.py` | `validate_upload(file, kind, max_bytes)` — size cap, MIME sniffing via `python-magic` (with extension fallback), filename sanitisation. Hook for Phase 8.2 virus scan. |

### Tests

All under `tests/security/`:

  * `test_tenant_cursor.py` — 5 tests
  * `test_tenant_cache.py` — 8 tests
  * `test_encrypted_fields.py` — 5 tests (requires `cryptography`)
  * `test_file_validation.py` — 8 tests
  * `test_tenant_required_task.py` — 5 tests
  * `test_tenant_manager.py` — 3 tests

Tests use `pytest.importorskip("django")` so they skip cleanly in
stripped CI environments (matches the existing pattern in
`tests/bl/test_handler_registry.py`).

## Adoption checklist — per call site

These get migrated incrementally as Phases 5-8 progress. **None
of this work is in this branch.** The list lives here so engineers
working on subsequent waves know what's expected:

### Phase 5 adoption

- [ ] Migrate `*.objects.filter(...)` call sites → `*.objects.for_tenant(ctx).filter(...)`
- [ ] Migrate `connection.cursor()` call sites → `tenant_cursor(ctx)`
- [ ] Enable `.semgrep/tenant_isolation.yml` (committed on
      `claude/sec-00-planning-docs`) as a CI gate

### Phase 6 adoption

- [ ] Audit existing `@shared_task` declarations
- [ ] Convert tenant-scoped tasks to `base=TenantRequiredTask`
- [ ] Convert cross-tenant tasks to `base=AdminTask` (security review)
- [ ] Set `app.Task = TenantRequiredTask` as Celery default base

### Phase 7 adoption

- [ ] Migrate `cache.get/set/delete` call sites in BL → `tenant_*` wrappers
- [ ] Audit existing `CacheService.cache.build_key` calls — they
      already include a schema segment but rely on caller discipline

### Phase 3 adoption (remaining secret columns)

Same pattern as `SessionLog` — for each:
  * Switch the column to `EncryptedCharField` or `EncryptedTextField`
  * Add a migration (alter-field, no DB rewrite if max_length suffices)
  * Add a `encrypt_legacy_<table>_tokens` backfill command
  * Run backfill in each environment after deploy

Tables still pending:
  * `telephony_config.authtoken` / `sid` — `api/tenant_models/integration.py:44`
  * `lead_capture.page_access_token` — `api/tenant_models/shared.py:50`
  * `user_gmail_tokens.access_token` / `refresh_token` — `integration.py:160`
  * `user_outlook_tokens.access_token` / `refresh_token` — `integration.py:161`
  * `salesforce_settings.password` / `client_secret` — `sf_integration/models.py:22`
  * `users.app_password` — `api/models.py:162`

### Phase 8 adoption

- [ ] `api/BL/blcontroller.py` ~line 2820 — file upload route through `validate_upload`
- [ ] Other upload sites (logos, attachments) — same
- [ ] Install `python-magic` and `libmagic1` in the Dockerfile
- [ ] Phase 8.2 — plug ClamAV / cloud malware scan into the TODO hook
      in `validate_upload`

## Deployment / rollout notes

### `SessionLog` token encryption migration

**Order matters:**

1. **Deploy code** with the new `EncryptedCharField` AND the
   `decrypt_token` legacy-plaintext passthrough. Both must be live
   so old rows keep working while new writes are encrypted.

2. **Run migration** `0010_encrypt_session_log_tokens` — alters
   column max_length 500 → 1024. No table rewrite, but worth
   running in a maintenance window for very large `session_log`
   tables (millions of rows).

3. **Backfill** with `python manage.py encrypt_legacy_session_tokens --dry-run`
   first to count rows, then without `--dry-run` to encrypt them.

4. **Verify** — re-run with `--dry-run`; should report 0 rows.

5. **Optional Phase 3 follow-up** — once backfill is verified,
   add a startup check (`api/apps.py.ready()`) that warns/alerts
   if plaintext rows reappear (e.g. some forgotten write path).

### `tenant_cursor` / `for_tenant` runtime check

Both check the connection's `search_path` against `ctx.schema`. On
mismatch they raise `PermissionError`, which the dispatcher converts
to 403. **Symptoms of mismatch:** a request that used to succeed
now returns 403 with `"DB connection not pinned"` in the log. The
fix is to ensure `TenantSchemaMiddleware` (or
`with_tenant_schema()` for background work) runs before the
manager / cursor call.

The check is cheap (one round-trip per call) so it's safe to leave
on permanently — Phase 4 will replace the `search_path` check with
a stronger `current_role` + `app.current_org_id` check.

### `TenantRequiredTask`

Tasks decorated with bare `@shared_task` (no `base=`) keep working
unchanged — they don't pick up this base class. The migration
strategy is opt-in per task. **Risk:** a task that does need to be
tenant-scoped but hasn't been migrated will continue to run without
the guard. Phase 6 audit closes this gap by listing every existing
task.

## Pre-deploy checklist

- [ ] Run `pytest tests/security/ -v` — all new tests pass
- [ ] Run `pytest tests/bl/test_handler_registry.py -v` — wave-1
      tests still pass with the new ctx parameter
- [ ] `python manage.py makemigrations --dry-run` — should report
      only `0010_encrypt_session_log_tokens`, nothing else
- [ ] Verify `OAUTH_TOKEN_ENC_KEY` (or `OAUTH_TOKEN_ENC_KEYS`) is
      set in every environment that will run the migration
- [ ] Smoke test in staging:
    - Log in → verify a `session_log` row exists with `ENC1:` prefix
    - Re-login flow uses the access/refresh tokens correctly
    - Run `encrypt_legacy_session_tokens --dry-run` against
      staging data to validate the migration plan

## Branch tree (current)

```
main
└── claude/godfile-split-wave1-handler-registry
    └── claude/sec-phase5-7-foundation  ← THIS BRANCH
```

## Hard "do NOT" rules

1. **Do NOT remove the legacy-plaintext passthrough** from
   `api/security/token_encryption.decrypt_token` until every
   table's backfill is verified clean.
2. **Do NOT enable Semgrep tenant-isolation rules in ERROR mode**
   on `main` until at least one wave of call-site migration is done
   — the codebase has hundreds of naked `.objects.*` calls today.
   Land it in WARNING mode first.
3. **Do NOT use `tenant_cache.purge_tenant` on a live tenant** —
   it's wired for offboarding only. Wiping caches for an active
   tenant induces a thundering-herd against the DB.
4. **Do NOT use `AdminTask` without security review.** Every new
   one is a chance to leak cross-tenant data.
