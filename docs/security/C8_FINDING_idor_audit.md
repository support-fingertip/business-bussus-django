# C8 finding — IDOR audit result

**Status:** Audit complete. No cross-tenant IDOR code fix required.
**Date:** 2026-05-19

## The question C8 had to answer

When a logged-in user calls `GET /api/leads/<id>` (or PATCH/DELETE),
can they pass **another tenant's** record ID and read/modify it?
This class of bug is called IDOR (Insecure Direct Object Reference).

## How the request actually flows

1. `Dispatcher._init_handler` → `_init_request_context` →
   `pin_request_tenant` → sets `request.tenant_schema` from the
   JWT, reconciled against the DB.
2. `TenantSchemaMiddleware` issues, for the request transaction:
   * `SET LOCAL search_path TO <tenant_schema>, public`
   * `SET LOCAL ROLE tenant_<schema>_role`
3. `get_business_logic` calls
   `get_permissions(request, tableName=object_name, id=id, ...)`.
4. The query runs as e.g. `SELECT ... FROM leads WHERE id = %s`.
   Because `search_path` is pinned, `leads` resolves to
   `tenant_acme.leads`.

## Why cross-tenant IDOR is structurally impossible

Custom business objects (leads, contacts, accounts, opportunities,
etc.) are NOT one shared table with an `organization_id` column.
**Each tenant has its own Postgres schema** containing its own
copy of every object table.

So when a tenant-A user requests a record ID that belongs to
tenant B:

  * The query runs against `tenant_acme.leads` (A's schema).
  * Tenant B's record is in `tenant_beta.leads` — a different
    schema entirely. It is not in A's `leads` table.
  * Result: zero rows → 404 / empty response. There is no row to
    leak.
  * Even if an attacker tried to fully-qualify the name
    (`tenant_beta.leads`), the per-tenant DB role
    (`tenant_acme_role`) has **no USAGE grant on `tenant_beta`** —
    Postgres returns `permission denied for schema tenant_beta`.

Two independent layers (schema separation + DB-role grants) both
block it. There is no ID an attacker can supply that addresses
another tenant's custom-object record.

## Shared tables (users, organizations, etc.)

The handful of tables in `public` that DO hold multiple tenants'
rows (`users`, `organizations`, `user_login_history`, `session_log`,
`lead_capture`) are covered by **Row-Level Security** (migration
0015). A `GET` for another tenant's user id returns zero rows
because the RLS policy filters on `app.current_org_id`.

## What is NOT covered by this finding (and shouldn't be)

**Within-tenant** access — can user A see user B's *private*
record inside the **same** organization? That is an authorization
question, not a tenant-isolation question. It is handled by the
existing permission + sharing layer:

  * `get_permissions` checks `ObjectPermission` / `FieldPermission`.
  * `SharingRecord` governs per-object default access; absence of a
    record means Private (default-deny).

That layer already exists and is a separate subsystem. If the
business wants stricter per-user record visibility, that is a
feature change to the sharing model — not an IDOR fix.

## Recommendation

* **No code change for C8.** Cross-tenant IDOR is prevented by
  architecture, not by per-view checks.
* **Do confirm it empirically** in the external penetration test
  (Stage E) — give the testers accounts in two tenants and have
  them explicitly try ID substitution across `GET/PATCH/DELETE`
  on every object type. Architecture review says it's safe;
  the pen test proves it.

## Why this document instead of code

The C8 task was explicitly conditional: "build the IDOR-fix branch
ONLY if the audit finds gaps." The audit found none — the
schema-per-tenant design plus per-tenant DB roles already close
this class of bug. Writing per-view `organization_id` checks would
be redundant code guarding against an attack the database makes
impossible. The honest output is this finding.
