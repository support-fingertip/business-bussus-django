"""Phase 3.3 — encrypt OAuth provider tokens at rest.

Switches the following columns from plaintext ``TextField`` to
``EncryptedTextField``:

  * ``user_gmail_tokens.access_token`` / ``.refresh_token``
  * ``user_outlook_tokens.access_token`` / ``.refresh_token``
  * ``lead_capture.page_access_token``

Underlying Postgres column type is unchanged (``text`` → ``text``);
no per-tenant DDL widening is needed. The migration only updates
Django's notion of the field type so the encrypt/decrypt hooks fire.

UserGmailToken / UserOutlookToken are per-tenant (``managed=False``)
so Django won't run DDL against them — but the field-type change is
purely Python-side, so that's fine.

LeadCapture lives in ``public`` schema and is also ``managed=False``
(see api/tenant_models/shared.py for why).

After deploy, run::

    python manage.py encrypt_legacy_oauth_tokens [--dry-run]
"""

from django.db import migrations
import api.security.encrypted_fields


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0010_encrypt_session_log_tokens"),
    ]

    operations = [
        migrations.AlterField(
            model_name="usergmailtoken",
            name="access_token",
            field=api.security.encrypted_fields.EncryptedTextField(
                blank=True, null=True,
            ),
        ),
        migrations.AlterField(
            model_name="usergmailtoken",
            name="refresh_token",
            field=api.security.encrypted_fields.EncryptedTextField(
                blank=True, null=True,
            ),
        ),
        migrations.AlterField(
            model_name="useroutlooktoken",
            name="access_token",
            field=api.security.encrypted_fields.EncryptedTextField(
                blank=True, null=True,
            ),
        ),
        migrations.AlterField(
            model_name="useroutlooktoken",
            name="refresh_token",
            field=api.security.encrypted_fields.EncryptedTextField(
                blank=True, null=True,
            ),
        ),
        migrations.AlterField(
            model_name="leadcapture",
            name="page_access_token",
            field=api.security.encrypted_fields.EncryptedTextField(
                blank=True, null=True,
            ),
        ),
    ]
