# Phase 1 — Operator Notes

Phase 1 lays the foundation that Phases 2–6 build on. It introduces no
user-visible features. Three things land:

1. **Schema authority** — every authenticated request now reconciles
   the user's org / schema / profile against the database before any
   downstream code runs.
2. **Dynamic-object gateway scaffold** — a hardened entrypoint for raw
   SQL on custom-business-object tables, feature-flagged off until
   Phase 2 wires it in.
3. **Observability + health endpoints + test harness** — structured
   logging with correlation IDs, `/healthz` / `/readyz` / `/livez`
   probes, and a pytest-based test suite.

## Required environment variables

### `SCHEMA_AUTHORITY_ENFORCE` (default `1`)

Controls whether `assert_pinned_schema()` raises on a kwarg/pinned
mismatch. Phase 1 ships with enforce mode ON because no caller yet
relies on the helper. During Phase 2 migration we'll **temporarily**
flip it to `0` (log-only) for the rollout window.

Operator: leave at default unless instructed otherwise.

### `LOG_FORMAT` (default `text`, set to `json` in production)

Selects the log formatter. JSON output is structured for ingestion by
Datadog / Loki / CloudWatch Insights. Each line carries:

```json
{"ts": "...", "level": "INFO", "logger": "...", "trace_id": "...",
 "tenant_id": "...", "user_id": "...", "msg": "..."}
```

### `LOG_LEVEL` (default `INFO`)

Standard Python `logging` level name.

### `USE_DYNAMIC_GATEWAY` (default `0` — off)

Phase 1 scaffold flag. The dynamic-object gateway is built and unit-
tested but not wired into BL. Leave off in Phase 1; Phase 2 enables it
behind a per-tenant rollout.

## Health probes

Three new endpoints (unauthenticated, no body):

| Path | Semantics | Use for |
|---|---|---|
| `/healthz` | Liveness — process responsive | k8s `livenessProbe` |
| `/livez` | Alias for `/healthz` | Some orchestrators |
| `/readyz` | Readiness — DB + cache reachable | k8s `readinessProbe`, ALB target group health |

`/readyz` returns 200 with per-component status when healthy and 503 with
the same shape when degraded — dashboards can scrape it directly.

## Schema authority — what's enforced now

The `Dispatcher._init_request_context` calls `pin_request_tenant`. This
verifies that the JWT's claimed `(org_id, schema, profile_id)` actually
belong to the authenticated user. Mismatches raise `PermissionError`
which the view methods convert to **403** (no information disclosure to
the client; full detail logged with trace_id).

Three trust attributes are written on the request:

- `request.tenant_schema` (canonical schema name)
- `request.tenant_org_id` (canonical org id)
- `request.tenant_profile_id` (canonical profile id)

For backward compatibility, the legacy `request.schema` and
`request.profile_id` attributes are still populated with the same
canonical values; new code should read the `tenant_*` versions.

## Running the tests

```bash
# Unit tests (no DB, no Django boot)
python -m pytest tests/ -m unit

# All tests
python -m pytest tests/
```

The harness uses `pytest-django`'s `DJANGO_SETTINGS_MODULE` declaration
in `pytest.ini`. Most Phase 1 tests are pure unit tests with stubbed
DB; integration tests in later phases will require a real test DB.

## Pre-deploy checklist

- [ ] `LOG_FORMAT=json` set in production env.
- [ ] `/healthz`, `/readyz`, `/livez` wired into k8s/ALB probes (replace whatever exists today).
- [ ] Sanity test: forged JWT with another tenant's `profile_id` → 403.
- [ ] Sanity test: anonymous request to any `/v2/api/...` → 401 (still gated by Phase 0's `IsAuthenticated`).
- [ ] Sanity test: request from active user with valid JWT → 2xx, response carries `X-Request-ID` header.

## Known follow-ups (Phase 2 scope)

- Replace every `kwargs.get('schema')` read in BL/permissions/ORM with
  `request.tenant_schema`. Grep target: 70+ files.
- Wire the dynamic-object gateway into BL behind a per-tenant feature
  flag.
- Object-name whitelist in dispatcher, validated against
  `metadata_loader.list_business_objects(schema)`.
- TOCTOU fix on the update path (Phase 2.A).
