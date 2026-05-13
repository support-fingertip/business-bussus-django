-- Revoke + drop the per-tenant Postgres role — Phase 4 part 1.
--
-- The inverse of ``provision_tenant_role.sql``. Used during tenant
-- offboarding (see ``docs/runbooks/tenant_offboard.md``).
--
-- Order of operations matters: revoke grants BEFORE dropping the role,
-- otherwise Postgres refuses the DROP because objects still depend on it.

-- 1. Take away every privilege the role currently holds.
REVOKE ALL ON ALL TABLES IN SCHEMA "${SCHEMA}" FROM "tenant_${SCHEMA}_role";
REVOKE ALL ON ALL SEQUENCES IN SCHEMA "${SCHEMA}" FROM "tenant_${SCHEMA}_role";
REVOKE ALL ON SCHEMA "${SCHEMA}" FROM "tenant_${SCHEMA}_role";

REVOKE ALL ON public.organizations         FROM "tenant_${SCHEMA}_role";
REVOKE ALL ON public.users                 FROM "tenant_${SCHEMA}_role";
REVOKE ALL ON public.user_login_history    FROM "tenant_${SCHEMA}_role";
REVOKE ALL ON public.lead_capture          FROM "tenant_${SCHEMA}_role";
REVOKE ALL ON public.session_log           FROM "tenant_${SCHEMA}_role";
REVOKE USAGE ON SCHEMA public              FROM "tenant_${SCHEMA}_role";

-- 2. Drop the default-privilege rules created for this schema.
ALTER DEFAULT PRIVILEGES IN SCHEMA "${SCHEMA}"
    REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES
    FROM "tenant_${SCHEMA}_role";
ALTER DEFAULT PRIVILEGES IN SCHEMA "${SCHEMA}"
    REVOKE USAGE, SELECT, UPDATE ON SEQUENCES
    FROM "tenant_${SCHEMA}_role";

-- 3. Revoke the membership on bussus_app so it can no longer SET ROLE.
REVOKE "tenant_${SCHEMA}_role" FROM bussus_app;

-- 4. Drop the role itself.
DROP ROLE IF EXISTS "tenant_${SCHEMA}_role";
