"""Verify migration 0005 emits no DDL.

Phase 2 ORM Wave 2's ``0005_phase2_tenant_models`` registers tenant-
scoped models in Django's state graph but uses
``SeparateDatabaseAndState`` with empty ``database_operations`` —
applying the migration must run zero SQL against the actual database.

This script asserts that contract by invoking ``manage.py sqlmigrate``
and checking the output. Wire into CI to catch a future change that
accidentally flips ``managed = True`` or adds a ``database_operations``
list.

Usage:
    python scripts/verify_managed_false_migration.py
    # or, in CI:
    DJANGO_SETTINGS_MODULE=version2.settings \\
        python scripts/verify_managed_false_migration.py

Exit code:
    0 — migration emits a no-op (header lines only)
    1 — migration would emit DDL
    2 — script could not run (e.g. Django not installed)
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Lines in ``manage.py sqlmigrate`` output that are headers / no-ops,
# not actual DDL. Anything else means we've got SQL we shouldn't.
NOOP_LINE_RE = re.compile(
    r"""^(
        \s* $                                          # blank
      | --.*$                                          # SQL comment
      | BEGIN \s* ; \s* $                              # transaction wrappers
      | COMMIT \s* ; \s* $
    )""",
    re.IGNORECASE | re.VERBOSE,
)


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    manage_py = ROOT / "manage.py"
    if not manage_py.exists():
        print("manage.py not found at repo root", file=sys.stderr)
        return 2

    try:
        proc = subprocess.run(
            [
                sys.executable, str(manage_py),
                "sqlmigrate", "api", "0005_phase2_tenant_models",
            ],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=60,
        )
    except FileNotFoundError as exc:
        print(f"Could not run manage.py: {exc}", file=sys.stderr)
        return 2

    if proc.returncode != 0:
        print("`manage.py sqlmigrate` failed:", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        return 2

    output = proc.stdout
    print("=== sqlmigrate api 0005_phase2_tenant_models ===")
    print(output)

    ddl_lines = [
        line for line in output.splitlines()
        if not NOOP_LINE_RE.match(line)
    ]
    if ddl_lines:
        print(
            f"❌ Expected zero DDL lines but found {len(ddl_lines)}:",
            file=sys.stderr,
        )
        for line in ddl_lines:
            print(f"    {line!r}", file=sys.stderr)
        print(
            "\nMigration 0005 should be state-only (managed=False + "
            "SeparateDatabaseAndState with empty database_operations). "
            "If you intentionally added DDL, update this script.",
            file=sys.stderr,
        )
        return 1

    print("✅ Migration 0005 is state-only — no DDL would run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
