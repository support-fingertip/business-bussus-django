# ADR 0004 — Multi-tenant zero-leak architecture

**Status:** Proposed
**Date:** 2026-05-13
**Phase:** Launch-readiness

## Context

Today's multi-tenant model relies on a single layer of enforcement:
`TenantSchemaMiddleware` issues `SET search_path` per request after
`schema_authority.pin_request_tenant` reconciles the JWT against the
DB. If that middleware is bypassed (forgotten Celery task, raw SQL
path, management command, future code that uses the wrong manager),
the connection's search_path falls back to `public` — or worse,
inherits a previous request's value from the connection pool.

For a paid multi-tenant SaaS, a single cross-tenant leak is a
business-ending event. The architecture must make cross-tenant access
require the simultaneous failure of multiple independent layers, not
just one.

## Decision

Adopt a **five-layer defence-in-depth** model. Any single layer must
be sufficient to prevent cross-tenant access; the other four exist so
that a bug in one layer cannot cause a leak.

| Layer | Mechanism |
|---|---|
| **L1 — Auth/identity** | JWT signed; `schema_authority.resolve_tenant` reconciles claimed `org_id` against `public.users.organization_id` |
| **L2 — Application** | `request.tenant_schema` is the only trusted source. `kwargs.get('schema')` is banned. |
| **L3 — ORM/query** | Tenant-aware manager requires explicit context; raw SQL routes through an audited helper. |
| **L4 — Database role** | App assumes a per-tenant Postgres role (`tenant_<schema>_role`) that has `USAGE` only on its tenant schema. Shared tables enforce RLS keyed on `current_setting('app.current_org_id')`. |
| **L5 — Infrastructure** | Redis keys namespaced per tenant; object-storage prefixes per tenant with IAM policies; per-tenant data-encryption keys derived from a single KEK. |

## Consequences

- **Onboarding a new tenant** is now a multi-step DB + infra operation,
  not just an `INSERT` into `organizations`. Automated via
  `scripts/provision_customer.sh` (Phase 6 of launch plan).
- **Backups** must preserve the per-tenant DB role + RLS policies.
- **Background work** must carry `TenantContext` end-to-end — see Phase 6.
- **Existing call sites** that use `.objects.all()` or `connection.cursor()`
  directly are migrated to `for_tenant(ctx)` / `tenant_cursor(ctx)`.
  Semgrep rules enforce the migration over time.

See `docs/security/launch_readiness_plan.md` for the implementation
sequence and effort estimates.
