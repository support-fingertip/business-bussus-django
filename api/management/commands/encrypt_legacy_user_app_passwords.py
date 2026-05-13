"""Backfill plaintext ``users.app_password`` rows → encrypted at rest.

The ``users`` table lives in the ``public`` schema and is shared
across tenants (per-user SMTP credentials). One pass over all rows
where ``app_password`` is non-null and doesn't start with ``ENC1:``.

Usage::

    python manage.py encrypt_legacy_user_app_passwords [--dry-run]
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
        "Encrypt any User.app_password rows still stored as plaintext "
        "(no ENC1: prefix). Idempotent."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--batch", type=int, default=500,
            help="Rows per save batch (default 500)."
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        from api.models import User

        dry_run = opts["dry_run"]
        batch_size = opts["batch"]

        qs = User.objects.exclude(
            app_password__isnull=True,
        ).exclude(
            app_password__startswith=ENCRYPTED_PREFIX,
        ).exclude(
            app_password__exact="",
        )
        count = qs.count()

        self.stdout.write(
            f"Users with plaintext app_password: {count} "
            + ("(dry-run)" if dry_run else "→ encrypting")
        )
        if dry_run or count == 0:
            return

        encrypted = 0
        for user in qs.iterator(chunk_size=batch_size):
            with transaction.atomic():
                user.app_password = user.app_password
                user.save(update_fields=["app_password"])
            encrypted += 1
            if encrypted % 100 == 0:
                self.stdout.write(f"  {encrypted}/{count}...")

        self.stdout.write(self.style.SUCCESS(
            f"Done. Encrypted {encrypted} User.app_password rows."
        ))
