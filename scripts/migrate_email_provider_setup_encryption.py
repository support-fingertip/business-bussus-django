"""One-shot data migration: encrypt existing email_provider_setup.cred rows.

Run via:
    python manage.py shell -c \
      "exec(open('scripts/migrate_email_provider_setup_encryption.py').read())"

Idempotent: skips rows already prefixed with ``ENC1:``.

Operator checklist before running:
  1. Set ``OAUTH_TOKEN_ENC_KEY`` in the environment.
  2. Take a backup of email_provider_setup (``pg_dump -t email_provider_setup``).
  3. Run on staging first; verify token refresh still works for an account.
  4. Then run on production.
"""

import logging

from django.db import connection

from api.security.token_encryption import (
    encrypt_token,
    is_encrypted,
)

logger = logging.getLogger(__name__)


def _list_tenant_schemas():
    with connection.cursor() as cur:
        cur.execute(
            "SELECT database_schema FROM public.organizations WHERE is_active = TRUE"
        )
        return [r[0] for r in cur.fetchall()]


def _migrate_in_schema(schema: str) -> tuple[int, int, int]:
    """Returns (scanned, encrypted, skipped) counts for one schema."""
    encrypted = skipped = scanned = 0
    with connection.cursor() as cur:
        cur.execute("SET search_path TO %s", [schema])
        cur.execute(
            "SELECT id, cred FROM email_provider_setup WHERE cred IS NOT NULL"
        )
        rows = cur.fetchall()
        for row_id, cred in rows:
            scanned += 1
            if is_encrypted(cred):
                skipped += 1
                continue
            try:
                new_value = encrypt_token(cred)
            except Exception as exc:
                logger.error(
                    "schema=%s id=%s encrypt failed: %s", schema, row_id, exc
                )
                continue
            cur.execute(
                "UPDATE email_provider_setup "
                "SET cred = %s, updated_at = NOW() "
                "WHERE id = %s",
                [new_value, row_id],
            )
            encrypted += 1
    return scanned, encrypted, skipped


def main():
    totals = {"scanned": 0, "encrypted": 0, "skipped": 0}
    for schema in _list_tenant_schemas():
        scanned, encrypted, skipped = _migrate_in_schema(schema)
        totals["scanned"] += scanned
        totals["encrypted"] += encrypted
        totals["skipped"] += skipped
        print(
            f"schema={schema:<30s} "
            f"scanned={scanned:<5d} encrypted={encrypted:<5d} skipped={skipped:<5d}"
        )
    print(
        f"DONE  total_scanned={totals['scanned']} "
        f"encrypted={totals['encrypted']} skipped={totals['skipped']}"
    )


if __name__ == "__main__":
    main()
else:
    main()
