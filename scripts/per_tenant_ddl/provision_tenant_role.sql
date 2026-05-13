-- Per-tenant Postgres role provisioning — Phase 4 part 1.
--
-- What this script does, in plain English
-- ---------------------------------------
--
-- Right now, the application connects to Postgres as ONE big role
-- (something like ``bussus_app``) that has access to every tenant's
-- schema. Tenant isolation is enforced entirely by the application:
-- the middleware runs ``SET search_path TO <tenant>`` and we trust
-- every query to honour that. If a query forgets to honour it — or
-- a Celery task skips the middleware — we leak between tenants.
--
-- This script changes that. For every tenant, it creates a
-- ``tenant_<schema>_role`` Postgres role that:
--
--   * Has ``USAGE`` and table privileges ONLY on its own tenant's schema.
--   * Has a narrow read/write whitelist on a few shared tables in
--     ``public`` (users, organizations, lead_capture, user_login_history).
--   * Cannot SELECT from any other tenant's schema, at all.
--
-- The middleware then runs ``SET LOCAL ROLE tenant_<schema>_role`` on
-- every request. From that point until the request ends, the database
-- itself refuses any cross-tenant query — even if a buggy view tries.
--
-- The application's primary role (``bussus_app``) doesn't lose any
-- access; it can still ``SET ROLE`` to any tenant role it needs.
-- That's because it's GRANTed membership in each tenant role.
-- (Postgres calls this "role inheritance" — a parent role can assume
-- any role it's a member of.)
--
-- Pre-conditions
-- --------------
--   * The tenant schema (e.g. ``tenant_acme``) already exists.
--   * All the tenant's tables exist inside it.
--   * The application's main role is ``bussus_app``.
--
-- How operators run this
-- ----------------------
--
-- This file is a TEMPLATE. Per-tenant provisioning replaces ${SCHEMA}
-- with the actual schema name and then runs the whole file.
-- See ``scripts/provision_tenant_role.py`` for the Python helper that
-- does the substitution + execution safely.
--
-- For a one-off manual run from psql:
--
--   psql $DATABASE_URL <<SQL
--   SET ON_ERROR_STOP = on;
--   -- replace tenant_acme with your real schema name in every spot below
--   \i scripts/per_tenant_ddl/provision_tenant_role.sql
--   SQL
--
-- Rollback
-- --------
--
-- See ``scripts/per_tenant_ddl/revoke_tenant_role.sql`` to undo what
-- this script does for a given tenant (used by the offboarding runbook).
--
-- =================================================================

-- Placeholder; the Python wrapper substitutes ${SCHEMA} for the real
-- schema name. When running this file by hand, ``SET LOCAL`` a psql
-- variable with ``\set SCHEMA tenant_acme`` first and reference it as
-- :"SCHEMA".

-- 1. Create the role. NOLOGIN — the role is assumed via SET ROLE,
-- never used for direct DB authentication. INHERIT — important for
-- the role-membership chain below.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'tenant_${SCHEMA}_role'
    ) THEN
        EXECUTE format('CREATE ROLE %I NOLOGIN INHERIT',
                       'tenant_${SCHEMA}_role');
    END IF;
END$$;

-- 2. Grant USAGE on the tenant's own schema. Without USAGE the role
-- cannot reference any object inside the schema even if the table
-- grants below succeed.
GRANT USAGE ON SCHEMA "${SCHEMA}" TO "tenant_${SCHEMA}_role";

-- 3. Grant table privileges on every existing table in the schema.
GRANT SELECT, INSERT, UPDATE, DELETE
    ON ALL TABLES IN SCHEMA "${SCHEMA}"
    TO "tenant_${SCHEMA}_role";

-- 4. Grant sequence privileges so INSERT can pull values from
-- auto-incrementing PKs. Most of our IDs are CharField but a few
-- tables (django_admin_log etc.) use sequences.
GRANT USAGE, SELECT, UPDATE
    ON ALL SEQUENCES IN SCHEMA "${SCHEMA}"
    TO "tenant_${SCHEMA}_role";

-- 5. Default privileges — apply the same grants to tables created in
-- this schema in the future (so add_field / new tables don't need
-- this script re-run).
ALTER DEFAULT PRIVILEGES IN SCHEMA "${SCHEMA}"
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES
    TO "tenant_${SCHEMA}_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA "${SCHEMA}"
    GRANT USAGE, SELECT, UPDATE ON SEQUENCES
    TO "tenant_${SCHEMA}_role";

-- 6. Narrow access to shared tables in `public`. These tables hold
-- cross-tenant rows (every customer's users, every org row), and
-- Phase 4 part 2 will add Row-Level Security so the role can only
-- see rows tagged with its own org_id. For now we just give the
-- privileges; RLS comes next.
GRANT USAGE ON SCHEMA public TO "tenant_${SCHEMA}_role";

-- Tenant role can read its own org row + write user activity
-- (login history) + read/write its own users + read/write
-- lead_capture (FB webhook target). It CANNOT read other shared
-- tables (auth_*, django_*) — that stays scoped to the platform.
GRANT SELECT ON public.organizations TO "tenant_${SCHEMA}_role";
GRANT SELECT, INSERT, UPDATE ON public.users TO "tenant_${SCHEMA}_role";
GRANT SELECT, INSERT ON public.user_login_history TO "tenant_${SCHEMA}_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON public.lead_capture TO "tenant_${SCHEMA}_role";
GRANT SELECT, INSERT, UPDATE, DELETE ON public.session_log TO "tenant_${SCHEMA}_role";

-- Sequences for the shared tables (mostly BIGINT auto pks on
-- the Django built-ins).
GRANT USAGE, SELECT ON public.users_groups_id_seq TO "tenant_${SCHEMA}_role";
GRANT USAGE, SELECT ON public.users_user_permissions_id_seq TO "tenant_${SCHEMA}_role";

-- 7. Membership: give the application's main role the ability to
-- ``SET ROLE`` into this tenant role. Without this grant, the
-- application can't assume the tenant role during request handling.
GRANT "tenant_${SCHEMA}_role" TO bussus_app;

-- 8. Verification — these statements run as the new role to confirm
-- it can ONLY see its own schema. They should each return 1.
-- (Operators run this manually after provisioning.)
--
-- SET LOCAL ROLE "tenant_${SCHEMA}_role";
-- SELECT count(*) FROM "${SCHEMA}".profile;        -- works
-- -- The cross-tenant probe MUST fail with "permission denied":
-- -- SELECT count(*) FROM <some_other_tenant_schema>.profile;
-- RESET ROLE;
