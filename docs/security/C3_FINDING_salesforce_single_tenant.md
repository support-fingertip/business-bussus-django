# C3 finding — Salesforce integration is single-tenant by design

**Status:** Finding, not a fix. Read before using Salesforce sync with more than one customer.
**Date:** 2026-05-19

## What the code-hardening plan assumed

The C3 task said: "wrap the Salesforce sync inner loop in
`with_tenant_schema()`." That assumed the integration was
multi-tenant and just missing a tenant pin.

## What is actually true

It is not. The Salesforce integration is **architecturally
single-tenant**:

| Model | Tenant link? |
|---|---|
| `SalesforceSettings` (the SF credentials) | ❌ No `organization_id` — ONE global row |
| `SalesforceSync` (per-object sync config) | ❌ No `organization_id` — global rows keyed only by `object_name` |
| `SalesforceMetadata` | ❌ No `organization_id` |
| `sf_integration_<object>` staging tables | Global tables in `public`, written via a direct `psycopg2.connect(DB_CONFIG)` |

There is exactly **one** Salesforce connection for the whole
platform. The sync task (`process_salesforce_sync`) iterates
`SalesforceSync` rows — but those rows are not owned by any tenant.

## Why you cannot "just add `with_tenant_schema()`"

`with_tenant_schema(schema)` needs a schema. The inner loop has no
way to know which tenant a `SalesforceSync` row belongs to —
because the row belongs to no tenant. The data has nowhere
tenant-specific to go.

## The real risk assessment

| Scenario | Risk |
|---|---|
| **One** customer uses Salesforce sync | **None.** Single tenant → no cross-tenant mixing possible. Safe as-is. |
| **Multiple** customers configure Salesforce sync | **Real.** All their SF data flows through the same global `sf_integration_<object>` staging tables and the same global `SalesforceSettings`. Customer B could see customer A's synced records. |

Today the model only supports ONE `SalesforceSettings` row, so in
practice only one SF account can be connected at a time. The risk
is **latent**, not active — it becomes real the moment the product
tries to offer Salesforce sync as a per-customer feature.

## The honest recommendation

**Do not ship Salesforce sync as a multi-tenant feature without
the re-architecture below.** Pick one:

### Option A — keep it single-tenant (cheapest)
Gate the feature: only the platform operator configures the one SF
connection. Don't expose SF sync in the customer-facing UI.
Effort: ~1 day (add a feature flag / hide the UI).

### Option B — make it genuinely multi-tenant (a project)
1. Add `organization_id` to `SalesforceSettings`, `SalesforceSync`,
   `SalesforceMetadata` (+ migrations + backfill).
2. Make `sf_integration_<object>` staging tables either per-tenant
   (move into each tenant schema) OR add `organization_id` + RLS.
3. Rewrite `process_salesforce_sync` to iterate
   `Organization.objects.filter(is_active=True)` and, for each,
   open `with_tenant_schema(org.database_schema)`.
4. Replace the direct `psycopg2.connect(DB_CONFIG)` in
   `push_data_to_salesforce` with the tenant-pinned connection.
5. Per-tenant SF OAuth credentials (each customer connects their
   own Salesforce org).

Effort: ~2-3 weeks. This is a feature project, not a hardening fix.

## Decision needed from the product owner

> Does Bussus need to offer Salesforce sync to **multiple**
> customers, each syncing **their own** Salesforce org?

- **No / not yet** → Option A. Hide the feature, revisit later.
- **Yes** → Option B. Schedule it as its own project with its
  own design review. It is out of scope for the security-hardening
  pass.

## Why this document exists instead of a code change

The user asked for "real problems and real fixes, no
over-hallucinated fixation." Wrapping the loop in
`with_tenant_schema()` would have been a fake fix — it would not
compile (no schema to pass) and would not address the actual
single-tenant architecture. The honest engineering output here is
this finding + a decision request, not code.
