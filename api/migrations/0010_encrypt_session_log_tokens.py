"""Migration — Phase 3.1: SessionLog token columns encrypted at rest.

This migration changes the FIELD TYPE for ``session_log.access_token``
and ``session_log.refresh_token`` from ``CharField(500)`` to
``EncryptedCharField(1024)``.

DB-level effect
---------------

The column type stays ``varchar`` in Postgres; only the ``max_length``
grows (500 → 1024), which Postgres handles without a table rewrite.
Existing plaintext rows continue to work because
``api.security.token_encryption.decrypt_token`` returns plaintext
unchanged when the ``ENC1:`` prefix is absent.

App-level effect
----------------

Once this migration is applied:
  * NEW writes (via ``SessionLog.objects.create(...)``) are encrypted.
  * Reads decrypt transparently.
  * EXISTING rows remain plaintext until the backfill command runs;
    see ``python manage.py encrypt_legacy_session_tokens`` (added in
    api/management/commands/encrypt_legacy_session_tokens.py).

Rollback safety
---------------

Reverting this migration drops back to ``CharField(500)``. Already-
encrypted rows (``ENC1:...``) are TRUNCATED if they exceed 500 chars
— most don't, but a long refresh token plus Fernet overhead can.
Before reverting in production, run::

    UPDATE session_log
    SET access_token = NULL, refresh_token = NULL
    WHERE access_token LIKE 'ENC1:%' AND length(access_token) > 500;

…and force users to re-login. Logout-and-login is cheap; data loss
isn't.
"""

from django.db import migrations
import api.security.encrypted_fields


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0009_phase4a_lead_capture"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sessionlog",
            name="access_token",
            field=api.security.encrypted_fields.EncryptedCharField(max_length=1024),
        ),
        migrations.AlterField(
            model_name="sessionlog",
            name="refresh_token",
            field=api.security.encrypted_fields.EncryptedCharField(max_length=1024),
        ),
    ]
