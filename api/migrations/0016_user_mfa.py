"""Phase C9 — UserMFA table for multi-factor authentication.

Creates ``user_mfa``: one row per user who has started or completed
MFA enrollment. Holds the encrypted TOTP secret, the enabled flag,
and the hashed one-time recovery codes.

This is a Django-managed table in the ``public`` schema (MFA is a
platform-level concern, keyed to ``public.users``).
"""

from django.db import migrations, models
import django.db.models.deletion
import api.security.encrypted_fields


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0015_enable_rls_shared_tables"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserMFA",
            fields=[
                ("id", models.BigAutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name="ID",
                )),
                ("secret", api.security.encrypted_fields.EncryptedCharField(
                    max_length=512,
                )),
                ("enabled", models.BooleanField(default=False)),
                ("recovery_codes", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("confirmed_at", models.DateTimeField(blank=True, null=True)),
                ("last_used_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.OneToOneField(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="mfa",
                    db_column="user_id",
                    to="api.user",
                )),
            ],
            options={
                "db_table": "user_mfa",
                "verbose_name": "User MFA",
                "verbose_name_plural": "User MFA",
            },
        ),
    ]
