"""Enable RLS on shared `public` tables — Phase 4 part 2.

In plain English
----------------

Adds the Row-Level Security policies that turn shared-table access
into per-tenant queries. After this migration, a tenant role
running a ``SELECT * FROM public.users`` only sees rows where
``organization_id`` matches the current request's pinned tenant.

This migration runs the same DDL as
``scripts/per_tenant_ddl/enable_rls_shared_tables.sql`` but through
Django's migration machinery so it runs once per environment and
is tracked in ``django_migrations``.

NOT using FORCE ROW LEVEL SECURITY
-----------------------------------

Without FORCE, the table OWNER (the main app role, e.g. ``bussus_app``)
bypasses the policy. That's intentional for the initial rollout:

  * Management commands keep working (they run as the main role).
  * Migrations keep working.
  * Per-request queries (running as ``tenant_<schema>_role``) ARE
    subject to RLS.

Once Phase 4 part 2 is soaked, a follow-up migration adds FORCE so
even the main role is subject to the policy (extreme defence-in-depth
for ops paths).

Pre-conditions
--------------

  * Migration 0012 has been applied (organization_id columns exist).
  * ``backfill_organization_id`` has been run (no NULL organization_id
    rows in session_log / user_login_history).
  * Per-tenant roles exist (Phase 4 part 1).

Rollback
--------

The migration is reversible: ``migrate api 0012_…`` drops every
policy and disables RLS. No data is lost. Roll back BEFORE flipping
FORCE on — once FORCE is on, ops queries running as the main role
will start hitting the policy and need ``app.current_org_id`` set.
"""

from django.db import migrations


# RLS DDL — kept in this module so Django migrations are the source of
# truth. The .sql script in scripts/per_tenant_ddl/ is a copy for
# manual operator use; both should agree.

ENABLE_RLS_SQL = """
-- public.organizations: each tenant sees its own row only
ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_select ON public.organizations;
CREATE POLICY tenant_isolation_select
    ON public.organizations
    FOR SELECT
    USING (id = current_setting('app.current_org_id', true));

-- public.users: read/write only this tenant's users
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.users;
CREATE POLICY tenant_isolation
    ON public.users
    FOR ALL
    USING  (organization_id = current_setting('app.current_org_id', true))
    WITH CHECK (organization_id = current_setting('app.current_org_id', true));

-- public.user_login_history
ALTER TABLE public.user_login_history ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.user_login_history;
CREATE POLICY tenant_isolation
    ON public.user_login_history
    FOR ALL
    USING  (organization_id = current_setting('app.current_org_id', true))
    WITH CHECK (organization_id = current_setting('app.current_org_id', true));

-- public.session_log
ALTER TABLE public.session_log ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.session_log;
CREATE POLICY tenant_isolation
    ON public.session_log
    FOR ALL
    USING  (organization_id = current_setting('app.current_org_id', true))
    WITH CHECK (organization_id = current_setting('app.current_org_id', true));

-- public.lead_capture (already has organization_id column from Phase 4.A)
ALTER TABLE public.lead_capture ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON public.lead_capture;
CREATE POLICY tenant_isolation
    ON public.lead_capture
    FOR ALL
    USING  (organization_id = current_setting('app.current_org_id', true))
    WITH CHECK (organization_id = current_setting('app.current_org_id', true));
"""


DISABLE_RLS_SQL = """
DROP POLICY IF EXISTS tenant_isolation_select ON public.organizations;
ALTER TABLE public.organizations DISABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON public.users;
ALTER TABLE public.users DISABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON public.user_login_history;
ALTER TABLE public.user_login_history DISABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON public.session_log;
ALTER TABLE public.session_log DISABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON public.lead_capture;
ALTER TABLE public.lead_capture DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0012_add_organization_id_to_shared_tables"),
    ]

    operations = [
        migrations.RunSQL(
            sql=ENABLE_RLS_SQL,
            reverse_sql=DISABLE_RLS_SQL,
        ),
    ]
