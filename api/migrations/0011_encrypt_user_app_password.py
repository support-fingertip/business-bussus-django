"""Phase 3.5 — encrypt User.app_password at rest.

Switches ``users.app_password`` from ``CharField(128)`` →
``EncryptedCharField(512)``. Postgres handles
``varchar(128) → varchar(512)`` without a table rewrite.

``app_password`` is the per-user SMTP application password (for outbound
mail through user-owned providers). Storing it plaintext meant a
``users`` table dump exposed every customer's SMTP credentials.

Operator: after deploy, run::

    python manage.py encrypt_legacy_user_app_passwords
"""

from django.db import migrations
import api.security.encrypted_fields


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0010_encrypt_session_log_tokens"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="app_password",
            field=api.security.encrypted_fields.EncryptedCharField(
                blank=True, null=True, max_length=512,
            ),
        ),
    ]
