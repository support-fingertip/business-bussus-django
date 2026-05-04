# ADR 0002 — Schema Authority Middleware

**Status:** Accepted
**Date:** 2026-05-03
**Phase:** 1 (Foundations)

## Context

The platform is multi-tenant via PostgreSQL schemas: every tenant
(organization) gets its own schema, and queries pick the right tenant via
`SET search_path TO <schema>`. The audit found this scheme broken in
practice:

1. **`kwargs.get('schema')` everywhere.** Every BL/permissions/ORM
   function takes a `schema` keyword and uses it without verifying it
   belongs to the calling user. A forged JWT or a buggy caller can route
   a query into another tenant's schema.
2. **`profile_id` from JWT is never validated** against the org's
   `profile` table. A forged JWT carrying a profile_id from another
   tenant slips past authentication and hits the permission layer with
   ambient cross-tenant authority.
3. **70+ files read `schema` from kwargs**, making the boundary
   impossible to audit and trivial to break in code review.

## Decision

Introduce **one canonical resolution point** that runs once per request:
`api.security.schema_authority.pin_request_tenant(request, ...)`.

After it returns successfully:

- `request.tenant_schema` — canonical schema name (validated against the database)
- `request.tenant_org_id` — canonical organization id
- `request.tenant_profile_id` — canonical profile id (verified to live in that schema)

These three attributes are the **only trusted source** of tenant
identity from this point forward. Every layer (BL, permissions, ORM,
gateway) reads from these — never from kwargs.

For migration safety, an `assert_pinned_schema(request, schema)` helper
lets legacy callers that still receive `schema` as a kwarg verify it
matches the pinned value, with a `SCHEMA_AUTHORITY_ENFORCE=0` soak mode
that logs violations without blocking.

## Rationale

1. **Single source of truth.** One file reconciles JWT claims with the
   database; everywhere else just reads `request.tenant_schema`.
2. **Defence in depth.** Even if a callsite bug reintroduces a kwarg
   read, the helper catches it.
3. **Reviewable.** A grep for `kwargs.get('schema')` becomes a useful
   signal of "this code hasn't been migrated yet."
4. **Identifier safety baked in.** `pin_request_tenant` runs the
   canonical schema through `validate_identifier`, so SQL builders
   downstream don't have to.

## Reconciliation algorithm

```
Given: user_id (from JWT), asserted_org_id, asserted_schema, asserted_profile_id (from JWT/session)

1. canonical_org_id  ← SELECT organization_id FROM public.users WHERE id = user_id
2. If asserted_org_id is set and ≠ canonical_org_id  → TenantViolation
3. canonical_schema  ← SELECT database_schema FROM public.organizations
                        WHERE id = canonical_org_id AND is_active
4. validate_identifier(canonical_schema, "schema")
5. If asserted_schema is set and ≠ canonical_schema  → TenantViolation
6. If asserted_profile_id is set:
   SELECT 1 FROM <canonical_schema>.profile WHERE id = asserted_profile_id
   If no row                                     → TenantViolation
7. Pin (canonical_org_id, canonical_schema, asserted_profile_id) on request.
```

## Migration plan

| Phase | Action |
|---|---|
| 1 | Build `schema_authority.py`; wire into `Dispatcher._init_request_context`. Legacy `request.schema` / `request.profile_id` kept populated for backward compat. |
| 2 | Begin replacing `kwargs.get('schema')` reads with `request.tenant_schema`. Run with `SCHEMA_AUTHORITY_ENFORCE=0` (soak) for one week to surface laggards in logs. |
| 3 | Flip to `SCHEMA_AUTHORITY_ENFORCE=1`. Pre-commit hook to flag any new `kwargs.get('schema')` reads (TBD). |
| 4 | Delete legacy `request.schema` / `request.profile_id` attributes. |

## Consequences

**Accepted:**
- Every authenticated request makes 3 small DB lookups (org, schema, profile). Profile cache is in-tenant; other two are tiny tables. Negligible.
- Background tasks (Celery, Channels consumers) don't go through this middleware — they explicitly carry tenant context in task payload.
- A user with a stale JWT after their org is deactivated gets 403 instead of "weird empty results."

**Risk:**
- During the soak window, log volume of `assert_pinned_schema` warnings may be high while legacy callers are migrated. Use Sentry/structured-log filters to track without burying real signal.

## Alternatives Considered

| Option | Why rejected |
|---|---|
| Validate `schema` in every layer | Status quo; we know it doesn't work because nobody does it |
| Use Postgres row-level security | Would help, but doesn't address the pre-DB-call validation gap and requires per-tenant role provisioning |
| Use `django-tenants` | Already a dep, but bypassed by the raw-SQL-everywhere pattern. Adopting it is a separate refactor (Phase 5+). |
