"""Backfill plaintext TelephonyConfig.authtoken / sid → encrypted at rest.

TelephonyConfig is per-tenant (lives in each org's schema). The
backfill iterates every active org, pins the connection to that
tenant's schema, and re-encrypts any rows whose ``authtoken`` or
``sid`` is still plaintext (no ``ENC1:`` prefix).

Usage::

    python manage.py encrypt_legacy_telephony_tokens [--dry-run] [--org <org_id>]

Behaviour
---------

  * Iterates ``public.organizations`` where ``is_active = TRUE``.
  * For each, opens a ``with_tenant_schema(org.database_schema)``
    block and re-saves the rows so ``EncryptedTextField.get_prep_value``
    runs the encrypt path.
  * Idempotent. Safe to re-run.
  * ``--dry-run`` counts candidates per tenant without modifying.
  * ``--org <id>`` restricts to a single org (useful for staged rollout).

Pre-condition
-------------

The per-tenant DDL in
``scripts/per_tenant_ddl/0011_widen_telephony_tokens.sql`` MUST have
been applied to every tenant schema first. Otherwise Fernet ciphertext
will silently truncate (varchar(512) is too narrow).

Safety
------

  * Encryption is reversible within the encryption-key lifetime.
  * Pre-rollout plaintext rows remain readable via the
    ``decrypt_token`` legacy passthrough, so background traffic
    continues working DURING the backfill.
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
        "Encrypt any TelephonyConfig.authtoken / sid rows that are still "
        "plaintext (no ENC1: prefix) across all active tenant schemas. "
        "Idempotent."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Count rows that need encryption but don't modify them.",
        )
        parser.add_argument(
            "--org",
            type=str,
            default=None,
            help="Restrict to a single org id (otherwise iterates all active orgs).",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        # Imported here so the module is import-safe in stripped envs.
        from api.models import Organization
        from api.security.tenant_context import with_tenant_schema
        from api.tenant_models.integration import TelephonyConfig

        dry_run: bool = opts["dry_run"]
        org_id: str | None = opts["org"]

        qs = Organization.objects.filter(is_active=True)
        if org_id:
            qs = qs.filter(id=org_id)

        total_encrypted = 0
        for org in qs.iterator():
            schema = org.database_schema
            if not schema:
                self.stdout.write(self.style.WARNING(
                    f"Skipping org {org.id}: no database_schema set."
                ))
                continue

            try:
                with with_tenant_schema(schema):
                    rows = TelephonyConfig.objects.exclude(
                        authtoken__startswith=ENCRYPTED_PREFIX,
                    ) | TelephonyConfig.objects.exclude(
                        sid__startswith=ENCRYPTED_PREFIX,
                    )
                    # Deduplicate (a row could match either branch).
                    rows = rows.distinct()
                    count = rows.count()

                    self.stdout.write(
                        f"[{schema}] {count} plaintext row(s) "
                        + ("(dry-run)" if dry_run else "→ encrypting")
                    )
                    if dry_run or count == 0:
                        continue

                    encrypted_here = 0
                    for row in rows.iterator(chunk_size=200):
                        with transaction.atomic():
                            # Re-assign to trigger get_prep_value's
                            # encrypt path. Idempotent on already-
                            # encrypted columns.
                            row.authtoken = row.authtoken
                            row.sid = row.sid
                            row.save(update_fields=["authtoken", "sid"])
                        encrypted_here += 1
                    total_encrypted += encrypted_here
                    self.stdout.write(self.style.SUCCESS(
                        f"[{schema}] encrypted {encrypted_here} rows"
                    ))
            except Exception as exc:
                logger.exception("encrypt_legacy_telephony_tokens failed for %s", schema)
                self.stdout.write(self.style.ERROR(
                    f"[{schema}] FAILED: {exc}. Continuing with next org."
                ))

        self.stdout.write(self.style.SUCCESS(
            f"Done. Total encrypted across all orgs: {total_encrypted}."
        ))
