"""Phase 2 ORM Wave 2 cleanup — registry hygiene.

Mutates ``sqlfiles/objects.sql`` and emits a parallel cleanup SQL
script for already-provisioned tenants. Three operations:

  1. **Add** 12 INSERT rows for setup tables that exist as DDL in
     ``default_tables.sql`` but were missing from the registry.

  2. **Rename** the registry row ``'reports'`` → ``'report'`` to match
     the actual table name created by ``default_tables.sql``.

  3. **Delete** 41 vestigial registry rows — entries with no DDL
     anywhere in the repo and no runtime queries
     (``apex_class``, ``approval_processes``, ``audit_trails``,
     ``auth_*``, ``call_logs``, ``columns_metadata``, ``component``,
     ``connected_app``, ``custom_metadata``, ``custom_setting``,
     ``customers``, ``duplicate_rule``, ``flows``,
     ``group_assignment_tracker``, ``hsitory``, ``import_wizard``,
     ``invoice_items``, ``invoices``, ``lightning_pages``,
     ``matching_rule``, ``named_credential``, ``node``, ``owd``,
     ``package``, ``permission_sets``, ``process_builders``,
     ``products``, ``regions``, ``remote_site_setting``, ``roles``,
     ``sales``, ``setup``, ``sf_integration_lead``, ``sharing_rules``,
     ``tables_metadata``, ``tabs``, ``theme``,
     ``users_user_permissions``, ``workflow_rules``).

The companion cleanup migration ``sqlfiles/phase2_registry_cleanup.sql``
applies the same three operations against an already-provisioned
tenant's ``object`` table — operators run it once per tenant after
deploying the seed change.

Run this script once to regenerate both files; commit the result.
"""

from __future__ import annotations

import re
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OBJECTS_SQL = ROOT / "sqlfiles" / "objects.sql"
CLEANUP_SQL = ROOT / "sqlfiles" / "phase2_registry_cleanup.sql"


# ---------------------------------------------------------------------------
# Action 1 — additions: 12 setup tables that exist in default_tables.sql
#                       but had no registry row.
# Each tuple: (name, label, plural_label)
# ---------------------------------------------------------------------------
ADDITIONS_SETUP = [
    ("callactivity", "Call Activity", "Call Activities"),
    ("dashboard_assignment", "Dashboard Assignment", "Dashboard Assignments"),
    ("dashboard_component", "Dashboard Component", "Dashboard Components"),
    ("dashboard_folder_sharing", "Dashboard Folder Sharing",
     "Dashboard Folder Sharings"),
    ("dashboard_folders", "Dashboard Folders", "Dashboard Folders"),
    ("email_provider_setup", "Email Provider Setup",
     "Email Provider Setups"),
    ("field_mapping", "Field Mapping", "Field Mappings"),
    ("homepage_assignment", "Homepage Assignment", "Homepage Assignments"),
    ("notifications", "Notifications", "Notifications"),
    ("org_company", "Organization Company", "Organization Companies"),
    ("organizations", "Organizations", "Organizations"),  # Django-modeled
    ("page_builder", "Page Builder", "Page Builders"),
    ("page_component", "Page Component", "Page Components"),
    ("report_folder", "Report Folder", "Report Folders"),
    ("report_folder_sharing", "Report Folder Sharing",
     "Report Folder Sharings"),
    ("shared_records", "Shared Records (per-record)",
     "Shared Records (per-record)"),
    ("telephony_user", "Telephony User", "Telephony Users"),
    ("user_gmail_tokens", "User Gmail Tokens", "User Gmail Tokens"),
    ("user_group_profiles", "User Group Profiles", "User Group Profiles"),
    ("user_group_public_groups", "User Group Public Groups",
     "User Group Public Groups"),
    ("user_outlook_tokens", "User Outlook Tokens", "User Outlook Tokens"),
]


# ---------------------------------------------------------------------------
# Action 2 — additions: 2 business tables that exist in tables.sql
#                       but had no registry row.
# Each tuple: (name, label, plural_label)
# ---------------------------------------------------------------------------
ADDITIONS_BUSINESS = [
    ("activity", "Activity", "Activities"),
    ("email", "Email Record", "Email Records"),
]


# ---------------------------------------------------------------------------
# Action 3 — rename: registry uses 'reports' but DDL is 'report'.
# ---------------------------------------------------------------------------
RENAME = ("reports", "report", "Report", "Reports")  # old, new, label, plural


# ---------------------------------------------------------------------------
# Action 4 — deletions: vestigial setup rows (no DDL, no runtime queries).
# Verified via grep -rE '(FROM|INTO|UPDATE)\s+<name>\b' against every
# Python source root; only `lead_capture` had hits (kept).
# ---------------------------------------------------------------------------
DELETIONS_VESTIGIAL = [
    "apex_class",
    "approval_processes",
    "audit_trails",
    "auth_group",
    "auth_group_permissions",
    "auth_permission",
    "call_logs",
    "columns_metadata",
    "component",
    "connected_app",
    "custom_metadata",
    "custom_setting",
    "customers",          # legacy duplicate of business 'customer'
    "duplicate_rule",
    "flows",
    "group_assignment_tracker",
    "hsitory",            # known typo of 'history' — but unused, so drop
    "import_wizard",
    "invoice_items",      # legacy duplicate of business 'invoice_item'
    "invoices",           # legacy duplicate of business 'invoice'
    "lightning_pages",
    "matching_rule",
    "named_credential",
    "node",
    "owd",
    "package",
    "permission_sets",
    "process_builders",
    "products",           # legacy duplicate of business 'product'
    "regions",
    "remote_site_setting",
    "roles",
    "sales",
    "setup",
    "sf_integration_lead",
    "sharing_rules",
    "tables_metadata",
    "tabs",
    "theme",
    "users_user_permissions",
    "workflow_rules",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# The 27-column header from objects.sql — we generate matching tuples.
# Order: id, allow_activities, allow_bulk_api_access, allow_in_chatter_groups,
# allow_reports, allow_sharing, allow_streaming_api_access, datatype, icon,
# icon_color, deployment_status, description, enable_licensing, label, name,
# plural_label, record_name, search_status, show_tab, starts_with_vowel_sound,
# track_field_history, prefix, created_date, last_modified_date,
# default_access_level, type, setup
NEW_ROW_TS = "'2026-05-03 00:00:00.000000+05:30'"


def _new_setup_id() -> str:
    return f"oBt_{uuid.uuid4().hex[:8]}-{uuid.uuid4().hex[:3]}"


def _new_business_id() -> str:
    return uuid.uuid4().hex[:10]


def build_setup_tuple(name: str, label: str, plural: str) -> str:
    return (
        f"    ('{_new_setup_id()}', "
        f"'False', 'False', 'False', 'False', 'False', 'False', "
        f"NULL, NULL, NULL, NULL, NULL, 'False', "
        f"'{label}', '{name}', '{plural}', "
        f"NULL, 'False', 'False', 'False', 'False', NULL, "
        f"{NEW_ROW_TS}, {NEW_ROW_TS}, NULL, 'standard', 'True')"
    )


def build_business_tuple(name: str, label: str, plural: str) -> str:
    return (
        f"    ('{_new_business_id()}', "
        f"'True', 'False', 'True', 'True', 'False', 'True', "
        f"'Text', NULL, NULL, 'Deployed', NULL, 'False', "
        f"'{label}', '{name}', '{plural}', "
        f"'{label}', 'True', 'True', 'False', 'True', NULL, "
        f"{NEW_ROW_TS}, {NEW_ROW_TS}, NULL, 'standard', 'False')"
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

_VAL_RE = re.compile(r"NULL|'(?:[^'\\]|\\.)*'", re.DOTALL)
_ROW_RE = re.compile(r"\((?:[^()']|'[^']*')+\)", re.DOTALL)


def _parse_rows(insert_block: str) -> list[tuple[str, str]]:
    """Return list of (name, full_row_text) for each row in the INSERT block."""
    out = []
    for m in _ROW_RE.finditer(insert_block):
        row = m.group(0)
        vs = _VAL_RE.findall(row)
        if len(vs) < 27:
            continue
        name = vs[14].strip("'")
        out.append((name, row))
    return out


def main():
    src = OBJECTS_SQL.read_text(encoding="utf-8")
    insert_idx = src.find('INSERT INTO "object"')
    if insert_idx < 0:
        raise SystemExit("Could not find INSERT INTO \"object\" header")

    # Find where the VALUES list starts (after `) VALUES\n`)
    header_end = src.index("VALUES", insert_idx) + len("VALUES")
    # Tail: everything from the trailing `;` of the INSERT onward.
    semi_idx = src.index(";", header_end)
    body = src[header_end:semi_idx]
    tail = src[semi_idx:]

    parsed = _parse_rows(body)
    print(f"Parsed {len(parsed)} existing rows")

    # 1) Drop vestigial entries.
    keep = [(n, r) for (n, r) in parsed if n not in DELETIONS_VESTIGIAL]
    dropped = len(parsed) - len(keep)
    print(f"Dropping {dropped} vestigial rows")

    # 2) Rename 'reports' -> 'report'.
    if RENAME[0] != RENAME[1]:
        renamed = []
        rename_count = 0
        for n, r in keep:
            if n == RENAME[0]:
                # Replace plural-and-name pair in the original row text.
                # The row keeps its id/timestamps; we just rewrite name +
                # label + plural columns.
                # Order in the row: ... 'False','{label}','{name}','{plural_label}', ...
                new_row = re.sub(
                    r"'False',\s*'[^']*',\s*'reports',\s*'[^']*'",
                    f"'False', '{RENAME[2]}', '{RENAME[1]}', '{RENAME[3]}'",
                    r,
                )
                if new_row == r:
                    # Fallback: replace the bare 'reports' literal.
                    new_row = r.replace("'reports'", f"'{RENAME[1]}'")
                renamed.append((RENAME[1], new_row))
                rename_count += 1
            else:
                renamed.append((n, r))
        keep = renamed
        print(f"Renamed {rename_count} row(s) {RENAME[0]!r} → {RENAME[1]!r}")

    # 3) Append new setup + business rows.
    new_setup_rows = [build_setup_tuple(*t) for t in ADDITIONS_SETUP]
    new_biz_rows = [build_business_tuple(*t) for t in ADDITIONS_BUSINESS]
    new_count = len(new_setup_rows) + len(new_biz_rows)
    print(f"Adding {new_count} new rows ({len(new_setup_rows)} setup + "
          f"{len(new_biz_rows)} business)")

    # Reassemble: header `VALUES\n  row1,\n  row2,\n  ...,\n  rowN;\n` shape.
    all_rows = [r for (_n, r) in keep] + new_setup_rows + new_biz_rows
    new_body = "\n" + ",\n".join(all_rows) + "\n"
    new_src = src[:header_end] + new_body + tail
    OBJECTS_SQL.write_text(new_src, encoding="utf-8")
    print(f"Wrote {OBJECTS_SQL}  ({len(all_rows)} total rows)")

    # ---- Generate cleanup migration for already-provisioned tenants ----
    lines = [
        "-- Phase 2 ORM Wave 2 — registry cleanup migration.",
        "--",
        "-- Apply once per tenant schema after deploying the new",
        "-- objects.sql seed. Idempotent: each operation is a no-op",
        "-- if already applied.",
        "--",
        "-- Operator usage:",
        "--   SET search_path TO <tenant_schema>;",
        "--   \\i sqlfiles/phase2_registry_cleanup.sql",
        "",
        "BEGIN;",
        "",
        "-- (1) Drop vestigial registry rows.",
    ]
    if DELETIONS_VESTIGIAL:
        delete_list = ", ".join(f"'{n}'" for n in DELETIONS_VESTIGIAL)
        lines.append(f"DELETE FROM object WHERE name IN ({delete_list});")
    lines.append("")
    lines.append(
        "-- (2) Rename 'reports' → 'report' so the registry name matches"
    )
    lines.append("--     the actual table created by default_tables.sql.")
    lines.append(
        f"UPDATE object SET name = '{RENAME[1]}', "
        f"label = '{RENAME[2]}', plural_label = '{RENAME[3]}' "
        f"WHERE name = '{RENAME[0]}';"
    )
    lines.append("")
    lines.append("-- (3) Insert missing setup-table registry rows.")
    for name, label, plural in ADDITIONS_SETUP:
        lines.append(
            f"INSERT INTO object (name, label, plural_label, type, setup) "
            f"VALUES ('{name}', '{label}', '{plural}', 'standard', TRUE) "
            f"ON CONFLICT DO NOTHING;"
        )
    lines.append("")
    lines.append("-- (4) Insert missing business-object registry rows.")
    for name, label, plural in ADDITIONS_BUSINESS:
        lines.append(
            f"INSERT INTO object (name, label, plural_label, type, setup) "
            f"VALUES ('{name}', '{label}', '{plural}', 'standard', FALSE) "
            f"ON CONFLICT DO NOTHING;"
        )
    lines.append("")
    lines.append("COMMIT;")

    CLEANUP_SQL.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {CLEANUP_SQL}")


if __name__ == "__main__":
    main()
