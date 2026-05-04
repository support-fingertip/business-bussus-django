"""Phase 4.A — per-tenant DDL introspection / drift detection.

Operator tool. Walks every tenant schema (or one specified schema)
and reads ``information_schema.columns`` for each Django-modeled
table. Compares the live shape against the canonical Django model
field definitions and reports drift.

Why this matters
----------------
The platform's tenant tables are unmanaged by Django (managed=False)
and provisioned by raw SQL files (default_tables.sql, tables.sql,
sqlfiles/shared_tables.sql). Across deployments, columns can drift
silently — a manual ALTER on one tenant, an old migration on another,
a new column added to the canonical file but not back-applied.

Phase 3.B added 13 models without verifying live tenant shapes
matched the model field types. This script is the catch-up audit.

Usage
-----

    # Dump one tenant's columns for all modeled tables
    python scripts/ddl_introspection.py dump --schema tenant_alpha

    # Dump all tenants
    python scripts/ddl_introspection.py dump

    # Compare one tenant against the canonical Django model types
    python scripts/ddl_introspection.py compare --schema tenant_alpha

    # Find the consensus shape across all tenants per table
    python scripts/ddl_introspection.py consensus

Exit codes
----------
    0 — no drift found (or dump completed)
    1 — drift detected
    2 — script could not run (DB connection failure, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from typing import Iterable


def _setup_django():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "version2.settings")
    import django
    django.setup()


def _modeled_table_inventory():
    """Return ``{table_name: ModelClass}`` for every modeled table.

    Includes per-tenant tables (managed=False under api.tenant_models)
    plus the shared/public tables added in Phase 4.A.
    """
    from api import tenant_models as tm

    inventory = {}
    for name in tm.__all__:
        model = getattr(tm, name)
        meta = model._meta
        inventory[meta.db_table] = model
    return inventory


def _list_tenant_schemas(connection) -> list[str]:
    """Return every tenant schema name from the public.organizations table."""
    with connection.cursor() as cur:
        cur.execute(
            "SELECT database_schema FROM public.organizations "
            "WHERE database_schema IS NOT NULL "
            "ORDER BY database_schema"
        )
        return [row[0] for row in cur.fetchall()]


def _dump_columns(connection, schema: str, tables: Iterable[str]) -> dict:
    """Return ``{table: [{column, data_type, is_nullable, default}, ...]}``.

    Tables not present in the schema are omitted from the result.
    """
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT table_name, column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = ANY(%s)
            ORDER BY table_name, ordinal_position
            """,
            [schema, list(tables)],
        )
        rows = cur.fetchall()

    out: dict[str, list[dict]] = defaultdict(list)
    for table, column, data_type, is_nullable, default in rows:
        out[table].append({
            "column": column,
            "data_type": data_type,
            "is_nullable": is_nullable == "YES",
            "default": default,
        })
    return dict(out)


# Mapping from Django field internal type to a set of acceptable Postgres
# data_type strings. Loose by design — any miss here surfaces as a
# spurious "drift" the operator can either accept or fix in this map.
_DJANGO_TO_PG_TYPE = {
    "CharField":            {"character varying", "text"},
    "TextField":            {"text", "character varying"},
    "IntegerField":         {"integer", "bigint", "smallint"},
    "BigIntegerField":      {"bigint"},
    "BooleanField":         {"boolean"},
    "DateField":            {"date"},
    "DateTimeField":        {"timestamp without time zone",
                             "timestamp with time zone"},
    "JSONField":            {"jsonb", "json"},
    "ForeignKey":           {"character varying", "uuid", "integer", "bigint"},
    "AutoField":            {"integer", "bigint"},
    "BigAutoField":         {"bigint"},
}


def _compare_schema(connection, schema: str) -> tuple[int, list[str]]:
    """Compare live columns in ``schema`` against canonical Django model types.

    Returns ``(drift_count, list_of_drift_lines)``.
    """
    inventory = _modeled_table_inventory()
    live = _dump_columns(connection, schema, inventory.keys())

    drift_lines: list[str] = []
    drift_count = 0

    for table, model in sorted(inventory.items()):
        live_cols = {c["column"]: c for c in live.get(table, [])}
        if not live_cols:
            drift_lines.append(f"  [missing] {schema}.{table} — table not present in this tenant")
            drift_count += 1
            continue

        for field in model._meta.get_fields():
            # Skip reverse relations / many-to-many — they don't map to columns
            if not getattr(field, "column", None):
                continue
            col = field.column
            internal = field.get_internal_type()
            expected = _DJANGO_TO_PG_TYPE.get(internal, set())

            live_col = live_cols.get(col)
            if live_col is None:
                drift_lines.append(
                    f"  [missing column] {schema}.{table}.{col} "
                    f"({internal}) not in live schema"
                )
                drift_count += 1
                continue
            if expected and live_col["data_type"] not in expected:
                drift_lines.append(
                    f"  [type drift]    {schema}.{table}.{col}: "
                    f"model expects {sorted(expected)}, "
                    f"live has '{live_col['data_type']}'"
                )
                drift_count += 1

    return drift_count, drift_lines


def _cmd_dump(args, connection) -> int:
    inventory = _modeled_table_inventory()
    schemas = [args.schema] if args.schema else _list_tenant_schemas(connection)
    out = {}
    for schema in schemas:
        out[schema] = _dump_columns(connection, schema, inventory.keys())
    print(json.dumps(out, indent=2, default=str))
    return 0


def _cmd_compare(args, connection) -> int:
    schemas = [args.schema] if args.schema else _list_tenant_schemas(connection)
    total_drift = 0
    for schema in schemas:
        drift_count, lines = _compare_schema(connection, schema)
        if drift_count == 0:
            print(f"✅ {schema} — no drift")
        else:
            print(f"❌ {schema} — {drift_count} drift item(s):")
            for line in lines:
                print(line)
        total_drift += drift_count
    return 0 if total_drift == 0 else 1


def _cmd_consensus(args, connection) -> int:
    """Find the consensus column shape per modeled table across all tenants."""
    inventory = _modeled_table_inventory()
    schemas = _list_tenant_schemas(connection)
    if not schemas:
        print("No tenants found in public.organizations", file=sys.stderr)
        return 2

    # per_table: {table: {column: {data_type: count_of_tenants}}}
    per_table: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    table_seen: dict[str, int] = defaultdict(int)

    for schema in schemas:
        live = _dump_columns(connection, schema, inventory.keys())
        for table, cols in live.items():
            table_seen[table] += 1
            for col in cols:
                per_table[table][col["column"]][col["data_type"]] += 1

    out = {}
    for table, model in sorted(inventory.items()):
        seen = table_seen.get(table, 0)
        out[table] = {
            "tenants_with_table": seen,
            "tenants_total": len(schemas),
            "columns": {
                col: {
                    "consensus_type": max(types.items(), key=lambda x: x[1])[0]
                                      if types else None,
                    "type_distribution": dict(types),
                    "tenant_coverage": sum(types.values()),
                }
                for col, types in sorted(per_table[table].items())
            },
        }
    print(json.dumps(out, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_dump = sub.add_parser("dump", help="Dump information_schema.columns for modeled tables")
    p_dump.add_argument("--schema", help="Restrict to one tenant schema")

    p_cmp = sub.add_parser("compare", help="Compare live shapes against canonical Django models")
    p_cmp.add_argument("--schema", help="Restrict to one tenant schema")

    sub.add_parser("consensus", help="Find consensus column shape across all tenants")

    args = parser.parse_args(argv)

    try:
        _setup_django()
    except Exception as exc:
        print(f"Could not boot Django: {exc}", file=sys.stderr)
        return 2

    from django.db import connection

    try:
        if args.cmd == "dump":
            return _cmd_dump(args, connection)
        if args.cmd == "compare":
            return _cmd_compare(args, connection)
        if args.cmd == "consensus":
            return _cmd_consensus(args, connection)
    except Exception as exc:
        print(f"Tool failed: {exc}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
