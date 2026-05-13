"""Backfill plaintext OAuth tokens (Gmail / Outlook / Facebook) → encrypted.

Targets three tables, all per-tenant:

  * ``user_gmail_tokens.access_token`` / ``.refresh_token``
  * ``user_outlook_tokens.access_token`` / ``.refresh_token``
  * ``lead_capture.page_access_token`` (lives in ``public`` schema,
    rows scoped by ``organization_id``)

Iterates every active org, switches to that tenant's schema for the
per-tenant tables, and re-encrypts plaintext rows in batches.

Usage::

    python manage.py encrypt_legacy_oauth_tokens [--dry-run] [--org <id>]

Idempotent. Safe to re-run.
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
        "Encrypt plaintext OAuth tokens across all tenants. Targets "
        "user_gmail_tokens, user_outlook_tokens, lead_capture. Idempotent."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--org", type=str, default=None)

    def handle(self, *args: Any, **opts: Any) -> None:
        from api.models import Organization
        from api.security.tenant_context import with_tenant_schema
        from api.tenant_models.integration import (
            UserGmailToken,
            UserOutlookToken,
        )
        from api.tenant_models.shared import LeadCapture

        dry_run: bool = opts["dry_run"]
        org_id: str | None = opts["org"]

        orgs = Organization.objects.filter(is_active=True)
        if org_id:
            orgs = orgs.filter(id=org_id)

        total = 0

        # --- per-tenant tables --------------------------------------
        for org in orgs.iterator():
            schema = org.database_schema
            if not schema:
                continue
            try:
                with with_tenant_schema(schema):
                    total += self._reencrypt(
                        UserGmailToken,
                        ["access_token", "refresh_token"],
                        schema,
                        dry_run,
                    )
                    total += self._reencrypt(
                        UserOutlookToken,
                        ["access_token", "refresh_token"],
                        schema,
                        dry_run,
                    )
            except Exception as exc:
                logger.exception("encrypt_legacy_oauth_tokens: tenant %s", schema)
                self.stdout.write(self.style.ERROR(
                    f"[{schema}] failed: {exc}"
                ))

        # --- shared table (lead_capture) ----------------------------
        # Scoped by organization_id, not schema. We don't open
        # with_tenant_schema; iterate by org filter instead.
        for org in orgs.iterator():
            try:
                rows = LeadCapture.objects.filter(
                    organization_id=org.id,
                ).exclude(page_access_token__startswith=ENCRYPTED_PREFIX)
                count = rows.count()
                self.stdout.write(
                    f"[lead_capture/{org.id}] {count} plaintext "
                    + ("(dry-run)" if dry_run else "→ encrypting")
                )
                if dry_run or count == 0:
                    continue
                encrypted_here = 0
                for row in rows.iterator(chunk_size=200):
                    with transaction.atomic():
                        row.page_access_token = row.page_access_token
                        row.save(update_fields=["page_access_token"])
                    encrypted_here += 1
                total += encrypted_here
                self.stdout.write(self.style.SUCCESS(
                    f"[lead_capture/{org.id}] encrypted {encrypted_here}"
                ))
            except Exception as exc:
                logger.exception("encrypt_legacy_oauth_tokens: lead_capture %s", org.id)
                self.stdout.write(self.style.ERROR(
                    f"[lead_capture/{org.id}] failed: {exc}"
                ))

        self.stdout.write(self.style.SUCCESS(
            f"Done. Total rows re-encrypted: {total}."
        ))

    @staticmethod
    def _reencrypt(model, fields: list[str], label: str, dry_run: bool) -> int:
        """Re-encrypt plaintext rows for ``model`` across the listed fields.

        Returns the number of rows touched.
        """
        # Build a queryset of rows where ANY of the target fields is
        # still plaintext. Use exclude+chain (Q would be cleaner if
        # the model were registered).
        qs = model.objects.all()
        plain_q = model.objects.none()
        for f in fields:
            plain_q = plain_q | qs.exclude(**{f + "__startswith": ENCRYPTED_PREFIX})
        plain_q = plain_q.distinct()

        count = plain_q.count()
        if count == 0:
            return 0
        if dry_run:
            print(f"[{label}/{model.__name__}] {count} plaintext (dry-run)")
            return 0

        n = 0
        for row in plain_q.iterator(chunk_size=200):
            with transaction.atomic():
                for f in fields:
                    setattr(row, f, getattr(row, f))
                row.save(update_fields=fields)
            n += 1
        print(f"[{label}/{model.__name__}] encrypted {n}")
        return n
