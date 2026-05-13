"""Add ``organization_id`` to ``session_log`` and ``user_login_history``.

Phase 4 part 2 of the launch-readiness plan.

In plain English
----------------

Row-Level Security (RLS) needs a column on every row to filter by.
For tenant-scoped tables that already live in each tenant's schema,
this is implicit (the schema name IS the tenant). For SHARED tables
in ``public`` (cross-tenant rows in one table), we need an explicit
``organization_id`` so RLS policies can say::

    USING (organization_id = current_setting('app.current_org_id'))

Two tables need this column added:
  * ``public.session_log``      — currently only has ``user_id``
  * ``public.user_login_history`` — same

Both can be filled in from the user's ``organization_id``. The
``backfill_organization_id`` management command does that work
incrementally so a large user table doesn't lock for hours.

The column is added NULLABLE in this migration so existing rows
don't fail the ALTER. A follow-up migration tightens it to NOT NULL
after the backfill has run + verified.

Postgres handles ``ADD COLUMN ... NULL`` instantly (no table rewrite)
since Postgres 11+ for non-volatile defaults. We pass no default
here so it's an O(1) DDL.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        # final-bussiness-backend merge: renumbered from 0012 → 0014.
        # A1 took 0011 (telephony); A2 became 0012 (oauth); A3 became 0013
        # (user_app_password). Phase 4 part 2 chains after all three.
        ("api", "0013_encrypt_user_app_password"),
    ]

    operations = [
        migrations.AddField(
            model_name="sessionlog",
            name="organization_id",
            field=models.CharField(
                blank=True, db_index=True, max_length=64, null=True,
            ),
        ),
        migrations.AddField(
            model_name="userloginhistory",
            name="organization_id",
            field=models.CharField(
                blank=True, db_index=True, max_length=64, null=True,
            ),
        ),
    ]
