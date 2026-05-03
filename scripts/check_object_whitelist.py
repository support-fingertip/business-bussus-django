"""Whitelist reconciliation tool — find tables that would 404.

The Phase 2.A.6 object-name whitelist (api/security/object_whitelist.py)
rejects any URL ``object_name`` capture that isn't either:

  - in the static ``RESERVED_ROUTES`` list (BL command names), or
  - in the per-tenant ``object`` registry (table ``object``).

If an in-house custom object exists in the tenant DB but isn't
registered, the dispatcher will return 404 once Phase 2.A.6 lands —
even though the table itself is fine.

This tool catches that pre-deploy. Run once per tenant before merging
the Phase 2.A.6 branch:

    python manage.py shell -c \
      "exec(open('scripts/check_object_whitelist.py').read())"

The script walks ``information_schema.tables`` for the tenant schema,
compares to (a) the registry and (b) RESERVED_ROUTES, and prints the
delta. Tables that are present-in-DB-but-not-allowed will 404; the
operator should add registry rows or expand RESERVED_ROUTES before
deploy.

Operator usage:
  - Set the tenant via env: ``TENANT_SCHEMA=tenant_alpha``
  - Or pass on the command line: ``python ... -- tenant_alpha``
"""

from __future__ import annotations

import os
import sys
from typing import Iterable

from django.db import connection

# Late import so the script works under `manage.py shell -c exec(...)`.
def _allowed_names(schema: str) -> set[str]:
    """Names the dispatcher would accept for this tenant."""
    from api.security.object_whitelist import RESERVED_ROUTES
    from api.ORM.dynamic.metadata_loader import list_business_objects

    allowed = set(RESERVED_ROUTES)
    try:
        allowed |= set(list_business_objects(schema))
    except Exception as exc:
        print(f"  ⚠️ list_business_objects({schema}) raised: {exc}", file=sys.stderr)
        # Fall back to reading the object table directly.
        with connection.cursor() as cur:
            cur.execute("SET search_path TO %s, public", [schema])
            cur.execute("SELECT name FROM object")
            allowed |= {r[0] for r in cur.fetchall()}
    return allowed


def _real_tables(schema: str) -> set[str]:
    """All non-system tables physically present in the tenant schema."""
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type = 'BASE TABLE'
            """,
            [schema],
        )
        return {r[0] for r in cur.fetchall()}


def _registry_names(schema: str) -> set[str]:
    """Distinct names in the tenant's ``object`` table."""
    with connection.cursor() as cur:
        cur.execute("SET search_path TO %s, public", [schema])
        cur.execute("SELECT name FROM object")
        return {r[0] for r in cur.fetchall()}


# Django-managed tables that legitimately exist in tenant schemas but
# aren't dispatcher routes — never expected on the whitelist.
DJANGO_FRAMEWORK_TABLES = {
    "django_admin_log", "django_content_type", "django_migrations",
    "django_session",
    "django_celery_beat_clockedschedule",
    "django_celery_beat_crontabschedule",
    "django_celery_beat_intervalschedule",
    "django_celery_beat_periodictask",
    "django_celery_beat_periodictasks",
    "django_celery_beat_solarschedule",
    "auth_group", "auth_group_permissions", "auth_permission",
    "users_user_permissions",
}


def report(schema: str) -> int:
    """Print the reconciliation report. Returns exit code (0 = OK)."""
    print(f"\n=== Whitelist reconciliation for schema={schema!r} ===\n")
    real = _real_tables(schema)
    allowed = _allowed_names(schema)
    registry = _registry_names(schema)

    real_excl_framework = real - DJANGO_FRAMEWORK_TABLES

    would_404 = sorted(real_excl_framework - allowed)
    in_registry_no_table = sorted(registry - real)
    in_real_no_registry = sorted(real_excl_framework - registry)

    print(f"Real tables (excluding Django framework): {len(real_excl_framework)}")
    print(f"Allowed names (RESERVED_ROUTES + object registry): {len(allowed)}")
    print(f"Registry rows: {len(registry)}")
    print()

    print(f"❌ Tables that EXIST but would 404 ({len(would_404)}):")
    for t in would_404:
        print(f"    {t}")
    print()

    print(f"⚠️ Registry rows with no matching real table ({len(in_registry_no_table)}):")
    for t in in_registry_no_table:
        print(f"    {t}")
    print()

    print(f"⚠️ Real tables with no registry row ({len(in_real_no_registry)}):")
    for t in in_real_no_registry:
        print(f"    {t}")
    print()

    if would_404:
        print(
            "ACTION: register the would-404 tables in `object` (setup=TRUE for "
            "metadata, setup=FALSE for business objects), or add their names to "
            "`api/security/object_whitelist.RESERVED_ROUTES` if they're BL "
            "command names rather than real tables."
        )
        return 1

    print("✅ Every real table is on the whitelist or in the registry.")
    return 0


def _pick_schema() -> str:
    if "--" in sys.argv:
        idx = sys.argv.index("--")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]
    if os.getenv("TENANT_SCHEMA"):
        return os.environ["TENANT_SCHEMA"]
    print("Pass tenant via --schema=NAME or env var TENANT_SCHEMA", file=sys.stderr)
    sys.exit(2)


def main():
    schema = _pick_schema()
    rc = report(schema)
    sys.exit(rc)


if __name__ == "__main__":
    main()
else:
    # When invoked via `manage.py shell -c exec(open(...).read())` the
    # __name__ is '__main__' from the shell's perspective, so this
    # branch handles the alternate entry point.
    try:
        schema = _pick_schema()
        report(schema)
    except SystemExit:
        pass
