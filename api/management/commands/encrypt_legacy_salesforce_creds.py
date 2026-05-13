"""Backfill plaintext SalesforceSettings.password / client_secret → encrypted.

SalesforceSettings is a single-row admin table in the ``public``
schema (no per-tenant iteration needed). The backfill re-encrypts
plaintext values in one pass; idempotent.

Usage::

    python manage.py encrypt_legacy_salesforce_creds [--dry-run]
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction

from api.security.token_encryption import ENCRYPTED_PREFIX

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Encrypt any SalesforceSettings.password / client_secret rows still "
        "stored as plaintext. Idempotent."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: Any, **opts: Any) -> None:
        from sf_integration.models import SalesforceSettings

        dry_run = opts["dry_run"]
        # Either field still plaintext → re-save.
        qs = (
            SalesforceSettings.objects.exclude(password__startswith=ENCRYPTED_PREFIX)
            | SalesforceSettings.objects.exclude(client_secret__startswith=ENCRYPTED_PREFIX)
        ).distinct()
        count = qs.count()

        self.stdout.write(
            f"SalesforceSettings: {count} plaintext row(s) "
            + ("(dry-run)" if dry_run else "→ encrypting")
        )
        if dry_run or count == 0:
            return

        encrypted = 0
        for row in qs.iterator():
            with transaction.atomic():
                row.password = row.password
                row.client_secret = row.client_secret
                row.save(update_fields=["password", "client_secret"])
            encrypted += 1

        self.stdout.write(self.style.SUCCESS(
            f"Done. Encrypted {encrypted} SalesforceSettings rows."
        ))
