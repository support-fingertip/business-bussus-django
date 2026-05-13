"""Phase 3.4 — encrypt SalesforceSettings.password / client_secret at rest.

Switches both columns from ``CharField(255)`` → ``EncryptedCharField(1024)``.
Postgres handles the ``varchar(255) → varchar(1024)`` widen without a
table rewrite.

Salesforce settings is a singleton-ish admin-level table that lives in
the ``public`` schema (Django-managed), so this migration runs against
the primary DB exactly once.

Operator: after deploy, run::

    python manage.py encrypt_legacy_salesforce_creds
"""

from django.db import migrations
import api.security.encrypted_fields


class Migration(migrations.Migration):

    dependencies = [
        ("sf_integration", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="salesforcesettings",
            name="password",
            field=api.security.encrypted_fields.EncryptedCharField(max_length=1024),
        ),
        migrations.AlterField(
            model_name="salesforcesettings",
            name="client_secret",
            field=api.security.encrypted_fields.EncryptedCharField(max_length=1024),
        ),
    ]
