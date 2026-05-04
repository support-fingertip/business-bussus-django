"""Phase 4.A — register LeadCapture in Django state (shared/public schema).

``lead_capture`` is a SHARED table — lives in the ``public`` schema
and rows are scoped by ``organization_id`` rather than by per-tenant
search_path. See ``api/ORM/sqlFunctions/getQueryBuilder.py:SHARED_TABLES``
for the canonical shared-table list.

Before Phase 4.A there was no Django model and no canonical DDL for
``lead_capture``. The runtime queried it from raw cursor at
``facebook/leadwebhook.py:159``. The shape was inferred from
``files/fields_inserts_no_id.sql:2206-2284`` (the field registry —
strongest evidence), and canonical DDL now lives at
``sqlfiles/shared_tables.sql``.

Same pattern as 0007/0008: ``managed = False`` +
``SeparateDatabaseAndState`` with empty ``database_operations`` —
Django registers the model in its state but does NOT run DDL.
Operators apply ``sqlfiles/shared_tables.sql`` by hand AFTER
introspecting any existing production table to confirm the column
shape matches.

After this migration the per-tenant model coverage is **49/49 = 100%**
and the shared-table gap from Phase 2/3 is closed.
"""

from __future__ import annotations

from django.db import migrations, models


_STATE_OPERATIONS = [
    migrations.CreateModel(
        name="LeadCapture",
        fields=[
            ("id", models.CharField(max_length=64, primary_key=True, serialize=False)),
            ("organization_id", models.CharField(db_index=True, max_length=64)),
            ("lead_page_id", models.CharField(blank=True, max_length=255, null=True)),
            ("lead_page_name", models.CharField(blank=True, max_length=255, null=True)),
            ("lead_form_id", models.CharField(blank=True, db_index=True, max_length=255, null=True)),
            ("lead_form_name", models.CharField(blank=True, max_length=255, null=True)),
            ("page_access_token", models.TextField(blank=True, null=True)),
            ("form_status", models.CharField(blank=True, max_length=64, null=True)),
            ("field_mapping", models.JSONField(blank=True, null=True)),
            ("task_status", models.CharField(blank=True, max_length=64, null=True)),
            ("webhook_url", models.CharField(blank=True, max_length=2048, null=True)),
            ("created_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("last_modified_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("owner_id", models.CharField(blank=True, max_length=64, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Lead Capture",
            "verbose_name_plural": "Lead Captures",
            "db_table": "lead_capture",
            "managed": False,
        },
    ),
]


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0008_phase4a_org_company"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=_STATE_OPERATIONS,
        ),
    ]
