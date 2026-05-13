"""Phase 3.2 — encrypt TelephonyConfig.authtoken / sid at rest.

The TelephonyConfig table is per-tenant (``managed = False``). This
migration updates Django's notion of the field type; the actual DB
column shape MUST be altered out-of-band on each tenant's schema
because Django won't run DDL against managed=False tables.

Per-tenant operator action
--------------------------

For each tenant schema, the operator runs::

    SET search_path TO <tenant_schema>;
    ALTER TABLE telephony_config
        ALTER COLUMN authtoken TYPE text,
        ALTER COLUMN sid TYPE text;

The change is from ``varchar(512)`` → ``text``. Postgres handles this
without a table rewrite. ``varchar(512)`` would silently truncate
Fernet ciphertext (which adds ~140 chars of overhead) and produce
unrecoverable tokens; the operator DDL MUST run before this code is
deployed to the matching tenant.

A helper script is provided at::

    scripts/per_tenant_alter_encrypt_telephony_tokens.sql

…that templates the ALTER block; operators iterate it over the
tenant list from ``public.organizations``.

After the DDL has run per-tenant, the backfill management command
encrypts any pre-rollout plaintext::

    python manage.py encrypt_legacy_telephony_tokens
"""

from django.db import migrations
import api.security.encrypted_fields


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0010_encrypt_session_log_tokens"),
    ]

    operations = [
        migrations.AlterField(
            model_name="telephonyconfig",
            name="authtoken",
            field=api.security.encrypted_fields.EncryptedTextField(
                blank=True, null=True,
            ),
        ),
        migrations.AlterField(
            model_name="telephonyconfig",
            name="sid",
            field=api.security.encrypted_fields.EncryptedTextField(
                blank=True, null=True,
            ),
        ),
    ]
