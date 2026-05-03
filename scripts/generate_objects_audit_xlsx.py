"""
Build an Excel audit workbook of every entry in the `object` registry.

Reads the seed data in sqlfiles/objects.sql, cross-references the Django
models actually defined in the codebase, and emits an .xlsx with three
sheets: Summary, All_Objects, Migration_Plan.
"""
import os
import re
import sys
from collections import OrderedDict

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo


ROOT = "/home/user/business-bussus-django"
OBJECTS_SQL = os.path.join(ROOT, "sqlfiles", "objects.sql")
OUT_XLSX = os.path.join(ROOT, "objects_audit.xlsx")


# Tables already defined as Django models in the codebase (db_table -> source path)
DJANGO_MODELED = {
    "organizations":         "api/models.py:Organization",
    "users":                 "api/models.py:User",
    "session_log":           "api/models.py:SessionLog",
    "user_login_history":    "api/models.py:UserLoginHistory",
    "facebook_lead":         "facebook/models.py",
    "facebookleadwebhooks":  "facebook/models.py",
    "message":               "whatsapp/models.py",
    "channel":               "whatsapp/models.py",
    "webhook":               "whatsapp/models.py",
    "salesforce_metadata":   "sf_integration/models.py",
    "salesforce_settings":   "sf_integration/models.py",
    "salesforce_sync":       "sf_integration/models.py",
}


# Functional grouping for setup tables (used for the Subcategory column)
SETUP_GROUPS = {
    # Platform metadata
    "object":                "Platform Metadata",
    "fields":                "Platform Metadata",
    "tables_metadata":       "Platform Metadata",
    "columns_metadata":      "Platform Metadata",
    "setup":                 "Platform Metadata",
    "custom_metadata":       "Platform Metadata",
    "custom_setting":        "Platform Metadata",
    # Authorization & sharing
    "profile":               "Authorization",
    "permission_sets":       "Authorization",
    "roles":                 "Authorization",
    "user_group":            "Authorization",
    "user_group_users":      "Authorization",
    "users_user_permissions":"Authorization",
    "object_permissions":    "Authorization",
    "field_permissions":     "Authorization",
    "tab_permissions":       "Authorization",
    "app_permissions":       "Authorization",
    "sharing_records":       "Authorization",
    "sharing_rules":         "Authorization",
    "owd":                   "Authorization",
    "auth_group":            "Authorization (Django)",
    "auth_group_permissions":"Authorization (Django)",
    "auth_permission":       "Authorization (Django)",
    # Identity
    "users":                 "Identity",
    # UI / layout / navigation
    "app":                   "UI / Layout",
    "tabs":                  "UI / Layout",
    "page_layouts":          "UI / Layout",
    "page_builder_assignment":"UI / Layout",
    "layout_assignment":     "UI / Layout",
    "lightning_pages":       "UI / Layout",
    "path_builder":          "UI / Layout",
    "search_layouts":        "UI / Layout",
    "listviews":             "UI / Layout",
    "theme":                 "UI / Layout",
    "component":             "UI / Layout",
    # Reporting / files
    "reports":               "Reporting",
    "dashboard":             "Reporting",
    "file":                  "Files",
    "import_wizard":         "Files",
    # Workflow / automation
    "workflow":              "Workflow",
    "workflow_node":         "Workflow",
    "workflow_edge":         "Workflow",
    "workflow_rules":        "Workflow",
    "process_builders":      "Workflow",
    "flows":                 "Workflow",
    "approval_processes":    "Workflow",
    "node":                  "Workflow",
    "matching_rule":         "Workflow",
    "duplicate_rule":        "Workflow",
    "lead_capture":          "Workflow",
    "email_templates":       "Workflow",
    # Integration / API
    "apex_class":            "Integration",
    "connected_app":         "Integration",
    "named_credential":      "Integration",
    "remote_site_setting":   "Integration",
    "package":               "Integration",
    "webhook":               "Integration",
    "facebook_lead":         "Integration",
    "sf_integration_lead":   "Integration",
    "salesforce_metadata":   "Integration",
    "salesforce_settings":   "Integration",
    "salesforce_sync":       "Integration",
    "landing_numbers":       "Integration / Telephony",
    "telephony_config":      "Integration / Telephony",
    "call_logs":             "Integration / Telephony",
    # Audit / history
    "audit_trails":          "Audit / History",
    "audit_trail_track":     "Audit / History",
    "field_history_log":     "Audit / History",
    "field_tracking_config": "Audit / History",
    "hsitory":               "Audit / History (typo: 'history')",
    "session_log":           "Audit / History",
    "user_login_history":    "Audit / History",
    "group_assignment_tracker":"Audit / History",
    # Messaging
    "message":               "Messaging",
    "channel":               "Messaging",
    # Misc / region / sales / task
    "regions":               "Sales Ops",
    "sales":                 "Sales Ops",
    "task":                  "Sales Ops",
    # Possible legacy duplicates of business-object names
    "customers":             "Legacy / Possible duplicate of 'customer'",
    "products":              "Legacy / Possible duplicate of 'product'",
    "invoices":              "Legacy / Possible duplicate of 'invoice'",
    "invoice_items":         "Legacy / Possible duplicate of 'invoice_item'",
    # Django framework tables
    "django_admin_log":      "Django Framework",
    "django_content_type":   "Django Framework",
    "django_migrations":     "Django Framework",
    "django_session":        "Django Framework",
    "django_celery_beat_clockedschedule":   "Django Framework (Celery Beat)",
    "django_celery_beat_crontabschedule":   "Django Framework (Celery Beat)",
    "django_celery_beat_intervalschedule":  "Django Framework (Celery Beat)",
    "django_celery_beat_periodictask":      "Django Framework (Celery Beat)",
    "django_celery_beat_periodictasks":     "Django Framework (Celery Beat)",
    "django_celery_beat_solarschedule":     "Django Framework (Celery Beat)",
}


# ---------- parsing -------------------------------------------------------- #
COL_ORDER = [
    "id", "allow_activities", "allow_bulk_api_access",
    "allow_in_chatter_groups", "allow_reports", "allow_sharing",
    "allow_streaming_api_access", "datatype", "icon", "icon_color",
    "deployment_status", "description", "enable_licensing", "label",
    "name", "plural_label", "record_name", "search_status",
    "show_tab", "starts_with_vowel_sound", "track_field_history",
    "prefix", "created_date", "last_modified_date",
    "default_access_level", "type", "setup",
]

VALUE_RE = re.compile(r"NULL|'(?:[^'\\]|\\.)*'", re.DOTALL)


def parse_objects_sql(path: str):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    start = text.find('INSERT INTO "object"')
    if start < 0:
        sys.exit("Could not find INSERT INTO \"object\" in objects.sql")
    block = text[start:]

    # naive paren-balanced row extractor
    rows = []
    depth = 0
    buf = []
    in_string = False
    for ch in block:
        if ch == "'" and (not buf or buf[-1] != "\\"):
            in_string = not in_string
        if not in_string:
            if ch == "(":
                if depth == 0:
                    buf = []
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    rows.append("(" + "".join(buf) + ")")
                    continue
        if depth > 0:
            buf.append(ch)

    parsed = []
    for raw in rows:
        values = VALUE_RE.findall(raw)
        if len(values) < len(COL_ORDER):
            continue
        rec = {}
        for col, val in zip(COL_ORDER, values):
            if val == "NULL":
                rec[col] = None
            else:
                rec[col] = val.strip("'")
        parsed.append(rec)
    return parsed


# ---------- categorization ------------------------------------------------- #
def categorize(rec):
    setup = rec.get("setup") == "True"
    typ = (rec.get("type") or "").lower()
    if setup:
        return "SETUP"
    if typ == "custom":
        return "BUSINESS / CUSTOM"
    return "BUSINESS / STANDARD"


def subcategory(rec):
    name = rec["name"]
    if rec.get("setup") == "True":
        return SETUP_GROUPS.get(name, "Setup (uncategorized)")
    if (rec.get("type") or "").lower() == "custom":
        return "User-defined"
    return "Standard business object"


def migration_recommendation(rec):
    name = rec["name"]
    if rec.get("setup") == "True":
        if name.startswith("django_"):
            return "Skip — managed by Django/Celery framework"
        if name in DJANGO_MODELED:
            return "Already in Django ORM — audit & harden"
        if name == "hsitory":
            return "Rename to 'history' then migrate to Django ORM"
        if name in ("customers", "products", "invoices", "invoice_items"):
            return "Investigate — likely legacy duplicate of business object"
        return "Migrate to Django ORM"
    return "Keep raw SQL — dynamic schema via metadata gateway"


# ---------- workbook building --------------------------------------------- #
HEADER_FILL = PatternFill("solid", fgColor="305496")
HEADER_FONT = Font(color="FFFFFF", bold=True)
SETUP_FILL = PatternFill("solid", fgColor="DDEBF7")
STD_BIZ_FILL = PatternFill("solid", fgColor="FFF2CC")
CUSTOM_BIZ_FILL = PatternFill("solid", fgColor="E2EFDA")
THIN = Side(border_style="thin", color="BFBFBF")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def style_header(ws, ncols):
    for col in range(1, ncols + 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        cell.border = BORDER
    ws.row_dimensions[1].height = 32
    ws.freeze_panes = "A2"


def autosize(ws, headers, max_w=60):
    for i, h in enumerate(headers, start=1):
        col_letter = get_column_letter(i)
        max_len = len(str(h))
        for cell in ws[col_letter][1:]:
            v = cell.value
            if v is not None:
                max_len = max(max_len, len(str(v)))
        ws.column_dimensions[col_letter].width = min(max_w, max_len + 2)


def add_summary(wb, parsed):
    ws = wb.create_sheet("Summary", 0)
    ws.append(["Bucket", "Count", "Notes"])

    n_setup = sum(1 for r in parsed if r.get("setup") == "True")
    n_std = sum(1 for r in parsed if r.get("setup") != "True"
                and (r.get("type") or "").lower() == "standard")
    n_cust = sum(1 for r in parsed if r.get("setup") != "True"
                 and (r.get("type") or "").lower() == "custom")
    n_django_modeled = sum(1 for r in parsed if r["name"] in DJANGO_MODELED)
    n_django_framework = sum(1 for r in parsed if r["name"].startswith("django_"))
    n_legacy = sum(1 for r in parsed if r["name"]
                   in ("customers", "products", "invoices", "invoice_items"))

    rows = [
        ("Total objects in registry", len(parsed), ""),
        ("Setup objects (setup=TRUE)", n_setup, "Fixed schema → migrate to Django ORM"),
        ("Standard business objects (setup=FALSE, type=standard)", n_std,
         "Dynamic schema → keep raw SQL via gateway"),
        ("Custom business objects (setup=FALSE, type=custom)", n_cust,
         "User-defined → keep raw SQL via gateway"),
        ("", "", ""),
        ("Already in Django ORM (db_table mapped)", n_django_modeled,
         "12 setup tables — audit & harden"),
        ("Setup tables that are Django framework / Celery", n_django_framework,
         "Skip — managed by Django/Celery"),
        ("Setup tables suspected legacy duplicates of business objects",
         n_legacy, "customers/products/invoices/invoice_items"),
        ("", "", ""),
        ("Setup tables remaining to migrate to Django ORM",
         n_setup - n_django_modeled - n_django_framework - n_legacy,
         "Primary migration scope"),
    ]
    for r in rows:
        ws.append(r)
    style_header(ws, 3)
    autosize(ws, ["Bucket", "Count", "Notes"])


def add_all_objects(wb, parsed):
    ws = wb.create_sheet("All_Objects")
    headers = [
        "Category", "Subcategory", "Name", "Label", "Plural Label",
        "Type", "Setup?", "Default Access Level", "Deployment Status",
        "Show Tab", "Allow Reports", "Allow Sharing",
        "Track Field History", "Prefix", "Currently in Django ORM?",
        "Django Model Source", "Migration Recommendation",
    ]
    ws.append(headers)

    # sort: SETUP first, then STANDARD, then CUSTOM; within each by name
    cat_order = {"SETUP": 0, "BUSINESS / STANDARD": 1, "BUSINESS / CUSTOM": 2}
    sorted_recs = sorted(parsed, key=lambda r: (cat_order[categorize(r)], r["name"]))

    for r in sorted_recs:
        cat = categorize(r)
        in_django = r["name"] in DJANGO_MODELED
        ws.append([
            cat,
            subcategory(r),
            r["name"],
            r.get("label"),
            r.get("plural_label"),
            r.get("type"),
            r.get("setup"),
            r.get("default_access_level"),
            r.get("deployment_status"),
            r.get("show_tab"),
            r.get("allow_reports"),
            r.get("allow_sharing"),
            r.get("track_field_history"),
            r.get("prefix"),
            "Yes" if in_django else "No",
            DJANGO_MODELED.get(r["name"], ""),
            migration_recommendation(r),
        ])

    style_header(ws, len(headers))

    # color-band rows by category
    for i, r in enumerate(sorted_recs, start=2):
        cat = categorize(r)
        fill = (SETUP_FILL if cat == "SETUP"
                else STD_BIZ_FILL if cat == "BUSINESS / STANDARD"
                else CUSTOM_BIZ_FILL)
        for c in range(1, len(headers) + 1):
            ws.cell(row=i, column=c).fill = fill
            ws.cell(row=i, column=c).border = BORDER
            ws.cell(row=i, column=c).alignment = Alignment(
                vertical="top", wrap_text=True
            )

    autosize(ws, headers)

    # turn it into a real Excel table for filtering
    last_col = get_column_letter(len(headers))
    last_row = ws.max_row
    table = Table(displayName="AllObjects", ref=f"A1:{last_col}{last_row}")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleLight1", showRowStripes=False, showColumnStripes=False
    )
    ws.add_table(table)


def add_migration_plan(wb, parsed):
    ws = wb.create_sheet("Migration_Plan")
    headers = [
        "Phase", "Wave", "Object Name", "Label", "Subcategory",
        "Action", "Notes",
    ]
    ws.append(headers)

    waves = OrderedDict()
    waves["Wave 1 — Core platform metadata"] = [
        "object", "fields", "tables_metadata", "columns_metadata", "setup",
    ]
    waves["Wave 2 — Authorization (high-risk)"] = [
        "profile", "permission_sets", "roles",
        "user_group", "user_group_users", "users_user_permissions",
        "object_permissions", "field_permissions",
        "tab_permissions", "app_permissions",
        "sharing_records", "sharing_rules", "owd",
    ]
    waves["Wave 3 — UI / layout / navigation"] = [
        "app", "tabs", "page_layouts", "page_builder_assignment",
        "layout_assignment", "lightning_pages", "path_builder",
        "search_layouts", "listviews", "theme", "component",
    ]
    waves["Wave 4 — Reporting / files"] = [
        "reports", "dashboard", "file", "import_wizard",
    ]
    waves["Wave 5 — Workflow / automation"] = [
        "workflow", "workflow_node", "workflow_edge", "workflow_rules",
        "process_builders", "flows", "approval_processes", "node",
        "matching_rule", "duplicate_rule", "lead_capture", "email_templates",
    ]
    waves["Wave 6 — Integration / telephony"] = [
        "apex_class", "connected_app", "named_credential", "remote_site_setting",
        "package", "sf_integration_lead",
        "landing_numbers", "telephony_config", "call_logs",
    ]
    waves["Wave 7 — Audit / history"] = [
        "audit_trails", "audit_trail_track", "field_history_log",
        "field_tracking_config", "hsitory", "group_assignment_tracker",
    ]
    waves["Wave 8 — Misc / sales ops"] = [
        "regions", "sales", "task", "custom_metadata", "custom_setting",
    ]

    name_to_rec = {r["name"]: r for r in parsed}

    # Phase 1 — already-modeled audit
    for n in sorted(DJANGO_MODELED.keys()):
        rec = name_to_rec.get(n)
        if not rec:
            continue
        ws.append([
            "Phase 1 — Audit existing Django models",
            "—",
            n,
            rec.get("label"),
            subcategory(rec),
            "Audit & harden",
            DJANGO_MODELED[n],
        ])

    # Phase 2 — wave-based migration of remaining setup tables
    for wave_name, objs in waves.items():
        for n in objs:
            rec = name_to_rec.get(n)
            if not rec:
                continue
            if n in DJANGO_MODELED:
                continue
            ws.append([
                "Phase 2 — Migrate setup tables to Django ORM",
                wave_name,
                n,
                rec.get("label"),
                subcategory(rec),
                "Build Django model + migration; replace raw SQL callsites",
                "",
            ])

    # Phase 3 — investigate legacy duplicates
    for n in ("customers", "products", "invoices", "invoice_items"):
        rec = name_to_rec.get(n)
        if not rec:
            continue
        ws.append([
            "Phase 3 — Resolve legacy duplicates",
            "—",
            n,
            rec.get("label"),
            subcategory(rec),
            "Investigate & merge or delete",
            f"Possible duplicate of business object '{n.rstrip('s')}'",
        ])

    # Phase 4 — Django framework — leave alone
    for n in sorted(r["name"] for r in parsed if r["name"].startswith("django_")):
        rec = name_to_rec.get(n)
        if not rec:
            continue
        ws.append([
            "Phase 4 — Skip (Django/Celery managed)",
            "—",
            n,
            rec.get("label"),
            subcategory(rec),
            "No action — framework owns it",
            "",
        ])

    # Phase 5 — Business objects — keep raw SQL
    for r in sorted(parsed, key=lambda x: x["name"]):
        if r.get("setup") == "True":
            continue
        ws.append([
            "Phase 5 — Business objects (raw SQL via gateway)",
            "Standard" if (r.get("type") or "").lower() == "standard" else "Custom",
            r["name"],
            r.get("label"),
            subcategory(r),
            "Route through hardened ORM gateway (sql.Identifier + schema authority)",
            "Dynamic schema — cannot be a static Django model",
        ])

    style_header(ws, len(headers))

    for row in ws.iter_rows(min_row=2, max_row=ws.max_row,
                            min_col=1, max_col=len(headers)):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = BORDER

    autosize(ws, headers, max_w=80)

    last_col = get_column_letter(len(headers))
    table = Table(displayName="MigrationPlan",
                  ref=f"A1:{last_col}{ws.max_row}")
    table.tableStyleInfo = TableStyleInfo(
        name="TableStyleLight9", showRowStripes=True
    )
    ws.add_table(table)


def main():
    parsed = parse_objects_sql(OBJECTS_SQL)
    print(f"Parsed {len(parsed)} object rows")

    wb = Workbook()
    # remove default sheet
    default = wb.active
    wb.remove(default)

    add_summary(wb, parsed)
    add_all_objects(wb, parsed)
    add_migration_plan(wb, parsed)

    wb.save(OUT_XLSX)
    print(f"Wrote {OUT_XLSX}")


if __name__ == "__main__":
    main()
