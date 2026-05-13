-- Row-Level Security for shared `public` tables — Phase 4 part 2.
--
-- In plain English
-- ----------------
--
-- Phase 4 part 1 made each tenant assume a Postgres role
-- (``tenant_<schema>_role``) that has permissions ONLY on its own
-- schema. That stops cross-tenant access to per-tenant tables
-- (every customer's `leads`, `contacts`, etc. live in different
-- schemas).
--
-- But four tables in the `public` schema hold rows from EVERY
-- tenant in one table:
--   * public.organizations       — one row per customer
--   * public.users               — every customer's users
--   * public.user_login_history  — every login event
--   * public.session_log         — every active session
--   * public.lead_capture        — Facebook lead-ads configs
--
-- A tenant role has access to these tables (it has to — login
-- needs to look up users, etc.). Without RLS, tenant A's role
-- could `SELECT * FROM users` and see every customer's users.
--
-- RLS adds a `WHERE` clause Postgres enforces on every query:
--
--     USING (organization_id = current_setting('app.current_org_id'))
--
-- The application's middleware sets `app.current_org_id` on every
-- request (via `SET LOCAL app.current_org_id = <org>`). From that
-- point, any SELECT against these tables is silently filtered to
-- the current tenant's rows. Trying to read another org's rows
-- doesn't error — it returns zero rows. (For DELETE / UPDATE / INSERT
-- the WITH CHECK clause additionally blocks writes.)
--
-- Roll-out safety
-- ---------------
--
-- We DON'T use `FORCE ROW LEVEL SECURITY` in this script. Without
-- FORCE, the table owner (your main DB role, e.g. `bussus_app`)
-- BYPASSES the policy. That means:
--   * Management commands, ops queries, migrations: keep working
--   * Per-request queries (running as tenant_<schema>_role): subject to RLS
--
-- This is intentional during rollout. Once Phase 4 part 2 is soaked
-- in production, flip FORCE on for the final tightening (see
-- `enable_rls_force.sql` — separate script).
--
-- Pre-conditions
-- --------------
--
--   * Migration 0012 has been applied (organization_id columns exist).
--   * `backfill_organization_id` management command has been run.
--   * Per-tenant roles exist (Phase 4 part 1 completed).
--   * Application's main role is named `bussus_app` (or update below).
--
-- Idempotency
-- -----------
--
-- Every statement uses `IF EXISTS` / `IF NOT EXISTS` where Postgres
-- supports it. Re-running this script is safe.

-- ==========================================================
-- public.organizations
-- ==========================================================
--
-- Each tenant should only see its OWN organization row. The
-- predicate matches the row's `id` (the org's primary key) against
-- the current request's pinned org id.

ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation_select ON public.organizations;
CREATE POLICY tenant_isolation_select
    ON public.organizations
    FOR SELECT
    USING (id = current_setting('app.current_org_id', true));

-- ==========================================================
-- public.users
-- ==========================================================
--
-- Read: only this tenant's users.
-- Write: only this tenant's users.

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON public.users;
CREATE POLICY tenant_isolation
    ON public.users
    FOR ALL
    USING  (organization_id = current_setting('app.current_org_id', true))
    WITH CHECK (organization_id = current_setting('app.current_org_id', true));

-- ==========================================================
-- public.user_login_history
-- ==========================================================

ALTER TABLE public.user_login_history ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON public.user_login_history;
CREATE POLICY tenant_isolation
    ON public.user_login_history
    FOR ALL
    USING  (organization_id = current_setting('app.current_org_id', true))
    WITH CHECK (organization_id = current_setting('app.current_org_id', true));

-- ==========================================================
-- public.session_log
-- ==========================================================

ALTER TABLE public.session_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON public.session_log;
CREATE POLICY tenant_isolation
    ON public.session_log
    FOR ALL
    USING  (organization_id = current_setting('app.current_org_id', true))
    WITH CHECK (organization_id = current_setting('app.current_org_id', true));

-- ==========================================================
-- public.lead_capture
-- ==========================================================
--
-- Already has organization_id from Phase 4.A. No backfill needed.

ALTER TABLE public.lead_capture ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON public.lead_capture;
CREATE POLICY tenant_isolation
    ON public.lead_capture
    FOR ALL
    USING  (organization_id = current_setting('app.current_org_id', true))
    WITH CHECK (organization_id = current_setting('app.current_org_id', true));

-- ==========================================================
-- Verification
-- ==========================================================
--
-- After running this script, verify policies exist:
--
--   SELECT schemaname, tablename, policyname, cmd, qual
--   FROM pg_policies
--   WHERE schemaname = 'public'
--   ORDER BY tablename, policyname;
--
-- Should show one tenant_isolation policy per table.
--
-- Test the policy by assuming a tenant role + setting org_id:
--
--   SET LOCAL ROLE tenant_acme_role;
--   SET LOCAL app.current_org_id = 'org_acme';
--   SELECT count(*) FROM public.users;
--   -- Returns count for org_acme only
--
--   SET LOCAL app.current_org_id = 'org_other';
--   SELECT count(*) FROM public.users;
--   -- Returns 0 (no rows for the un-pinned org)
--   RESET ROLE;
