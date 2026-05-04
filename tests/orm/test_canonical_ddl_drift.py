"""Phase 4.A — canonical DDL ↔ Django model drift tests.

Pure unit tests (no DB). Parses ``default_tables.sql``, ``tables.sql``,
and ``sqlfiles/shared_tables.sql`` for ``CREATE TABLE`` blocks, then
checks that every table modeled by Django has:

  1. A canonical CREATE TABLE block in one of the source-controlled
     DDL files (catches "model added without DDL").
  2. A column for every Django model field that has a ``column``
     attribute (catches "model adds a column the canonical DDL is
     missing").

These are structural checks — they don't try to validate exact types.
That heavier check happens via ``scripts/ddl_introspection.py
compare`` against a real database.

Why two tests instead of one
----------------------------
Test 1 fails LOUDLY when a new model lands without DDL — common when
Phase X adds a model but the DDL block was forgotten.

Test 2 fails when a model field name doesn't match any column in the
canonical DDL — common when a column gets renamed in the model but
not in the SQL file (or vice-versa).
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest


pytestmark = pytest.mark.unit


REPO_ROOT = Path(__file__).resolve().parents[2]

DDL_FILES = [
    REPO_ROOT / "default_tables.sql",
    REPO_ROOT / "tables.sql",
    REPO_ROOT / "sqlfiles" / "shared_tables.sql",
]


# Catches:
#   CREATE TABLE foo (...)
#   CREATE TABLE IF NOT EXISTS foo (...)
#   CREATE TABLE "foo" (...)        — case-table is quoted
# Does NOT match commented-out blocks (we discard `--` lines first).
_CREATE_RE = re.compile(
    r"""
    \bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?
    "?([A-Za-z_][A-Za-z0-9_]*)"?
    \s*\(
    (.*?)        # body — captured for column extraction
    \)\s*;
    """,
    re.IGNORECASE | re.DOTALL | re.VERBOSE,
)


def _strip_sql_comments(text: str) -> str:
    """Drop -- line comments so we don't match commented-out CREATE TABLEs."""
    return "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("--")
    )


def _all_canonical_tables() -> dict[str, str]:
    """Return ``{table_name: column_block_text}`` from every DDL file."""
    out: dict[str, str] = {}
    for path in DDL_FILES:
        if not path.exists():
            continue
        text = _strip_sql_comments(path.read_text(encoding="utf-8"))
        for match in _CREATE_RE.finditer(text):
            name = match.group(1).lower()
            body = match.group(2)
            out[name] = body
    return out


def _column_names_from_block(body: str) -> set[str]:
    """Extract column names from a CREATE TABLE body.

    Heuristic: each comma-delimited stanza begins with the column
    name (or a constraint keyword). We strip the constraint keywords
    and take the first identifier as the column name.
    """
    names: set[str] = set()
    # Split on top-level commas. Naive but adequate — our DDL doesn't
    # use parenthesized expression defaults that span commas at the
    # top level (the only nested parens are in CONCAT(), gen_random_uuid(),
    # NUMERIC(15,2) etc., which we skip by tracking depth).
    depth = 0
    buf = []
    parts = []
    for ch in body:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf).strip())

    constraint_kw = re.compile(
        r"^(constraint|primary\s+key|foreign\s+key|unique|check|exclude)\b",
        re.IGNORECASE,
    )
    ident_re = re.compile(r'^"?([A-Za-z_][A-Za-z0-9_]*)"?')
    for part in parts:
        if not part:
            continue
        if constraint_kw.match(part):
            continue
        m = ident_re.match(part)
        if m:
            names.add(m.group(1).lower())
    return names


def _ensure_django():
    pytest.importorskip("django")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    try:
        import django
        django.setup()
    except Exception:
        pytest.skip("Django not configured in this environment")


def test_every_modeled_table_has_canonical_ddl():
    """Every Django-modeled table has a CREATE TABLE somewhere in
    source control. Catches "model added without DDL"."""
    _ensure_django()
    from api import tenant_models as tm

    canonical = _all_canonical_tables()
    missing = []
    for name in tm.__all__:
        model = getattr(tm, name)
        table = model._meta.db_table.lower()
        if table not in canonical:
            missing.append((name, table))

    assert not missing, (
        "Django models without canonical DDL in default_tables.sql, "
        "tables.sql, or sqlfiles/shared_tables.sql:\n  "
        + "\n  ".join(f"{cls} ({tbl})" for cls, tbl in missing)
    )


def test_every_model_field_has_a_canonical_column():
    """Every concrete model field maps to a column in the canonical
    DDL. Catches "model adds a column that DDL doesn't have"."""
    _ensure_django()
    from api import tenant_models as tm

    canonical = _all_canonical_tables()
    drift: list[str] = []

    for name in tm.__all__:
        model = getattr(tm, name)
        table = model._meta.db_table.lower()
        block = canonical.get(table)
        if block is None:
            continue  # caught by the other test
        ddl_cols = _column_names_from_block(block)

        for field in model._meta.get_fields():
            col = getattr(field, "column", None)
            if not col:
                continue  # reverse relation / many-to-many
            if col.lower() not in ddl_cols:
                drift.append(
                    f"  {name}.{field.name} -> column '{col}' "
                    f"missing from canonical DDL of '{table}'"
                )

    assert not drift, (
        "Model fields with no matching canonical-DDL column "
        "(rename in model but not in SQL?):\n" + "\n".join(drift)
    )


def test_canonical_ddl_files_exist_and_are_non_empty():
    """Sanity — the parser inputs are present."""
    for path in DDL_FILES:
        assert path.exists(), f"Canonical DDL file missing: {path}"
        assert path.stat().st_size > 0, f"Canonical DDL file empty: {path}"
