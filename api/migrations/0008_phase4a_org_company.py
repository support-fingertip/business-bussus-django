"""Phase 4.A — register OrgCompany in Django state.

The ``org_company`` table's CREATE TABLE block in default_tables.sql
was previously fully commented out — every column line including the
closing ``);`` was prefixed with ``--``. As a result the table did
NOT exist in newly-provisioned tenants.

Phase 4.A un-comments the DDL block and adds the OrgCompany Django
model so the ORM can address it without raw cursors.

Same pattern as 0005-0007: ``managed = False`` +
``SeparateDatabaseAndState`` with empty ``database_operations`` —
Django registers the model in its state but does NOT run DDL.
Operators are responsible for applying the un-commented DDL to
existing tenants (see docs/PHASE4_A_OPERATOR_NOTES.md).

After this migration the tenant-model coverage is **49/49 = 100%**.
"""

from __future__ import annotations

from django.db import migrations, models


def _id_field():
    return models.CharField(max_length=64, primary_key=True, serialize=False)


_STATE_OPERATIONS = [
    migrations.CreateModel(
        name="OrgCompany",
        fields=[
            ("id", _id_field()),
            ("company_name", models.CharField(max_length=255)),
            ("primary_contact", models.CharField(blank=True, max_length=255, null=True)),
            ("division", models.CharField(blank=True, max_length=255, null=True)),
            ("phone", models.CharField(blank=True, max_length=64, null=True)),
            ("fax", models.CharField(blank=True, max_length=64, null=True)),
            ("email", models.CharField(blank=True, max_length=255, null=True)),
            ("website", models.CharField(blank=True, max_length=512, null=True)),
            ("street", models.CharField(blank=True, max_length=512, null=True)),
            ("city", models.CharField(blank=True, max_length=255, null=True)),
            ("state", models.CharField(blank=True, max_length=255, null=True)),
            ("postal_code", models.CharField(blank=True, max_length=32, null=True)),
            ("country", models.CharField(blank=True, max_length=255, null=True)),
            ("default_currency", models.CharField(default="USD", max_length=8)),
            ("default_language", models.CharField(default="en", max_length=8)),
            ("timezone", models.CharField(default="UTC", max_length=64)),
            ("fiscal_year_start_month", models.CharField(default="April", max_length=16)),
            ("description", models.TextField(blank=True, null=True)),
            ("logo", models.CharField(blank=True, max_length=2048, null=True)),
            ("created_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("last_modified_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("deleted_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("is_deleted", models.BooleanField(default=False)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
            ("deleted_date", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Organization Company",
            "verbose_name_plural": "Organization Companies",
            "db_table": "org_company",
            "managed": False,
        },
    ),
]


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0007_phase3b_tenant_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=_STATE_OPERATIONS,
        ),
    ]
