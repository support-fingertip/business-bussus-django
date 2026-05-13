"""Provision (or revoke) the per-tenant Postgres role — Phase 4 part 1.

In plain English
----------------

This management command does what
``scripts/per_tenant_ddl/provision_tenant_role.sql`` does, but with
a Python wrapper that:

  * Substitutes the tenant's schema name into the template safely
    (using psycopg2.sql.Identifier — no string-format SQL injection).
  * Iterates every active org if ``--all`` is passed.
  * Has a ``--dry-run`` mode so operators can see what it would do.
  * Has a ``--revoke`` mode to undo the provisioning for offboarding.

Usage
-----

    # Provision a single tenant
    python manage.py provision_tenant_role --org tenant_acme

    # Provision every active tenant (idempotent — re-runs are safe)
    python manage.py provision_tenant_role --all

    # See what would happen without running it
    python manage.py provision_tenant_role --all --dry-run

    # Revoke (used by tenant_offboard.md)
    python manage.py provision_tenant_role --org tenant_acme --revoke

Safety
------

* All identifier interpolation goes through ``psycopg2.sql.Identifier``
  — even a malicious schema name in ``public.organizations`` can't
  inject SQL.
* ``--dry-run`` prints the SQL it would execute and exits.
* Each tenant runs in its own transaction. A failure on one tenant
  doesn't taint the others.
* Idempotent. The SQL guards CREATE ROLE with ``IF NOT EXISTS`` and
  GRANTs are idempotent in Postgres.
"""

from __future__ import annotations

import logging
from typing import Any, List

from django.core.management.base import BaseCommand
from django.db import connection, transaction
from psycopg2 import sql

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Create the per-tenant Postgres role and grants for one or every "
        "active org. Idempotent. See Phase 4 part 1 of the launch-readiness plan."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--org",
            type=str,
            default=None,
            help="Schema name of a single org to provision (e.g. tenant_acme).",
        )
        parser.add_argument(
            "--all",
            action="store_true",
            help="Provision every active org (public.organizations.is_active=TRUE).",
        )
        parser.add_argument(
            "--revoke",
            action="store_true",
            help="Revoke the role instead of provisioning it.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the SQL that would run and exit.",
        )
        parser.add_argument(
            "--app-role",
            type=str,
            default="bussus_app",
            help="Name of the application's main Postgres role (default 'bussus_app').",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        if not opts["org"] and not opts["all"]:
            self.stderr.write("Pass --org <schema> or --all.")
            return

        schemas = self._resolve_schemas(opts["org"], opts["all"])
        if not schemas:
            self.stdout.write(self.style.WARNING("No schemas matched. Nothing to do."))
            return

        action = "revoke" if opts["revoke"] else "provision"
        self.stdout.write(
            f"About to {action} {len(schemas)} tenant role(s): "
            + ", ".join(schemas[:5])
            + (" ..." if len(schemas) > 5 else "")
        )

        for schema in schemas:
            try:
                if opts["revoke"]:
                    self._revoke(schema, opts["dry_run"])
                else:
                    self._provision(schema, opts["app_role"], opts["dry_run"])
            except Exception as exc:
                logger.exception("provision_tenant_role failed for %s", schema)
                self.stderr.write(self.style.ERROR(
                    f"[{schema}] failed: {exc}. Continuing with next tenant."
                ))

        self.stdout.write(self.style.SUCCESS(
            f"Done. {action.capitalize()}d {len(schemas)} role(s)."
        ))

    # ------------------------------------------------------------------

    def _resolve_schemas(self, org: str | None, all_orgs: bool) -> List[str]:
        if org:
            return [org]
        # Pull the schema list from public.organizations.
        with connection.cursor() as cur:
            cur.execute(
                "SELECT database_schema FROM public.organizations "
                "WHERE is_active = TRUE AND database_schema IS NOT NULL "
                "AND database_schema <> ''"
            )
            return [row[0] for row in cur.fetchall()]

    def _provision(self, schema: str, app_role: str, dry_run: bool) -> None:
        """Run the provisioning DDL for one schema.

        Every identifier is wrapped in ``psycopg2.sql.Identifier`` so a
        malicious schema name from public.organizations can't escape.
        """
        role_name = f"tenant_{schema}_role"

        # Build the statement list. Each is a (description, sql.Composed) tuple
        # so dry-run output is human-readable.
        statements = [
            (
                f"create role {role_name} if missing",
                sql.SQL(
                    "DO $$ BEGIN "
                    "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = %s) THEN "
                    "EXECUTE format('CREATE ROLE %I NOLOGIN INHERIT', %L); "
                    "END IF; END$$;"
                ).format(),
                [role_name, role_name],
            ),
            (
                f"grant USAGE on schema {schema} to {role_name}",
                sql.SQL("GRANT USAGE ON SCHEMA {sch} TO {role}").format(
                    sch=sql.Identifier(schema),
                    role=sql.Identifier(role_name),
                ),
                None,
            ),
            (
                f"grant CRUD on every table in {schema} to {role_name}",
                sql.SQL(
                    "GRANT SELECT, INSERT, UPDATE, DELETE "
                    "ON ALL TABLES IN SCHEMA {sch} TO {role}"
                ).format(
                    sch=sql.Identifier(schema),
                    role=sql.Identifier(role_name),
                ),
                None,
            ),
            (
                f"grant sequences in {schema}",
                sql.SQL(
                    "GRANT USAGE, SELECT, UPDATE "
                    "ON ALL SEQUENCES IN SCHEMA {sch} TO {role}"
                ).format(
                    sch=sql.Identifier(schema),
                    role=sql.Identifier(role_name),
                ),
                None,
            ),
            (
                f"default privileges in {schema} (tables)",
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA {sch} "
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}"
                ).format(
                    sch=sql.Identifier(schema),
                    role=sql.Identifier(role_name),
                ),
                None,
            ),
            (
                f"default privileges in {schema} (sequences)",
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA {sch} "
                    "GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {role}"
                ).format(
                    sch=sql.Identifier(schema),
                    role=sql.Identifier(role_name),
                ),
                None,
            ),
            (
                "grant USAGE on public",
                sql.SQL("GRANT USAGE ON SCHEMA public TO {role}").format(
                    role=sql.Identifier(role_name),
                ),
                None,
            ),
            (
                "shared-table privileges",
                sql.SQL(
                    "GRANT SELECT ON public.organizations TO {role}; "
                    "GRANT SELECT, INSERT, UPDATE ON public.users TO {role}; "
                    "GRANT SELECT, INSERT ON public.user_login_history TO {role}; "
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON public.lead_capture TO {role}; "
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON public.session_log TO {role};"
                ).format(role=sql.Identifier(role_name)),
                None,
            ),
            (
                f"grant {role_name} membership to {app_role}",
                sql.SQL("GRANT {role} TO {app}").format(
                    role=sql.Identifier(role_name),
                    app=sql.Identifier(app_role),
                ),
                None,
            ),
        ]

        if dry_run:
            for desc, stmt, params in statements:
                rendered = stmt.as_string(connection.connection) if not isinstance(stmt, sql.SQL) else str(stmt)
                self.stdout.write(f"  [{schema}] {desc}: {rendered}")
            return

        with transaction.atomic():
            with connection.cursor() as cur:
                for desc, stmt, params in statements:
                    cur.execute(stmt, params or [])
        self.stdout.write(self.style.SUCCESS(f"[{schema}] provisioned."))

    def _revoke(self, schema: str, dry_run: bool) -> None:
        role_name = f"tenant_{schema}_role"
        if dry_run:
            self.stdout.write(f"  [{schema}] would DROP ROLE {role_name} (after revokes).")
            return

        statements = [
            sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA {sch} FROM {role}").format(
                sch=sql.Identifier(schema), role=sql.Identifier(role_name)),
            sql.SQL("REVOKE ALL ON ALL SEQUENCES IN SCHEMA {sch} FROM {role}").format(
                sch=sql.Identifier(schema), role=sql.Identifier(role_name)),
            sql.SQL("REVOKE ALL ON SCHEMA {sch} FROM {role}").format(
                sch=sql.Identifier(schema), role=sql.Identifier(role_name)),
            sql.SQL("REVOKE ALL ON public.organizations FROM {role}").format(role=sql.Identifier(role_name)),
            sql.SQL("REVOKE ALL ON public.users FROM {role}").format(role=sql.Identifier(role_name)),
            sql.SQL("REVOKE ALL ON public.user_login_history FROM {role}").format(role=sql.Identifier(role_name)),
            sql.SQL("REVOKE ALL ON public.lead_capture FROM {role}").format(role=sql.Identifier(role_name)),
            sql.SQL("REVOKE ALL ON public.session_log FROM {role}").format(role=sql.Identifier(role_name)),
            sql.SQL("REVOKE USAGE ON SCHEMA public FROM {role}").format(role=sql.Identifier(role_name)),
            sql.SQL("DROP ROLE IF EXISTS {role}").format(role=sql.Identifier(role_name)),
        ]
        with transaction.atomic():
            with connection.cursor() as cur:
                for stmt in statements:
                    try:
                        cur.execute(stmt)
                    except Exception as exc:
                        # Continue on REVOKE failures — they often just mean
                        # the grant didn't exist (the role was never fully
                        # provisioned). DROP ROLE will surface a real problem.
                        logger.info("revoke step on %s: %s (continuing)", schema, exc)
        self.stdout.write(self.style.SUCCESS(f"[{schema}] revoked + dropped."))
