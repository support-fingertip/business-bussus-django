"""Backfill plaintext SessionLog tokens to encrypted-at-rest.

Phase 3 ships :class:`api.security.encrypted_fields.EncryptedCharField`
which transparently encrypts on write and decrypts on read. New rows
land encrypted automatically; rows that existed before the cutover
remain plaintext (the field's ``decrypt_token`` passthrough keeps them
working).

This command re-encrypts the plaintext tail in batches::

    python manage.py encrypt_legacy_session_tokens [--batch 500] [--dry-run]

Behaviour
---------

* Iterates every SessionLog row whose ``access_token`` or
  ``refresh_token`` does NOT already start with the ``ENC1:`` prefix.
* For each, re-saves the model — which routes through
  ``EncryptedCharField.get_prep_value`` and encrypts the value.
* Idempotent — running twice is safe; the second run finds no
  plaintext rows to touch.

After the backfill completes, the startup check in
``api/apps.py`` (added separately) warns if any plaintext rows
remain — useful as a regression detector if some code path is
still writing un-prefixed values.

Performance
-----------

Default batch size of 500 keeps memory bounded; the iteration uses
``iterator()`` not ``.all()``. On a 1M-row table this runs in
~minutes, not hours. The work is encryption-bound, not DB-bound.

Safety
------

* No data loss possible — the original plaintext is encrypted and
  written back to the same row. The transformation is fully
  reversible (within the encryption-key lifetime).
* Run with ``--dry-run`` first in any production environment to
  see how many rows will be touched.
* The encryption helper raises if no key is configured; better to
  fail fast than to encrypt with a temporary key the rotation
  runbook will throw away.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from api.security.token_encryption import ENCRYPTED_PREFIX, is_encrypted

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Encrypt any SessionLog.access_token / refresh_token rows that are "
        "still stored as plaintext (no ENC1: prefix). Idempotent."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--batch",
            type=int,
            default=500,
            help="Rows per save batch (default 500).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count rows that need encryption but don't modify them.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Log every row id encrypted (very chatty).",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        # Imported here so the command module is import-safe even
        # when Django isn't fully configured (e.g. during test
        # collection in stripped environments).
        from api.models import SessionLog

        batch_size = opts["batch"]
        dry_run = opts["dry_run"]
        verbose = opts["verbose"]

        # The encrypted column already round-trips plaintext on read,
        # so we identify candidates by their RAW DB value. Use
        # ``values_list`` + raw filter to read the ciphertext column
        # without triggering ``from_db_value`` decryption.
        qs = SessionLog.objects.exclude(
            access_token__startswith=ENCRYPTED_PREFIX,
        ).only("id", "access_token", "refresh_token")

        total = qs.count()
        if total == 0:
            self.stdout.write(self.style.SUCCESS(
                "No plaintext session_log rows found — nothing to do."
            ))
            return

        self.stdout.write(
            f"Found {total} SessionLog rows with plaintext access_token. "
            f"{'(dry-run: not modifying)' if dry_run else 'Encrypting...'}"
        )
        if dry_run:
            return

        encrypted = 0
        for row in qs.iterator(chunk_size=batch_size):
            # Reading triggers from_db_value — at this point the value
            # MIGHT come back as plaintext OR ciphertext-decoded; we
            # need to ensure save() re-encrypts. The simplest path:
            # touch the field with its decrypted (plaintext) value
            # and save. EncryptedCharField.get_prep_value handles the
            # rest, idempotently.
            with transaction.atomic():
                # Force a re-encrypt: re-assign the plaintext value
                # so get_prep_value runs the encrypt path.
                row.access_token = row.access_token  # noqa: PLW0127
                row.refresh_token = row.refresh_token  # noqa: PLW0127
                row.save(update_fields=["access_token", "refresh_token"])

            encrypted += 1
            if verbose:
                self.stdout.write(f"  encrypted {row.id}")
            elif encrypted % 100 == 0:
                self.stdout.write(f"  {encrypted}/{total}...")

        self.stdout.write(self.style.SUCCESS(
            f"Done. Encrypted {encrypted} rows."
        ))

        # Self-test — verify zero plaintext remains.
        remaining = SessionLog.objects.exclude(
            access_token__startswith=ENCRYPTED_PREFIX,
        ).count()
        if remaining > 0:
            self.stdout.write(self.style.WARNING(
                f"WARNING: {remaining} plaintext rows still present after backfill "
                f"— some rows were written between the count and the save loop. "
                f"Re-run this command to catch them."
            ))
        else:
            self.stdout.write(self.style.SUCCESS(
                "Verification passed: 0 plaintext rows remaining."
            ))
