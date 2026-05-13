"""Populate ``organization_id`` on ``session_log`` and ``user_login_history``.

Phase 4 part 2 step 2 — after the columns are added but before RLS
is enabled, every existing row needs the tenant id set. We pull it
from the linked ``user.organization_id`` via a single UPDATE per
table.

Plain English
-------------

Old rows in ``session_log`` / ``user_login_history`` have a ``user_id``
but no ``organization_id`` yet (we just added the column). Each
user belongs to exactly one organization, so the right ``organization_id``
for a row is ``users.organization_id WHERE users.id = session_log.user_id``.

This command runs that UPDATE in batches so a multi-million-row
``user_login_history`` doesn't lock the table for hours.

Usage
-----

    python manage.py backfill_organization_id [--dry-run] [--batch 50000]
    python manage.py backfill_organization_id --table session_log
    python manage.py backfill_organization_id --table user_login_history

Idempotent — re-running only touches rows where ``organization_id IS NULL``.

What "done" looks like
----------------------

    SELECT count(*) FROM session_log WHERE organization_id IS NULL;
    -- 0

    SELECT count(*) FROM user_login_history WHERE organization_id IS NULL;
    -- 0

Only after BOTH are zero can RLS be enabled with ``FORCE ROW LEVEL
SECURITY`` on these tables.
"""

from __future__ import annotations

import logging
from typing import Any

from django.core.management.base import BaseCommand
from django.db import connection, transaction

logger = logging.getLogger(__name__)


_TARGETS = ("session_log", "user_login_history")


class Command(BaseCommand):
    help = (
        "Backfill organization_id on session_log and user_login_history "
        "from the linked user's org. Idempotent, batched."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--batch",
            type=int,
            default=50_000,
            help="Rows per UPDATE batch (default 50,000).",
        )
        parser.add_argument(
            "--table",
            choices=_TARGETS,
            default=None,
            help=f"Restrict to one table (default: all of {list(_TARGETS)}).",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        targets = (opts["table"],) if opts["table"] else _TARGETS
        for table in targets:
            self._backfill_one(table, opts["batch"], opts["dry_run"])

    def _backfill_one(self, table: str, batch_size: int, dry_run: bool) -> None:
        with connection.cursor() as cur:
            cur.execute(
                f"SELECT count(*) FROM public.{table} WHERE organization_id IS NULL"
            )
            remaining = cur.fetchone()[0]

        if remaining == 0:
            self.stdout.write(self.style.SUCCESS(
                f"[{table}] already backfilled (0 NULL rows)."
            ))
            return

        self.stdout.write(
            f"[{table}] {remaining} row(s) need backfilling "
            + ("(dry-run)" if dry_run else "")
        )
        if dry_run:
            return

        # Batch in chunks of `batch_size`. Each iteration does a
        # single bounded UPDATE — the limit clause uses an IN-subquery
        # so Postgres can use the index on `organization_id IS NULL`
        # rows for efficient batch selection.
        total_updated = 0
        while True:
            with transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute(
                        f"""
                        WITH batch AS (
                            SELECT t.id
                            FROM public.{table} t
                            WHERE t.organization_id IS NULL
                            LIMIT %s
                        )
                        UPDATE public.{table} AS t
                        SET organization_id = u.organization_id
                        FROM public.users u, batch
                        WHERE t.id = batch.id AND t.user_id = u.id
                        """,
                        [batch_size],
                    )
                    updated = cur.rowcount
            if updated == 0:
                break
            total_updated += updated
            self.stdout.write(f"[{table}] updated {total_updated}/{remaining}")

        # Final summary + leftover check (rows whose user_id was NULL
        # or where the user has no org — those won't have been
        # touched and need manual triage before NOT NULL can be
        # applied).
        with connection.cursor() as cur:
            cur.execute(
                f"SELECT count(*) FROM public.{table} WHERE organization_id IS NULL"
            )
            leftover = cur.fetchone()[0]

        if leftover == 0:
            self.stdout.write(self.style.SUCCESS(
                f"[{table}] done. All rows have organization_id."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"[{table}] {leftover} row(s) still NULL — likely orphan rows "
                f"(missing user, or user with no org). Triage before "
                f"enabling NOT NULL: "
                f"SELECT id, user_id FROM public.{table} "
                f"WHERE organization_id IS NULL LIMIT 10;"
            ))
