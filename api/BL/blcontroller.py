import json
from django.apps import apps
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from django.contrib.auth.hashers import make_password

#from api.ORM.setup.ObjectManager.field_execution import update_field_in_table
from CacheService.cache import CacheService
from api.BL.Listviews.GetListview import GetListviews, enrich_task_with_related_to, field_level_permissions, get_dynamic_listview
from api.BL.ObjectManager.ObjectWithSetup import get_objects_for_report
from api.BL.ObjectManager.ObjectWithoutSetup import get_field_mapping
from api.BL.ObjectManager.SearchLayouts import GetSearchLayouts
from api.BL.PageBuilder.get_pagebuilder import get_pagebuilder
from api.BL.PageLayouts.page_layout import PageLayouts
from api.BL.PreviewPage.GetPreviewPage import get_preview_page
from api.BL.Profiles.patch_profiles import update_profiles
from api.BL.Reports.get_reports import get_reports
from api.BL.Users.CreateUsers import UserBussinessLogic
from api.BL.dashboards.dashboard import get_dashboards
from api.BL.home.home import get_home_page
from api.BL.utils import construct_filters
from api.BL.whatsapp.utils import post_whatsapp
from public.utils.objects.builk_object_creation import create_bulk_objects
from utils.filter_logic_validator import validate_filter_logic
from .whatsapp.whatsapp import WhatsAppService
from api.ORM.setup.update_page_builder import update_page_builder
from api.ORM.sqlFunctions.information_schema import get_information_schema, is_deleted_field_exist, column_exists
from api.emailsend.views import send_test_email
from api.BL.recycle_bin import empty_recycle_bin, get_deleted_records, permanently_delete_records, restore_soft_deleted_records

# Report detail-row caps. Keep preview responsive on parent-child datasets:
# bound children per parent and the overall row count. Callers inspect the
# returned `truncated` flag to show a "results truncated" hint in the UI.
REPORT_MAX_CHILDREN_PER_PARENT = 200
REPORT_MAX_DETAIL_ROWS = 5000


def _cap_details_per_parent(details, parent_fk, max_per_parent=REPORT_MAX_CHILDREN_PER_PARENT):
    """Keep at most `max_per_parent` rows per parent FK. Returns (trimmed, truncated)."""
    if not details or not parent_fk:
        return details, False
    trimmed = []
    seen = {}
    truncated = False
    for row in details:
        key = row.get(parent_fk)
        count = seen.get(key, 0)
        if count < max_per_parent:
            trimmed.append(row)
            seen[key] = count + 1
        else:
            truncated = True
    return trimmed, truncated


def _normalize_csv_ilike_filters(filters):
    """Rewrite multi-value ILIKE filters that arrive as a single comma-
    separated string into proper IN filters.

    Multi-select widgets sometimes serialise N picked values as
    `{operator: ilike, value: '%a,b,c,...%'}`. Postgres can't index that
    pattern (no leading anchor) AND the comma-joined literal matches no
    real row anyway, so the query degenerates into a sequential scan
    that returns nothing — the report's edit-page preview hangs for
    several seconds before rendering an empty table.

    Triggers when ALL these hold:
      • operator is ilike / contains
      • value is a string containing at least one comma
      • the field name ends with `_id` (so a CSV value is unmistakably
        a list of identifiers, not free-form text the user typed)
    Any other ILIKE filter is passed through unchanged.
    """
    if not isinstance(filters, list):
        return filters
    out = []
    for f in filters:
        if not isinstance(f, dict):
            out.append(f)
            continue
        op = (f.get('operator') or '').lower()
        if op not in ('ilike', 'contains'):
            out.append(f)
            continue
        field = f.get('field') or ''
        value = f.get('value')
        if not (isinstance(field, str) and field.endswith('_id')
                and isinstance(value, str) and ',' in value):
            out.append(f)
            continue
        # Strip surrounding %s the UI tacks on for ILIKE, then split.
        cleaned = value.strip().strip('%')
        parts = [p.strip() for p in cleaned.split(',') if p.strip()]
        if not parts:
            out.append(f)
            continue
        new_f = dict(f)
        new_f['operator'] = 'in'
        new_f['value'] = parts
        out.append(new_f)
    return out
from api.BL.task import get_related_tasks,user_can_make_call
from api.ORM.setup.ObjectManager.create_field import create_field
from api.ORM.setup.workflows.create_workflow import create_workflow, validate_single_formula
from api.ORM.setup.ObjectManager.delete_field import delete_field
from api.ORM.setup.workflows.update_workflow import update_workflow
from api.ORM.setup.ObjectManager.delete_object import delete_customobject
from api.ORM.setup.ObjectManager.post_object import post_customobject
from api.ORM.sqlFunctions.createSQLFunction import post_data_sql
from api.ORM.sqlFunctions.deleteSQLFunction import delete_data_sql
from api.permissions.permissions import get_permissions, patch_permission, post_permission, delete_permission, get_field_metadata
from api.permissions.FetchUsers.fetch_shared_records import fetch_shared_records
from facebook.TaskCreation import register_facebook_webhook
from facebook.pageAccessToken import get_long_lived_page_token
from django.contrib.postgres.search import SearchVector, SearchQuery, SearchRank
from django.db import transaction
from utils.field_tracking import get_field_tracking_data
from utils.target_item_filters import enrich_target_item_with_assigned_to
from api.formulas.evaluate_formula import process_formula
from api.formulas.evaluate_rollup import evaluate_rollup_fields
from .dashboard import build_folder_tree
from .utils import encrypt_dict

from django.db import transaction
from utils.file_handling import handle_file_upload

from .recycle_bin import empty_recycle_bin, get_deleted_records, permanently_delete_records, restore_soft_deleted_records
from utils.field_tracking import get_field_tracking_data, update_tracked_fields,get_field_history
from utils.usergroup_utils import patch_user_group,get_permissions_with_users, get_permissions_with_child_tables
from django.db import connection
from api.ORM.sqlFunctions.relationships import find_relationship_paths, get_object_relationships, get_lookup_relationships
from ..notifications.notify import trigger_notication,get_admin,get_user_details
from channels.layers import get_channel_layer
from pprint import pprint
from asgiref.sync import async_to_sync
from ..emailsend.utils.nylas_service import send_email_using_nylas
from api.ORM.setup.ObjectManager.field_execution import update_field_in_table
from pprint import pprint

import requests
class BusinessLogicHandler:
    def __init__(self, request, object_name):
        self.request = request
        self.object_name = object_name
        self.channel = get_channel_layer()

    def get_business_logic(self, **kwargs):
        another_object = kwargs.get('object_name')
        id = self.request.GET.get('id') 
        param3 = kwargs.get('param3')    
        profile_id = kwargs.get('profile_id')
        user_id = kwargs.get('user_', {}).get('id')
        if self.object_name == 'listview':
            data = GetListviews(self.request, **kwargs)
            return data
        elif self.object_name == 'home':
            return get_home_page(self.request, **kwargs)
        elif self.object_name == 'report':
            import time as _time_report
            _t_total = _time_report.perf_counter()
            _t_last = _t_total
            def _lap(label):
                nonlocal _t_last
                now = _time_report.perf_counter()
                # print(f"[report-perf] {label}: {(now - _t_last) * 1000:.1f} ms")
                _t_last = now
            report_id = self.request.GET.get('id')
            # No `limit` query param means "return everything the report
            # produces" — used by the home dashboard charts which now
            # render every group the saved report defines, no client-side
            # pagination. Only coerce when an explicit value is supplied.
            raw_limit = self.request.GET.get('limit')
            if raw_limit is None or raw_limit == '':
                limit = None
            else:
                try:
                    limit = int(raw_limit)
                except (TypeError, ValueError):
                    limit = None
            offset = self.request.GET.get("offset", 0)
            try:
                offset = int(offset)
            except (TypeError, ValueError):
                offset = 0
            # Detail-grid pagination: when the client passes details_limit /
            # details_offset explicitly, we take it as a signal that the UI
            # is doing its own pagination — we honour the slice verbatim and
            # skip the REPORT_MAX_DETAIL_ROWS / per-parent caps below.
            raw_details_limit = self.request.GET.get('details_limit')
            raw_details_offset = self.request.GET.get('details_offset')
            client_paginating_details = raw_details_limit is not None
            try:
                details_limit_override = int(raw_details_limit) if raw_details_limit is not None else None
            except (TypeError, ValueError):
                details_limit_override = None
                client_paginating_details = False
            try:
                details_offset_override = int(raw_details_offset) if raw_details_offset is not None else 0
            except (TypeError, ValueError):
                details_offset_override = 0
            # Client opt-in: skip the expensive summary GROUP BY when the UI
            # is only rendering the flat detail grid. Huge-object saver.
            skip_summary_flag = str(self.request.GET.get('skip_summary', '')).lower() in ('1', 'true', 'yes')
            # Client opt-in: run the summary GROUP BY against the FULL filtered
            # table instead of scoping it to the paginated parent_values set.
            # Used by the saved-report preview so a 50-row detail page doesn't
            # collapse a 3L-row aggregation down to a 50-row sample. The
            # detail-grid pagination still drives `details_limit/offset`.
            full_summary_flag = str(self.request.GET.get('full_summary', '')).lower() in ('1', 'true', 'yes')
            if not report_id:
                raise Exception("Report ID is required.")

            # Step 1: Fetch report definition
            report_data = get_permissions(
                self.request,
                tableName='report',
                where=[{'field': 'id', 'value': report_id, 'operator': '='}],
                **kwargs
            ).get('data')
            _lap("fetch report definition")
            if not report_data:
                raise Exception('Report not found.')
            report = report_data[0]
            report_name = report.get('name')
            fields = report.get('fields') or []
            # `filters_raw` is what we hand back to the UI — preserve the
            # exact saved shape so the edit-report form renders the same
            # filter chip the user authored (the multi-select widget binds
            # to its own ILIKE-CSV encoding). `filters` is the in-memory
            # copy the SQL pipeline uses; we normalise just that one so
            # Postgres gets a real IN list and the index does its job.
            filters_raw = report.get('filters') or []
            filters = _normalize_csv_ilike_filters(filters_raw)
            group_by = report.get('group_by') or []
            filter_logic = report.get('filter_logic')
            table_name = report.get('table_name')
            show_row_counts=report.get('show_row_counts')
            show_detail_rows= report.get('show_detail_rows')
            show_subtotals= report.get('show_subtotals')
            show_grand_total= report.get('show_grand_total')
            group_by_fields = normalize_group_by(group_by).get("rows", []) + normalize_group_by(group_by).get("columns", [])
            filtered_fields = filter_summary_fields(fields, group_by) if group_by_fields else get_details_fields(fields)


            # Separate computed fields (formula/rollup) from physical fields
            schema = (get_validated_schema(kwargs) or 'public')
            details_fields_raw = get_details_fields(fields)
            physical_details, computed_fields_details, extra_deps_details = process_computed_fields_for_report(details_fields_raw, table_name, schema)

            # Add dependency fields for formula evaluation. Wrap each in
            # dict form so the SELECT builder emits an explicit alias
            # (e.g. invoice_id AS invoice_id) — bare strings can get folded
            # into JOIN/lookup logic and the raw FK never reaches the result
            # row, leaving apply_computed_fields_to_records with no parent_id.
            existing_dep_names = set()
            for f in physical_details:
                if isinstance(f, dict):
                    existing_dep_names.add(f.get("name"))
                    existing_dep_names.add(f.get("alias"))
                else:
                    existing_dep_names.add(f)
            for dep in extra_deps_details:
                if dep not in existing_dep_names:
                    physical_details.append({"name": dep, "alias": dep})
                    existing_dep_names.add(dep)

            # Separate computed filters from physical filters
            computed_base_names = {meta.get("name", k) for k, meta in computed_fields_details.items()}
            all_computed_names = set(computed_fields_details.keys()) | computed_base_names
            filters, computed_filters = separate_computed_filters(filters, all_computed_names, schema, table_name)
            # Convert rollup_summary computed filters into native FK-IN
            # physical predicates up front (one round-trip per rollup filter
            # resolves matching parent IDs). The main detail SELECT then
            # fetches only the rows we actually need, avoiding the over-
            # fetch + Python post-filter that was making the report stall
            # on tables with hundreds of thousands of rows.
            from api.BL.computed_fields import convert_rollup_filters_to_physical
            extra_phys_main, computed_filters = convert_rollup_filters_to_physical(
                computed_filters, table_name, schema,
            )
            if extra_phys_main:
                filters = list(filters) + extra_phys_main

            # Step 3: Fetch all detail records with physical fields only.
            # When group_by.rows is set, apply the limit at the PARENT level
            # (distinct values of the first row-group field) instead of the
            # flattened joined rows — so parent-child reports (e.g. invoice
            # -> line items) don't get truncated mid-parent.
            parent_group_rows = normalize_group_by(group_by).get("rows", [])
            details_filters = list(filters)
            if client_paginating_details:
                details_limit = details_limit_override
                details_offset = details_offset_override
            else:
                details_limit = limit
                details_offset = offset
            # Callers can opt into skipping the detail-row fetch entirely via
            # `skip_details=true` (used by the dashboard widget creator so a
            # 3L-row table doesn't get pulled just to render a chart). The
            # auto-enable heuristic on show_detail_rows=False was removed —
            # the preview page relies on detail rows to render the summary
            # view for some grouped reports, and suppressing them hid the
            # grouped columns from the output.
            skip_details_flag = str(
                self.request.GET.get('skip_details', '')
            ).lower() in ('1', 'true', 'yes')
            skip_details = bool(skip_details_flag)
            # When the client is paginating the detail grid, the UI normally
            # wants a flat paginated view — but the saved-report preview page
            # also sends `details_limit` on the very first load, when the
            # summary cells (including formula/rollup aggregates) still need
            # to be populated. So we still run the parent-keys probe, just
            # without forcing the per-parent IN-filter on the detail fetch:
            # the detail SQL stays paginated as the UI wants, while the
            # summary GROUP BY + computed-aggregate bucketing reuse the same
            # parent_values so the cells line up.
            filter_field = None
            parent_values = []
            parent_keys_result = []
            # Run the parent_keys probe whenever the report is grouped — the
            # paginated parent slice is what scopes the computed-aggregate
            # refetch below. With `full_summary=1` the summary GROUP BY itself
            # runs over the full filtered table, but the formula/rollup
            # bucketing pass still needs the parent IDs of THIS page so the
            # refetch fetches detail rows for the right invoices instead of
            # whatever the first 5000 rows happen to be (which is what was
            # making page 2+ render every aggregate as 0.00).
            if parent_group_rows:
                parent_key_raw = parent_group_rows[0]
                # Rows may be either bare field names or config dicts like
                # {"field": "created_date", "grouping": "day"} — normalize.
                if isinstance(parent_key_raw, dict):
                    parent_key = parent_key_raw.get("field") or parent_key_raw.get("name", "")
                else:
                    parent_key = parent_key_raw
                if "." in parent_key:
                    relation_name = parent_key.split(".", 1)[0]
                    group_field_for_keys = f"{relation_name}_id"
                    filter_field = group_field_for_keys
                    alias = "__parent_fk__"
                else:
                    group_field_for_keys = parent_key
                    filter_field = parent_key
                    alias = "__parent_key__"

                parent_keys_result = get_permissions(
                    self.request,
                    tableName=table_name,
                    fields=[{"name": group_field_for_keys, "alias": alias}],
                    where=filters,
                    group_by=[group_field_for_keys],
                    report=True,
                    limit=limit,
                    offset=offset,
                    **kwargs
                ).get("data", [])
                _lap("parent_keys query")
                parent_values = []
                for row in parent_keys_result:
                    val = row.get(alias)
                    if val is None:
                        val = row.get(group_field_for_keys)
                    if val is not None:
                        parent_values.append(val)
                if parent_values and not client_paginating_details:
                    # Per-parent bucketing for the pivot summary view: scope
                    # the detail fetch to the same parents the summary covers,
                    # bump the limit, and rely on the Python per-parent cap.
                    details_filters.append({
                        "field": filter_field,
                        "operator": "in",
                        "value": parent_values,
                    })
                    details_limit = REPORT_MAX_DETAIL_ROWS
                    details_offset = 0
                elif not parent_values and not client_paginating_details:
                    skip_details = True

            # Ensure parent FK is selected so Python-side per-parent cap can
            # bucket rows correctly; strip it from output if we added it.
            fk_cap_alias = "__cap_parent_fk__"
            fk_injected = False
            details_fields_for_fetch = list(physical_details)
            if parent_group_rows and filter_field and not client_paginating_details:
                existing_names = set()
                for f in details_fields_for_fetch:
                    if isinstance(f, dict):
                        existing_names.add(f.get("name"))
                        existing_names.add(f.get("alias"))
                    else:
                        existing_names.add(f)
                if filter_field not in existing_names and fk_cap_alias not in existing_names:
                    details_fields_for_fetch.append({
                        "name": filter_field,
                        "alias": fk_cap_alias,
                    })
                    fk_injected = True

            details_truncated = False
            if skip_details:
                details_result = []
            else:
                get_kwargs = {}
                if details_limit is not None:
                    get_kwargs["limit"] = details_limit
                    get_kwargs["offset"] = details_offset
                details_result = get_permissions(
                    self.request,
                    tableName=table_name,
                    fields=details_fields_for_fetch,
                    where=details_filters,
                    report=True,
                    **get_kwargs,
                    **kwargs
                ).get("data", [])
                _lap(f"details query ({len(details_result)} rows)")
                if parent_group_rows and filter_field and not client_paginating_details:
                    cap_key = fk_cap_alias if fk_injected else filter_field
                    details_result, details_truncated = _cap_details_per_parent(
                        details_result, cap_key
                    )
                if details_limit is not None and len(details_result) >= details_limit:
                    details_truncated = True
                if fk_injected:
                    for row in details_result:
                        row.pop(fk_cap_alias, None)

            # Compute formula/rollup values
            if computed_fields_details:
                details_result = apply_computed_fields_to_records(details_result, computed_fields_details, table_name, schema)

            # Apply computed field filters. Pass computed_fields_details so
            # the filter can lazily evaluate the field on rows where the
            # earlier compute pass didn't populate it (missing FK, related
            # field not in SELECT, etc.) instead of silently treating None
            # as "doesn't match" and dropping the row.
            if computed_filters:
                details_result = apply_computed_filters(
                    details_result,
                    computed_filters,
                    computed_fields=computed_fields_details,
                    table_name=table_name,
                    schema=schema,
                )

            # Build summary from computed details if group_by exists.
            # Skipped on paginated pages > 0 (client already has it) or when
            # the client opted in with skip_summary=1 (detail-only grid view).
            skip_summary = bool(
                (client_paginating_details and details_offset_override > 0)
                or skip_summary_flag
            )
            # Count is skipped only on paginated pages > 0 — skip_summary_flag
            # doesn't skip it because the DataGrid still needs total_count.
            skip_count = bool(client_paginating_details and details_offset_override > 0)
            # Back-compat name used below.
            skip_summary_and_count = skip_summary
            report_result = details_result
            if group_by_fields and not skip_summary:
                # Resolve formula `formula_expression`s for computed
                # group_by fields so the SQL builder can inline them
                # into SELECT and GROUP BY. Without this, a user
                # pivoting by `tax_amount` (a formula) gets the field
                # silently stripped — the pivot's column-axis buckets
                # are then empty in every cell. Rollups still get
                # stripped (they need correlated subqueries that aren't
                # safe to inline here).
                def _gb_name(g):
                    if isinstance(g, dict):
                        return g.get("field") or g.get("name", "")
                    return g
                from api.BL.dashboards.dashboard import _SQL_FUNCTION_TOKENS as _GB_SQL_TOKENS, _list_table_columns
                import re as _re_gb
                _gb_base_columns = _list_table_columns(table_name, schema)

                def _qualify_and_coalesce_gb(expr, tname, columns):
                    """Inline a formula expression, qualifying each column
                    ref with the base-table name AND wrapping it in
                    `COALESCE(col, 0)`. Without the coalesce, a single
                    NULL operand collapses the entire row's expression to
                    NULL, which is what made the pivot's "Tax Amount"
                    column-axis bucket show "Null" for every group when
                    `tax_percent` was unset on some rows."""
                    if not expr:
                        return expr
                    def _repl(m):
                        ident = m.group(0)
                        if ident.upper() in _GB_SQL_TOKENS:
                            return ident
                        if ident in columns:
                            return f'COALESCE("{tname}"."{ident}", 0)'
                        return ident
                    return _re_gb.sub(r"\b[a-zA-Z_]\w*\b", _repl, expr)

                _resolved = []
                for g in group_by_fields:
                    gname = _gb_name(g)
                    if gname not in all_computed_names:
                        _resolved.append(g)
                        continue
                    meta = computed_fields_details.get(gname) or computed_fields_details.get(gname.split(".")[-1])
                    if not meta and details_fields_raw:
                        meta = next(
                            (m for k, m in (computed_fields_details or {}).items()
                             if (m.get("name") == gname or k == gname)),
                            None,
                        )
                    if meta and meta.get("datatype") == "formula" and meta.get("formula_expression"):
                        expr_sql = _qualify_and_coalesce_gb(
                            meta["formula_expression"], table_name, _gb_base_columns,
                        )
                        new_g = dict(g) if isinstance(g, dict) else {"field": gname}
                        new_g["expression"] = expr_sql
                        _resolved.append(new_g)
                    # else: drop (rollup or unresolved formula).
                group_by_fields = _resolved
                if group_by_fields:
                    # Re-run summary query with physical fields only (no computed)
                    physical_filtered, computed_fields_summary, extra_deps = process_computed_fields_for_report(filtered_fields, table_name, schema)
                    # Re-attach computed group_by fields to the SELECT
                    # list — `process_computed_fields_for_report` strips
                    # them, but the SQL builder needs them in `fields`
                    # so it can emit the formula expression with its
                    # alias and the result row carries the column-axis
                    # value. Without this the pivot's "Tax Amount" /
                    # "Total Amount" headers showed up but every cell
                    # was blank because the inlined GROUP BY clause had
                    # no matching SELECT alias on the row.
                    _existing_pf = set()
                    for _pf in physical_filtered:
                        if isinstance(_pf, dict):
                            _existing_pf.add(_pf.get("name"))
                            _existing_pf.add(_pf.get("alias"))
                        else:
                            _existing_pf.add(_pf)
                    for _g in group_by_fields:
                        if not isinstance(_g, dict) or not _g.get("expression"):
                            continue
                        _gname = _g.get("field") or _g.get("name", "")
                        if not _gname:
                            continue
                        _galias = _gname.replace(".", "_") if "." in _gname else _gname
                        if _galias in _existing_pf:
                            continue
                        # Use the `expression: True` shape so the SELECT
                        # carries the formula SQL directly. Without this,
                        # `get_permissions` strips the synthetic
                        # `{name: "tax_amount"}` entry because
                        # `tax_amount` is classified as a formula column
                        # (no physical column on the base table) — the
                        # SELECT then never includes the column-axis
                        # alias and the pivot's "Tax Amount" header
                        # renders as "Null" for every bucket.
                        physical_filtered.append({
                            "name": _g["expression"],
                            "expression": True,
                            "alias": _galias,
                        })
                    if group_by_fields:
                        physical_filtered.append({
                            "aggregate": "count",
                            "name": "id",
                            "alias": "row_count",
                        })
                    # Scope the summary GROUP BY to the same parent_values the
                    # parent_keys probe picked. Otherwise report_result holds
                    # groups whose detail rows weren't fetched and Python
                    # bucketing emits 0.00 for every row. We do this even when
                    # the client is paginating the detail grid — the detail
                    # SQL itself stays paginated, but the summary buckets must
                    # line up with the parent set so formula aggregates fill.
                    summary_filters_main = list(filters)
                    # Scope the summary GROUP BY to the same parent_values
                    # the probe paginated — UNLESS the caller asked for a
                    # full summary. Without this carve-out, the summary
                    # only counts invoice_items belonging to the first
                    # `limit` parents (e.g. 200), so a 3L-row source
                    # collapses to ~600 rows in the visible GROUP BY and
                    # the user sees absurdly small Row Counts. With
                    # `full_summary=1` we run the GROUP BY against the
                    # full filtered table, so date-buckets reflect every
                    # matching row and Row Count totals to the real
                    # 3L-row count.
                    if parent_group_rows and filter_field and parent_values and not full_summary_flag:
                        summary_filters_main.append({
                            "field": filter_field,
                            "operator": "in",
                            "value": parent_values,
                        })
                    # `FULL_SUMMARY_GROUP_CAP` is a safety ceiling for the
                    # full-summary path (no parent_values clamp). For the
                    # paginated path the parent_values clamp narrows the
                    # GROUP BY to one page worth of parents, so we can
                    # request all matching groups without re-applying
                    # offset (which would skip past everything and emit
                    # an empty page on page 2+).
                    FULL_SUMMARY_GROUP_CAP = 10000
                    summary_call_kwargs = {
                        "tableName": table_name,
                        "fields": physical_filtered,
                        "where": summary_filters_main,
                        "group_by": group_by_fields,
                        "report": True,
                    }
                    if full_summary_flag:
                        # Page through the unscoped GROUP BY using the
                        # URL's limit/offset — only fetch the rows the
                        # user is currently viewing. When the caller
                        # didn't specify a limit, pass None so no LIMIT
                        # clause is emitted and every group is returned
                        # (home dashboard charts rely on this).
                        summary_call_kwargs["limit"] = limit
                        summary_call_kwargs["offset"] = offset or 0
                    elif parent_values:
                        # Cap is bounded by the parent_values slice anyway;
                        # if the caller passed no explicit limit, leave it
                        # unset so SQL returns every group for the parents.
                        if limit is None:
                            summary_call_kwargs["limit"] = None
                        else:
                            summary_call_kwargs["limit"] = max(
                                len(parent_values), limit
                            )
                        summary_call_kwargs["offset"] = 0
                    else:
                        summary_call_kwargs["limit"] = limit
                        summary_call_kwargs["offset"] = offset or 0
                    result = get_permissions(
                        self.request,
                        **summary_call_kwargs,
                        **kwargs,
                    )
                    report_result = result.get("data", [])
                    _lap(f"summary GROUP BY ({len(report_result)} groups, full={full_summary_flag})")

                    # Per-outer-group quota for multi-level groupings.
                    # When the report groups by 2+ fields (e.g. Product
                    # Type → Product), a single global LIMIT applied to
                    # the GROUP BY result truncates the long-tail of one
                    # outer value and starves the others — the chart
                    # ends up with all rows under "Digital" and zero
                    # under "Physical" / "Service". With a limit set,
                    # slice the result so each unique value of the
                    # first group_by field gets up to `limit` rows of
                    # its own.
                    if (
                        limit is not None
                        and isinstance(group_by_fields, list)
                        and len(group_by_fields) >= 2
                        and isinstance(report_result, list)
                        and report_result
                    ):
                        first_g = group_by_fields[0]
                        if isinstance(first_g, dict):
                            first_field = first_g.get("field") or first_g.get("name", "")
                        else:
                            first_field = str(first_g)
                        first_key = first_field.replace(".", "_")
                        if first_key:
                            by_outer = {}
                            outer_order = []
                            for row in report_result:
                                if not isinstance(row, dict):
                                    continue
                                k = row.get(first_key)
                                if k not in by_outer:
                                    by_outer[k] = []
                                    outer_order.append(k)
                                by_outer[k].append(row)
                            sliced = []
                            for k in outer_order:
                                sliced.extend(by_outer[k][:limit])
                            report_result = sliced
                            _lap(f"per-outer-group quota applied ({len(report_result)} rows across {len(outer_order)} groups)")

                    # Merge formula/rollup aggregates into grouped summary rows.
                    # These are not physical columns, so SQL GROUP BY can't aggregate
                    # them — we compute per-group in Python from raw detail values.
                    # Pick up every formula/rollup column whether or not the
                    # saved field carried an explicit aggregate. When it
                    # didn't (the non-aggregate variant the newReport save
                    # flow stores alongside the aggregate one), default to
                    # SUM and write to a `sum_<alias>` key so the frontend's
                    # `${aggregate}_${apiName}` cell lookup finds the value.
                    # filter_summary_fields drops non-aggregate fields, so
                    # we also classify against the full `fields` list to
                    # surface formula/rollup columns it filtered out.
                    _full_details = get_details_fields(fields)
                    _, _full_computed, _ = process_computed_fields_for_report(
                        _full_details, table_name, schema
                    )
                    _merged_computed = dict(computed_fields_summary or {})
                    for _k, _v in (_full_computed or {}).items():
                        if _k not in _merged_computed:
                            _merged_computed[_k] = _v
                    computed_agg_fields = {}
                    for _k, _v in _merged_computed.items():
                        if _v.get("aggregate"):
                            computed_agg_fields[_k] = _v
                            continue
                        if _v.get("datatype") in ("formula", "rollup_summary"):
                            _meta = dict(_v)
                            _meta["aggregate"] = "sum"
                            _base = _v.get("alias") or _k
                            _agg_key = (
                                _base if _base.startswith("sum_") else f"sum_{_base}"
                            )
                            _meta["alias"] = _agg_key
                            computed_agg_fields[_agg_key] = _meta
                    # Skip the full-table refetch when the client is driving
                    # the DataGrid: it doesn't render computed aggregates per
                    # summary row. This block would otherwise pull every row
                    # of the filtered dataset into memory — a 100k+ row stall.
                    if computed_agg_fields and report_result:
                        # Goal: a row-bucket per group in report_result, with
                        # detail rows whose parent FK matches the same set of
                        # parent_values the summary GROUP BY now uses.
                        #
                        # The previously-fetched `details_result` only matches
                        # that scope when the client isn't paginating the
                        # detail grid. With client_paginating_details=True
                        # (e.g. saved-report preview's first load) it's a
                        # paginated slice of the full table, so we'd bucket
                        # the wrong rows. Refetch a parent-scoped slice in
                        # that case — limited and cheap because parent_values
                        # is at most ~100 IDs.
                        scoped_to_parents = (
                            parent_group_rows
                            and filter_field
                            and parent_values
                            and not client_paginating_details
                        )
                        if scoped_to_parents and details_result:
                            all_details = list(details_result)
                            _lap(f"reusing details_result for computed aggregates ({len(all_details)} rows)")
                        else:
                            COMPUTED_AGG_REFETCH_CAP = 5000
                            _lap("starting bounded refetch for computed aggregates")
                            unlimited_kwargs = {k: v for k, v in kwargs.items() if k not in ('limit', 'offset')}
                            agg_where = list(filters)
                            # Scope the agg refetch to the groups visible
                            # on the current summary page. With
                            # `full_summary=1`, parent_values came from an
                            # unbounded probe (or a different ordering)
                            # and won't align with the page slice, so the
                            # bucketing pass would find no matching detail
                            # rows and emit 0.00 in every formula/rollup
                            # cell. Extract the group-key values straight
                            # off `report_result` instead — those ARE the
                            # 50 groups the UI is rendering — and scope
                            # the refetch by them.
                            #
                            # NOT for date-bucket groupings (Month/Year/
                            # etc.): the summary returns TO_CHAR-formatted
                            # strings ("Jan", "Feb", …) which can't be
                            # WHERE-IN'd against a raw `date` column —
                            # Postgres raises "invalid input syntax for
                            # type date". Skip scoping in that case and
                            # let the refetch sweep the filtered set
                            # bounded by COMPUTED_AGG_REFETCH_CAP.
                            first_gb_meta = parent_group_rows[0] if parent_group_rows else None
                            is_date_bucket_group = (
                                isinstance(first_gb_meta, dict)
                                and bool(first_gb_meta.get("grouping"))
                            )
                            applied_scope = False
                            if (
                                full_summary_flag
                                and parent_group_rows
                                and not is_date_bucket_group
                            ):
                                first_gb = parent_group_rows[0]
                                gb_field_full = (
                                    first_gb.get("field") or first_gb.get("name", "")
                                    if isinstance(first_gb, dict) else first_gb
                                )
                                gb_alias = gb_field_full.replace(".", "_") if gb_field_full else ""
                                values_from_summary = []
                                for r in (report_result or []):
                                    if not isinstance(r, dict):
                                        continue
                                    v = r.get(gb_alias) or r.get(gb_field_full)
                                    if v is not None:
                                        values_from_summary.append(v)
                                if values_from_summary and gb_field_full:
                                    agg_where.append({
                                        "field": gb_field_full,
                                        "operator": "in",
                                        "value": values_from_summary,
                                    })
                                    applied_scope = True
                            if (not applied_scope) and parent_group_rows and filter_field and parent_values:
                                agg_where.append({
                                    "field": filter_field,
                                    "operator": "in",
                                    "value": parent_values,
                                })
                            all_details = get_permissions(
                                self.request,
                                tableName=table_name,
                                fields=physical_details,
                                where=agg_where,
                                report=True,
                                limit=COMPUTED_AGG_REFETCH_CAP,
                                **unlimited_kwargs
                            ).get("data", [])
                            if len(all_details) >= COMPUTED_AGG_REFETCH_CAP:
                                details_truncated = True
                            _lap(f"computed-agg refetch ({len(all_details)} rows)")
                            if computed_fields_details:
                                all_details = apply_computed_fields_to_records(
                                    all_details, computed_fields_details, table_name, schema
                                )
                            if computed_filters:
                                all_details = apply_computed_filters(
                                    all_details,
                                    computed_filters,
                                    computed_fields=computed_fields_details,
                                    table_name=table_name,
                                    schema=schema,
                                )

                        def _group_result_key(gb):
                            if isinstance(gb, dict):
                                name = gb.get("field") or gb.get("name") or ""
                            else:
                                name = str(gb)
                            return name.replace(".", "_")

                        # Keys as they appear in report_result / detail rows
                        group_keys = [_group_result_key(g) for g in group_by_fields]
                        # Detect date grouping units (SQL reformats the value on the
                        # grouped side, so direct value matching won't work). In that
                        # case fall back to a global aggregate across all details.
                        has_date_grouping = any(
                            isinstance(g, dict) and (g.get("grouping") or g.get("grouping_unit"))
                            for g in group_by_fields
                        )

                        def _extract_raw(record, meta):
                            # Detail records may hold the value under several
                            # keys depending on how the computed field was
                            # registered. In particular, the agg meta carries
                            # a SUM-prefixed alias ("sum_invoice_grand_total")
                            # while `apply_computed_fields_to_records` stores
                            # the evaluated value under the ORIGINAL alias
                            # ("invoice_grand_total") AND the dotted-name
                            # variant. Try every shape so the bucketing pass
                            # finds the value regardless of how the field was
                            # originally registered.
                            fname = meta.get("name", "")
                            alias = meta.get("alias") or ""
                            candidates = [
                                fname,
                                fname.split(".")[-1] if fname else None,
                                fname.replace(".", "_") if fname else None,
                                alias,
                                alias[len("sum_"):] if alias.startswith("sum_") else None,
                            ]
                            for key in candidates:
                                if key and record.get(key) is not None:
                                    return record.get(key)
                            return None

                        def _apply_agg(values, agg):
                            agg = (agg or "sum").lower()
                            if not values:
                                return 0
                            if agg == "sum":
                                return round(sum(values), 2)
                            if agg == "min":
                                return round(min(values), 2)
                            if agg == "max":
                                return round(max(values), 2)
                            if agg == "count":
                                return len(values)
                            if agg == "avg":
                                return round(sum(values) / len(values), 2)
                            if agg == "median":
                                sv = sorted(values)
                                n = len(sv)
                                mid = n // 2
                                m = sv[mid] if n % 2 else (sv[mid - 1] + sv[mid]) / 2
                                return round(m, 2)
                            return round(sum(values), 2)

                        # Diagnostics: log the keys we have on each side, plus
                        # a sample value for each computed_agg field on a
                        # detail row, plus a sample bucket-key for the first
                        # summary row vs the detail rows. This pins down
                        # whether the 0.00 is from a key mismatch or from
                        # every detail value being None/0.
                        try:
                            sample_detail = all_details[0] if all_details else None
                            sample_summary = report_result[0] if report_result else None
                            sample_agg_values = {}
                            if sample_detail:
                                for _alias, _meta in computed_agg_fields.items():
                                    sample_agg_values[_alias] = {
                                        "name_val": sample_detail.get(_meta.get("name", "")),
                                        "alias_val": sample_detail.get(_alias),
                                        "name_split_val": sample_detail.get(
                                            _meta.get("name", "").split(".")[-1]
                                        ),
                                    }
                            sample_summary_key = (
                                tuple(sample_summary.get(k) for k in group_keys)
                                if sample_summary else None
                            )
                            sample_detail_key = (
                                tuple(sample_detail.get(k) for k in group_keys)
                                if sample_detail else None
                            )
                            print(
                                f"[DEBUG][report] computed_agg group_keys={group_keys} "
                                f"has_date_grouping={has_date_grouping} "
                                f"detail_keys={list(sample_detail.keys()) if sample_detail else None} "
                                f"summary_keys={list(sample_summary.keys()) if sample_summary else None} "
                                f"all_details_count={len(all_details)} report_result_count={len(report_result)} "
                                f"sample_summary_key={sample_summary_key} sample_detail_key={sample_detail_key} "
                                f"sample_agg_values={sample_agg_values} "
                                f"computed_agg_fields_keys={list(computed_agg_fields.keys())}"
                            )
                        except Exception as _dbg_e:
                            print(f"[DEBUG][report] diagnostic print failed: {_dbg_e}")

                        # Build a per-record transform per group key. Date-
                        # grouped fields need the raw timestamp on the detail
                        # row reformatted to match the SQL alias on the
                        # summary side (TO_CHAR(date, 'Mon') etc.) — without
                        # this every grouped row gets the same global agg.
                        from datetime import datetime as _dt
                        _MONTH_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
                        def _grouping_unit_for(g):
                            if isinstance(g, dict):
                                return (g.get("grouping") or g.get("grouping_unit") or "").lower()
                            return ""
                        def _coerce_date_value(val, unit):
                            if val is None:
                                return None
                            d = None
                            if hasattr(val, "year"):
                                d = val
                            elif isinstance(val, str):
                                try:
                                    d = _dt.fromisoformat(val.replace("Z", "+00:00"))
                                except Exception:
                                    try:
                                        d = _dt.strptime(val[:10], "%Y-%m-%d")
                                    except Exception:
                                        return val
                            if d is None:
                                return val
                            # Match the SQL TO_CHAR formats in
                            # `complexGetSql.GROUPING_FORMAT_MAP` so the
                            # detail-side bucket key compares equal to
                            # the summary-side group value. Out-of-sync
                            # formats here mean the bucketing pass finds
                            # no matching detail rows for any summary
                            # group → every formula/rollup cell renders
                            # 0.00 even though the detail values are
                            # correctly evaluated upstream.
                            if unit == "year":
                                return d.strftime("%Y")
                            if unit == "quarter":
                                return f"Q{((d.month - 1) // 3) + 1}-{d.year}"
                            if unit == "month":
                                return f"{_MONTH_ABBR[d.month - 1]}-{d.year}"
                            if unit in ("day", "date"):
                                return d.strftime("%d-%m-%Y")
                            if unit == "hour":
                                return d.strftime("%d-%m-%Y %H")
                            if unit == "minute":
                                return d.strftime("%d-%m-%Y %H:%M")
                            return val
                        grouping_units = [_grouping_unit_for(g) for g in group_by_fields]

                        # Always bucket by group key — even with date grouping
                        # — using the per-key transform so detail rows align
                        # with their summary group.
                        from collections import defaultdict
                        grouped_details = defaultdict(list)
                        for rec in all_details:
                            key_parts = []
                            for idx, k in enumerate(group_keys):
                                v = rec.get(k)
                                unit = grouping_units[idx] if idx < len(grouping_units) else ""
                                if unit:
                                    v = _coerce_date_value(v, unit)
                                key_parts.append(v)
                            grouped_details[tuple(key_parts)].append(rec)
                        if True:
                            # Fallback: if bucketing by group_keys finds no
                            # matches at all (e.g. a JOIN aliasing or dotted-
                            # path mismatch between the summary SQL and the
                            # detail SQL leaves report_result rows looking up
                            # under one key while detail rows expose another),
                            # rebuild the buckets keyed by the parent FK that
                            # both queries share. parent_keys_result holds the
                            # `__parent_key__`/`__parent_fk__` value plus the
                            # group_field_for_keys value, so we can map between
                            # the two.
                            any_match = any(
                                tuple(row.get(k) for k in group_keys) in grouped_details
                                for row in report_result
                            )
                            if (
                                not any_match
                                and parent_group_rows
                                and filter_field
                            ):
                                # Rekey detail rows by their parent FK value.
                                grouped_by_fk = defaultdict(list)
                                for rec in all_details:
                                    fk_val = rec.get(filter_field)
                                    if fk_val is None:
                                        continue
                                    grouped_by_fk[fk_val].append(rec)
                                # Build a map: summary group-value tuple ->
                                # parent FK, using parent_keys_result which
                                # carries both sides for each top-N parent.
                                parent_key_alias = "__parent_fk__" if "." in (
                                    parent_group_rows[0].get("field") or parent_group_rows[0].get("name", "")
                                    if isinstance(parent_group_rows[0], dict) else parent_group_rows[0]
                                ) else "__parent_key__"
                                # Re-fetch the resolved group value for each
                                # parent FK so we can align buckets.
                                summary_value_by_fk = {}
                                for prow in parent_keys_result or []:
                                    fk_val = prow.get(parent_key_alias) or prow.get(filter_field)
                                    if fk_val is None:
                                        continue
                                    # Try to read the resolved group value from
                                    # one of the all_details rows for this FK.
                                    sample = next(
                                        (r for r in all_details if r.get(filter_field) == fk_val),
                                        None,
                                    )
                                    if sample is None:
                                        continue
                                    summary_value_by_fk[fk_val] = tuple(
                                        sample.get(k) for k in group_keys
                                    )
                                # Now rebuild grouped_details keyed by the same
                                # tuple report_result rows use.
                                grouped_details = defaultdict(list)
                                for fk_val, recs in grouped_by_fk.items():
                                    key = summary_value_by_fk.get(fk_val)
                                    if key is None:
                                        continue
                                    grouped_details[key].extend(recs)

                            for row in report_result:
                                key = tuple(row.get(k) for k in group_keys)
                                matching = grouped_details.get(key, [])
                                for alias, meta in computed_agg_fields.items():
                                    values = []
                                    for rec in matching:
                                        raw = _extract_raw(rec, meta)
                                        if raw is None:
                                            continue
                                        try:
                                            values.append(float(raw))
                                        except (TypeError, ValueError):
                                            pass
                                    row[alias] = _apply_agg(values, meta.get("aggregate"))
            # Total row count for the report's filter set (unpaginated). Lets
            # the frontend size its pagination and decide hasMore without
            # waiting for a short last page. Skipped on paginated pages > 0
            # since filters don't change and the client already has it.
            # Always try the direct SQL count first against the physical
            # filter set — `convert_rollup_filters_to_physical` upstream
            # has already pushed rollup predicates down to native FK-IN
            # where possible, so even computed-filter reports get an
            # accurate count. Only when a leftover computed filter
            # remains (formula that couldn't push) do we leave it null
            # rather than report a misleading SQL-only total.
            total_count = None
            if not skip_count:
                total_count = direct_report_count(
                    table_name, filters, get_validated_schema(kwargs)
                )
                if total_count is None:
                    try:
                        count_res = get_permissions(
                            self.request,
                            tableName=table_name,
                            fields=[{"aggregate": "count", "name": "id", "alias": "total"}],
                            where=filters,
                            report=True,
                            **kwargs,
                        )
                        count_rows = count_res.get("data") or []
                        total_count = int((count_rows[0] or {}).get("total") or 0) if count_rows else 0
                    except Exception:
                        total_count = None
                # If a computed filter is still pending (couldn't push
                # to SQL), the count above ignores it. Drop back to
                # null rather than over-report.
                if computed_filters:
                    total_count = None
            _lap(f"count query (total={total_count})")
            # print(f"[report-perf] TOTAL: {(_time_report.perf_counter() - _t_total) * 1000:.1f} ms")

            # Group count for the Summary View pagination — distinct values
            # of the parent group key under the same filter set. Detail rows
            # use total_count above; the summary pagination needs this so
            # "1-50 of 10000" reflects groups, not detail rows.
            group_count = None
            if parent_group_rows and not skip_count:
                parent_key_raw_gc = parent_group_rows[0]
                # When `full_summary=1` is set the summary GROUP BY runs
                # without a row cap, so report_result is the COMPLETE
                # groups list — len() is the truthful group count.
                # Without this, dotted group keys (e.g. invoice.status)
                # fall through to COUNT(DISTINCT invoice_id) which
                # overshoots wildly: 10 distinct statuses but 1L distinct
                # invoice_ids → pagination shows "1-50 of 1L" and pages
                # 2+ render empty. Date-bucketed grouping has the same
                # issue (the original case this branch was added for).
                full_summary_flag_gc = bool(self.request.GET.get('full_summary')) if hasattr(self.request, 'GET') else False
                if full_summary_flag_gc and isinstance(report_result, list):
                    group_count = len(report_result)
                else:
                    if isinstance(parent_key_raw_gc, dict):
                        parent_key_gc = parent_key_raw_gc.get("field") or parent_key_raw_gc.get("name", "")
                    else:
                        parent_key_gc = parent_key_raw_gc
                    if parent_key_gc:
                        if "." in parent_key_gc:
                            gc_field = f"{parent_key_gc.split('.', 1)[0]}_id"
                        else:
                            gc_field = parent_key_gc
                        try:
                            group_count = direct_group_count(
                                table_name, filters, gc_field, get_validated_schema(kwargs)
                            )
                        except Exception as gc_exc:
                            print(f"[report] group_count SQL failed: {gc_exc!r}")
                            group_count = None
                        if computed_filters:
                            group_count = None

            # ── Summary-data fallback ──────────────────────────────────────
            # When `full_summary=1` is set the summary GROUP BY runs without
            # a row cap, so `report_result` is the *complete* groups list
            # and each row carries `row_count` from the SQL count(id) agg.
            # That's enough to derive both totals exactly — covers the case
            # where direct_report_count returned null (dotted-field filters
            # not handled, get_permissions count returned None, etc.).
            if (
                not skip_count
                and parent_group_rows
                and isinstance(report_result, list)
                and report_result
                and isinstance(report_result[0], dict)
                and 'row_count' in report_result[0]
            ):
                full_summary_flag = bool(self.request.GET.get('full_summary')) if hasattr(self.request, 'GET') else False
                if full_summary_flag:
                    if group_count is None:
                        group_count = len(report_result)
                    if total_count is None:
                        try:
                            total_count = sum(
                                int(r.get('row_count') or 0)
                                for r in report_result
                                if isinstance(r, dict)
                            )
                        except (TypeError, ValueError):
                            pass

            return {
                "id": report.get("id"),
                "name": report_name,
                "report_type": report.get("report_type"),
                "fields": fields,
                # Hand the UI the saved-shape filters (filters_raw), not
                # the SQL-normalised IN list. Otherwise editing the
                # report shows hundreds of separate chips for what was
                # one multi-select pill. `filters_raw` already contains
                # every filter the user authored — physical AND
                # computed alike — so we DON'T concatenate
                # `computed_filters` here, since `separate_computed_filters`
                # extracted those FROM `filters_raw`. Concatenating
                # duplicated every computed filter on the edit page.
                "filters": filters_raw,
                "group_by": normalize_group_by(group_by),
                "filter_logic": filter_logic,
                "filter_json": filters_raw,
                "created_at": report.get("created_at"),
                "updated_at": report.get("updated_at"),
                "table_name": table_name,
                "show_row_counts": show_row_counts,
                "show_detail_rows": show_detail_rows,
                "show_subtotals": show_subtotals,
                "show_grand_total": show_grand_total,
                "data": report_result,
                "details": details_result,
                "truncated": details_truncated,
                "total_count": total_count,
                "group_count": group_count,
            }

        elif self.object_name == 'lookup':
            search_term = self.request.GET.get('search')  # Can be None
            owner_id_filter = self.request.GET.get('owner_id')  # Filter records by owner
            exclude_current = self.request.GET.get('exclude_current') == 'true'  # Exclude current user
            filters = []  # Start with an empty Q object
            is_deleted = is_deleted_field_exist(another_object, get_validated_schema(kwargs))
            if search_term:
                filters = [{'field': "name", 'value': f"%{search_term}%", 'operator': 'ilike'}]
            if is_deleted:
                filters.append({'field': 'is_deleted', 'value': False, 'operator': '='})
            if another_object == 'object':
                filters.append({'field': 'setup', 'value': False, 'operator': '='})
            # Hide inactive products from lookup dropdowns
            if another_object == 'product':
                filters.append({'field': 'is_active', 'value': True, 'operator': '='})
            # Filter by owner_id for contacts/leads/accounts lookups
            if owner_id_filter and another_object not in ('users', 'object'):
                filters.append({'field': 'owner_id', 'value': owner_id_filter, 'operator': '='})
            # Exclude the current logged-in user from users lookup
            if another_object == 'users' and exclude_current:
                current_user_id = kwargs.get('user_', {}).get('id')
                if current_user_id:
                    filters.append({'field': 'id', 'value': current_user_id, 'operator': '!='})
            if another_object:
                if another_object in ["campaign"]:
                    filters.append({'field':'is_active','value':True,'operator':"="})
                fields = ['name', 'profile.profile_type','is_active'] if another_object == 'users' else ['name']
                result = get_permissions(
                    self.request,
                    tableName=another_object,
                    where=filters,
                    fields=fields,
                    **kwargs
                )
                if another_object == 'campaign':
                    print(f"[DEBUG] campaign lookup result: {result.get('data', [])}")
                data = result.get('data', [])  # Get data safely
                return data[:30]
            else:
                raise Exception('Invalid data.')
        
        elif self.object_name == 'global_search':
            search_term = self.request.GET.get('search')
            if not search_term:
                return {"error": "Search term is required."}
            
            # Fetch the objects to search through
            objects = get_permissions(self.request, tableName='search_layouts', fields=['search_results_fields', 'object.name', 'object.label', 'object.id', 'object.icon', 'object.icon_color'], order_by=[{'field': 'object.created_date', 'direction': 'ASC'}], **kwargs).get('data', None)

            global_results = {}
            record_counts = {}

            from django.db import close_old_connections
            import threading

            # Define the function to fetch results for an object
            def fetch_results(object):
                close_old_connections()
                tid = threading.get_ident()
                fields = object.get('search_results_fields', None)
                obj = object.get('object')
                tableName=obj.get('name')
                try:
                    if fields:
                        filters = construct_filters(fields, tableName, search_term, **kwargs)
                        filters['and'] = [{'field': 'is_deleted', 'operator': '=', 'value': False}]
                        # Hide inactive products from global search results
                        if tableName == 'product':
                            filters['and'].append({'field': 'is_active', 'operator': '=', 'value': True})
                        profile = get_permissions(self.request, tableName='profile', where=[{'field': 'id', 'value': kwargs.get('profile_id'), 'operator': '='}], **kwargs).get('data')[0]
                        if profile.get('profile_type') != 'admin':
                            filters['and'].append({'field': 'owner_id', 'operator': '=', 'value': kwargs.get('user_', {}).get('id')})
                        result_dicts = get_permissions(self.request, tableName=obj.get('name'), where=filters, limit=5, **kwargs).get('data', [])
                        return obj.get('label'), result_dicts, obj
                except Exception as e:
                    print(f"[T{tid}] ERROR table={tableName} -> {repr(e)}")
                    raise
                finally:
                    try:
                        connection.close()
                    except Exception:
                        pass
            # Use ThreadPoolExecutor for parallel API calls
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(fetch_results, obj): obj for obj in objects}
                for future in as_completed(futures):
                    try:
                        label, result_dicts, obj = future.result()
                        if label and len(result_dicts) > 0:
                            global_results[label] = {
                                "data": result_dicts,
                                "object": obj
                            }
                            record_counts[label] = len(result_dicts)
                    except Exception as e:
                        print(f"Error processing future results: {e}")
            return {
                "search_term": search_term,
                "results": global_results,
                "record_counts": record_counts
            }   

        if another_object == 'preview':
            error_obj = []
            object_details={}
            record_data = {}
            all_columns = []
            sections= []
            buttons= []
            field_items = []
            related_lists =[]
            layout= {}
            related_data = {}
            tasks = []
            attachments=[]
            path_builder_data={}
            history_data=[]
            events=[]
            message = ""

            object_name = self.object_name   
            record_id = self.request.GET.get('id')          
            try: 
                object_details = get_permissions(self.request, tableName='object', where =[{'field': 'name', 'value': object_name, 'operator': '='}], **kwargs).get('data')[0]
            except Exception:
                raise Exception('Object not found.')
            if record_id:
                record_data = get_permissions(
                    self.request,
                    tableName=object_name,
                    id=record_id,
                    **kwargs,
                    where=[{"field": "is_deleted","operator": "=", "value": False}],
                ).get('data', [])
                if not record_data:
                    raise Exception("Record not found.")
                # Check record access: owner, assigned_to, or shared
                profile = get_permissions(self.request, tableName='profile', where=[{'field': 'id', 'value': kwargs.get('profile_id'), 'operator': '='}], **kwargs).get('data', [{}])[0]
                if profile.get('profile_type') != 'admin':
                    user_id = kwargs.get('user_', {}).get('id')
                    record_owner = record_data[0].get('owner_id') if record_data else None
                    assigned_to = record_data[0].get('assigned_to_id') if record_data else None
                    # For events, also check users_id (assigned user)
                    event_assigned = record_data[0].get('users_id') if record_data and object_name in ('event', 'events') else None
                    if record_owner != user_id and assigned_to != user_id and event_assigned != user_id:
                        shared_recs = fetch_shared_records(user_id, object_name, get_validated_schema(kwargs), type='read/write')
                        shared_ids = {str(rec.get('record_id')) for rec in shared_recs}
                        if str(record_id) not in shared_ids:
                            raise Exception("Record not found.")
            try:        
                assigned_layouts = get_permissions(
                    self.request,
                    tableName='layout_assignment',
                    where=[
                        {"field": "object_id", "operator": "=", "value": object_details.get('id')},
                        {"field": "profile_id", "operator": "=", "value":  kwargs.get('profile_id')}
                    ],
                    **kwargs
                ).get('data') 

                page_layout_id = assigned_layouts[0].get('page_layouts_id') if assigned_layouts else None
                if not page_layout_id:
                    return {"error": "No layout assigned for this object."}

                layout_data = get_permissions(
                    self.request,
                    tableName='page_layouts',
                    where=[
                        {"field": "object_name", "operator": "=", "value": object_name},
                        {"field": "id", "operator": "=", "value": page_layout_id}
                    ],
                    **kwargs
                ).get('data')

                if not layout_data:
                    return {"error": "No layout found for this object."}
                layout = layout_data[0]
                sections = layout.get('sections', [])
                buttons = layout.get('buttons', [])
                field_items = layout.get('field_items', [])
                related_lists = layout.get("related_lists", [])
                if not record_id:
                    return {
                        "layout": sections
                    }
                datas, fields_metadata_list = get_field_metadata(object_details.get('id'), "read", **kwargs)
                fields_to_fetch = set()
                for section in sections:
                    fields_to_fetch.update(section.get("fields", []))
                computed_field_names = {
                    col.get('name') for col in (fields_metadata_list or [])
                    if isinstance(col, dict) and col.get('datatype') in ('formula', 'rollup_summary')
                }
                fields_to_fetch -= computed_field_names
                # Convert set to list for passing
                fields_to_fetch = list(fields_to_fetch)
                
                if object_name in ["lead", "leads"]:
                    if not any(str(field_name).lower() == "company" for field_name in fields_to_fetch):
                        fields_to_fetch.append("company")
                if object_name == "task" and "object_id" not in fields_to_fetch:
                    fields_to_fetch.append("object_id")
                if object_name in ["event", "events"]:
                    for required_field in [
                        "master_record_id",
                        "leads_id",
                        "contacts_id",
                        "accounts_id",
                        "subject",
                        "start",
                        "end",
                        "owner_id",
                        "created_by_id",
                    ]:
                        if required_field not in fields_to_fetch:
                            fields_to_fetch.append(required_field)

                # --- Fetch main record data with only required fields ---
                result = get_permissions(
                    self.request,
                    tableName=object_name,
                    id=record_id,
                    fields=fields_to_fetch,
                    **kwargs
                )  
                record_lists = result.get('data', [])
                all_columns = result.get('all_columns', [])
                #Field level permissions
                try:
                    all_columns = field_level_permissions(self.request,object_name,all_columns, **kwargs)
                except Exception as er:
                    print("Field level permission issue",er) 
                    error_obj.append("Field level permissions")
                if object_name == 'task':
                    record_lists = enrich_task_with_related_to(self.request, record_lists, **kwargs)
                record_data = record_lists[0] if record_lists else {}

                # if object is target item 
                # if object_name == "target_item":
                #     target_id = record_data.get("target_id")
                #     assigned_to = None
                #     if target_id:
                #         target_result = get_permissions(
                #             self.request,
                #             tableName="target",
                #             id=target_id,
                #             fields=["users_id"]
                #         ).get("data", [])
                #         if target_result:
                #             user_id = target_result[0].get("users_id")
                #             if user_id:
                #                 user_result = get_permissions(
                #                     self.request,
                #                     tableName="users",
                #                     id=user_id,
                #                     fields=["name"]
                #                 ).get("data", [])
                #                 if user_result:
                #                     assigned_to = user_result[0].get("name")
                #     record_data["assigned_to"] = assigned_to

                if object_name == "target_item":
                    record_data = enrich_target_item_with_assigned_to(self.request, record_data, **kwargs)
                
                # Enrich with owner name if present
                owner_id = record_data.get('owner_id')
                if owner_id:
                    try:
                        owner_info = get_user_details(owner_id)
                        if owner_info:
                            record_data['owner_name'] = owner_info[0]
                    except Exception as e:
                        print(f"[DEBUG] Error fetching owner name: {e}")
            except Exception as er:
                print(er)
                error_obj.append("Layout")

            # record_data = {field: record_dict.get(field) for field in fields_to_fetch}

            # --- Fetch related data ---
            related_data = {}
            try:
                for related in related_lists:
                    related_model_name = related.get("object",{}).get("name", None)
                    if not related_model_name:
                        continue

                    # Special case: field_history_log — fetch via get_field_history
                    # which joins public.users for human-readable name/email.
                    if related_model_name == "field_history_log":
                        history_rows = get_field_history(
                            object_name, record_id, schema=(get_validated_schema(kwargs) or 'public')
                        )
                        history_records = [
                            {
                                "field_name": r[0],
                                "old_value": r[1],
                                "new_value": r[2],
                                "changed_at": r[3],
                                "user_id": r[4],
                                "user": r[5],
                                "email": r[6],
                            }
                            for r in history_rows
                        ]
                        related_data[related_model_name] = {
                            "related_list": related,
                            "data": history_records,
                            "visible_columns": ["field_name", "old_value", "new_value", "changed_at", "user"],
                            "all_columns": [],
                        }
                        continue

                    foreign_key_field = related.get("related_field", {}).get("name", None)
                    if not foreign_key_field:
                        continue
                    where = [{"field": foreign_key_field, "operator": "=", "value": record_id}]
                    related_fields = related.get('fields', [])
                    fields = [field.get('name') for field in related_fields if field.get('visible')]

                    # Separate computed fields for the related object
                    related_schema = (get_validated_schema(kwargs) or 'public')
                    physical_related, computed_related, extra_deps_related = process_computed_fields_for_report(
                        fields, related_model_name, related_schema
                    )
                    for dep in extra_deps_related:
                        if dep not in physical_related:
                            physical_related.append(dep)
                    if 'id' not in physical_related:
                        physical_related.append('id')

                    related_result = get_permissions(
                        self.request,
                        tableName=related_model_name,
                        where=where,
                        fields=physical_related,
                        **kwargs
                    )
                    related_records = related_result.get('data', [])

                    # Compute formula/rollup values for related records
                    if computed_related and related_records:
                        related_records = apply_computed_fields_to_records(
                            related_records, computed_related, related_model_name, related_schema
                        )

                    related_data[related_model_name] = {
                        "related_list": related,
                        "data": related_records,
                        "visible_columns": fields,
                        "all_columns": related_result.get('all_columns', [])
                    }
            except Exception as er:
                print("Related issues",er)
                error_obj.append("Related data")

            # --- Fetch tasks and attachments ---
            try:
                tasks = get_permissions(
                    self.request,
                    tableName='task',
                    fields = ['id', 'assigned_to_id', 'due_date', 'status', 'subject', 'related_to_object_id', 'assigned_to.name', 'created_date', 'last_modified_date', 'created_by_id', 'last_modified_by_id', 'created_by.name', 'last_modified_by.name'],
                    where=[{"field": "related_to_object_id", "operator":"=", "value": record_id},{"field":"is_deleted","operator":"=","value":False}],
                    **kwargs
                ).get('data', [])
            except Exception as e:
                print("Task issues",str(e))
                error_obj.append("Task")
            
            try:
                permissions = get_permissions(
                    self.request, 
                    tableName='object_permissions',
                    fields=["read", "write", "delete", "edit", "view_all","modify_all"],
                    where=[{"field": "object_id", "operator":"=", "value": object_details.get('id')},
                    {"field": "profile_id", "operator":"=", "value": kwargs.get('profile_id')}], 
                    **kwargs).get('data', [])
            except Exception as e:
                print("Permission issues",str(e))
                error_obj.append("Permission")

            try:
                user_id = kwargs.get('user_', {}).get('id')
                if record_id and user_id:
                    all_shared = fetch_shared_records(user_id, object_name, get_validated_schema(kwargs), type='read/write')
                    write_shared = fetch_shared_records(user_id, object_name, get_validated_schema(kwargs), type='write')
                    all_shared_ids = {str(r.get('record_id')) for r in all_shared}
                    write_ids = {str(r.get('record_id')) for r in write_shared}
                    if str(record_id) in all_shared_ids:
                        can_edit = str(record_id) in write_ids  # write bit (2) set = Read/Write
                        if permissions:
                            if not can_edit:
                                permissions[0]['edit'] = False
                            permissions[0]['delete'] = False
                        else:
                            permissions = [{'read': True, 'edit': can_edit, 'delete': False, 'write': can_edit}]
            except Exception as e:
                print(f"Error checking shared record permissions: {e}")
                error_obj.append("Shared record permissions")

            try:
                attachments = get_permissions(
                    self.request,
                    tableName='file',
                    where=[{"field": "record_id", "operator":"=", "value": record_id},
                        {"field": "is_deleted", "operator": "=", "value": False}],
                    **kwargs
                ).get('data', [])
            except Exception as er:
                print("File issues",er)
                error_obj.append("File")

            try:
                related_event_field_map = {
                    "accounts": "accounts_id",
                    "account": "accounts_id",
                    "leads": "leads_id",
                    "lead": "leads_id",
                    "contact": "contacts_id",
                    "contacts": "contacts_id",
                }
                related_event_field = related_event_field_map.get(
                    str(object_name).lower()
                )

                jsonb_event_fields = {"leads_id", "contacts_id"}
                if related_event_field and record_id:
                    if related_event_field in jsonb_event_fields:
                        event_operator = "@>"
                        event_value = json.dumps([record_id])
                    else:
                        event_operator = "="
                        event_value = record_id
                    events = get_permissions(
                        self.request,
                        tableName='event',
                        where=[
                            {
                                "field": related_event_field,
                                "operator": event_operator,
                                "value": event_value,
                            },
                            {"field": "is_deleted", "operator": "=", "value": False},
                        ],
                        **kwargs
                    ).get('data', [])
                else:
                    events = []

                if related_event_field and events and "event" not in related_data:
                    related_data["event"] = {
                        "related_list": {
                            "object": {"name": "event", "label": "Events"},
                            "related_field": {"name": related_event_field},
                            "fields": [
                                {"name": "name", "label": "Event ID", "visible": True},
                                {"name": "subject", "label": "Subject", "visible": True},
                                {"name": "start", "label": "Start", "visible": True},
                                {"name": "end", "label": "End", "visible": True},
                            ],
                        },
                        "data": events,
                        "visible_columns": ["name", "subject", "start", "end"],
                        "all_columns": [],
                    }
            except Exception as er:
                print("Event issues",er)
                error_obj.append("Event")
            #----Telephony config------
            try:
                telephone = get_permissions(
                    self.request,
                    tableName="telephony_config",
                    where=[{"field":"target_object","operator":"=","value":object_details.get('id')}],
                    **kwargs
                ).get("data",[])
                canview = False
                telephony = len(telephone) > 0
                callsettings ={}
                for tele in telephone:
                    target_field = tele.get("target_field",None)
                    if target_field:
                        groups =  get_permissions(self.request,tableName="landing_numbers",where=[{"field":"telephony_id","operator":"=","value":tele.get("id","")}],**kwargs).get("data",[])
                        for group in groups:
                            kwargs['telephony_grp'] = group.get('group_id')
                            canview = user_can_make_call(**kwargs)
                            if canview:
                                callsettings["config"] = tele
                                callsettings["landingnumber"] =group.get('landing_number')
                                callsettings["display_fields"] = tele.get("display_fields")
            except Exception as er:
                print("Telephony config issues",er)     
                error_obj.append("Telephony config")   
            # --- Fetch path builder ---
            try:
                path_builder_data = get_permissions(
                    self.request,
                    tableName='path_builder',
                    where=[{"field": "object_id", "operator": "=", "value": object_details.get("id")}],
                    **kwargs
                ).get("data", [])
                path_builder_data = path_builder_data[0] if path_builder_data else None
            except Exception as er:
                print("Path builder issues",er)
                error_obj.append("Path builder")

            try:
                # --- Fetch field history ---
                field_history_rows = get_field_history(object_name, record_id, schema=(get_validated_schema(kwargs) or 'public'))
                history_data = [
                    {
                        "field_name": row[0],
                        "old_value": row[1],
                        "new_value": row[2],
                        "changed_at": row[3],
                        "user_id": row[4],
                        "user": row[5],
                        "email": row[6],
                    }
                    for row in field_history_rows
                ]
                print(field_history_rows)
                print(history_data)
            except Exception as er:
                print("History issues",er)
                error_obj.append("History")
            # Evaluate roll-up summary fields FIRST so formulas can reference them
            if record_data and record_id:
                try:
                    evaluate_rollup_fields(
                        record_id=record_id,
                        record_data=record_data,
                        parent_object=object_name,
                        schema=(get_validated_schema(kwargs) or 'public'),
                    )
                except Exception as e:
                    print(f"[DEBUG] Rollup fields processing error: {e}")

            # Evaluate formula fields with iterative dependency resolution
            if record_data and all_columns:
                try:
                    formula_fields = [
                        col for col in all_columns
                        if isinstance(col, dict) and col.get('datatype') == 'formula'
                    ]
                    # Iterate up to 5 times so formulas referencing other formulas resolve
                    for _ in range(5):
                        progress = False
                        for formula_col in formula_fields:
                            formula_expr = formula_col.get('formula_expression')
                            fname = formula_col.get('name')
                            if not formula_expr or not fname:
                                continue
                            if record_data.get(fname) is not None:
                                continue
                            try:
                                value = process_formula(formula_expr, fname, record_data)
                                if value is not None:
                                    record_data[fname] = value
                                    progress = True
                            except Exception:
                                pass
                        if not progress:
                            break
                    # Final pass: any still-unresolved formula becomes None
                    for formula_col in formula_fields:
                        fname = formula_col.get('name')
                        if fname and fname not in record_data:
                            record_data[fname] = None
                except Exception as e:
                    print(f"[DEBUG] Formula fields processing error: {e}")

            if error_obj:
                message = f"{', '.join(error_obj)} {'are' if len(error_obj) > 1 else 'is'} getting an error!!"
            has_email = any(
                col.get("datatype") == "email"
                for col in all_columns
                if isinstance(col, dict)
            )
            print(message)
            return {
                "object_metada": {
                    'id': object_details.get('id'),
                    'name': object_details.get('name'),
                    'label': object_details.get('label'),
                    'icon': object_details.get('icon'),
                    'icon_color': object_details.get('icon_color'),
                    "telephony":telephony and canview,
                    "callsettings":callsettings,
                    "has_email": has_email,
                    "permissions": permissions[0] if permissions else {}
                },
                "data": {
                    "id": record_data.get('id'),
                    **record_data
                },
                "all_columns": all_columns,
                "layout": {
                    **layout,
                    "sections": sections,
                    "buttons": buttons,
                    "field_items": field_items,
                    "related_lists": related_lists
                },
                "related_data": related_data,
                "tasks": tasks,
                "attachments": attachments,
                "path_builder": path_builder_data,
                "history": history_data,
                "events": events,
                "message":message
            }        
            
        elif self.object_name == 'whatsapp':
            whatsapp_service = WhatsAppService(self.request, kwargs)
            if another_object == 'chats':          
                return whatsapp_service.chats()  
            elif another_object == 'templates':
                return whatsapp_service.templates()
            elif another_object == 'accounts':                
                return whatsapp_service.accounts()
            elif another_object == 'leads':   
                return whatsapp_service.leads()
            return whatsapp_service.default()
        elif self.object_name == 'email_templates':
                selected_object = self.request.GET.get('object')
                filters = []
                if selected_object:
                    filters = [{"field": "selected_object","operator": "=","value": selected_object}]
                return get_permissions(self.request, tableName="email_templates", where=filters, **kwargs)
        elif self.object_name == 'task':
            if id:
                try:
                    tasks = get_permissions(
                        self.request,
                        tableName='task',
                        id=id,
                        fields = ['assigned_to_id', 'due_date', 'status', 'subject', 'related_to_object_id', 'assigned_to.name', 'created_date', 'last_modified_date', 'created_by_id', 'last_modified_by_id', 'created_by.name', 'last_modified_by.name'],
                        **kwargs
                    ).get('data', [])
                    return tasks
                except Exception as e:
                    print(str(e))
                    raise Exception(str(e))
                
            tasks = get_related_tasks(id=id, **kwargs)
            return tasks      

        elif self.object_name == 'notifications':
            limit = self.request.GET.get("limit",10)
            offset = self.request.GET.get("offset",0)
            result = get_permissions(
                self.request,
                tableName=self.object_name,
                where=[{"field": "owner_id", "operator": "=", "value": kwargs.get("user_").get("id")}],
                order_by=[{"field": "created_at", "direction": "DESC"}],
                limit=limit,
                offset=offset,
                **kwargs
            ).get('data', [])
            return result
        
        if self.object_name == "objects":
            if another_object == "tabs":
                app_ = self.request.GET.get('app', 'sales')
                cache = CacheService()
                result = cache.get(app_, "tabs", get_validated_schema(kwargs))
                if result:
                    return result
                try:
                    apps = get_permissions(self.request, tableName='app', fields=["id", "name", "label", "tabs"], where = [{"field": "name", "operator": "=", "value": app_}], **kwargs).get('data')[0]
                    tabs = apps.get('tabs', [])
                    object_names = [tab.get('name') for tab in tabs if tab.get('type') == 'object']
                    pages = [tab.get('name') for tab in tabs if tab.get('type') == 'page_builder']
                    if not object_names and not pages:
                        return []
                except Exception as e:
                    raise Exception(f'App not found. {e}')
                page_results = []
                object_lookup = {}
                page_lookup = {}
                object_results = []
                if pages:
                    page_results = get_permissions(
                        self.request,
                        tableName='page_builder_assignment',
                        fields=['id', 'page_builder_id', 'page_builder.name'],
                        where=[{"field": "page_builder.name", "operator": "in", "value": pages}, {"field": "profile_id", "operator": "=", "value": kwargs.get('profile_id')}],
                        **kwargs
                    ).get('data')
                    page_lookup = {p.get('page_builder')['name']: p for p in page_results}
                if object_names:
                    # Fetch permissions for objects
                    where = [
                        {"field": "object.name", "operator": "in", "value": object_names},
                        {"field": "profile_id", "operator": "=", "value": kwargs.get('profile_id')},
                        {"field": "type", "operator": "=", "value": 'Default ON'}
                    ]
                    object_results = get_permissions(
                        self.request,
                        tableName='tab_permissions',
                        fields=['object.label', 'object.plural_label', 'object.name', 'object.icon', 'object.icon_color'],
                        where=where,
                        **kwargs
                    ).get('data')
                    object_lookup = {o.get('object')['name']: o for o in object_results}
                combined = []
                for tab in tabs:
                    name = tab.get('name')
                    if tab.get('type') == 'object' and name in object_lookup:
                        combined.append(object_lookup[name])
                    elif tab.get('type') == 'page_builder' and name in page_lookup:
                        combined.append(page_lookup[name])
                    elif tab.get('type') == 'custom_tab':
                        combined.append(tab)
                cache.set(app_, combined, "tabs", get_validated_schema(kwargs))    
                return combined
        elif self.object_name == 'field_mapping':            
            return get_field_mapping(self.request, id, **kwargs)
        elif self.object_name == 'users':
            UserService = UserBussinessLogic(self.request, **kwargs)
            if id is not None:
                return UserService.get_user_by_id(id)
            elif another_object == 'me':
                return UserService.get_me()
            elif another_object == 'firstlogin':
                return UserService.send_welcomenotes(kwargs.get('user_', {}).get('id'),kwargs.get('user_', {}).get('name'))
            return UserService.get_all_users()
        elif self.object_name == 'setup':
            if another_object == 'object': 
                if param3 == 'fields':
                    where = [{'field': 'object_id', "operator": '=', "value": id}]
                    result = get_permissions(self.request, tableName='fields',  where=where, order_by = [{'field': 'name', 'direction': 'ASC'}], **kwargs).get('data')
                    if self.request.GET.get("report_data") and self.request.GET.get("report_data") == "preview":
                        where.append({"field":"profile_id","operator":"=","value":kwargs.get('profile_id')})
                        assigned_layouts = get_permissions(self.request,tableName='layout_assignment',fields=['id','object_id'],where=where,**kwargs).get('data',[])
                        layouts = get_permissions(self.request, tableName='page_layouts',where=[{"field":"object_id","operator":"=","value":assigned_layouts[0].get("object_id")}], **kwargs).get('data', [])
                        if layouts:
                             layout = layouts[0]
                             sections = layout.get('sections', [])
                             field_items = layout.get('field_items', [])
                             fields_in_layout = set()
                             for section in sections:
                                 fields_in_layout.update(section.get('fields', []))
                             for item in field_items:
                                 fields_in_layout.add(item.get('field_name'))
                             result = [field for field in result if field.get("name") in fields_in_layout]

                        # Fetch fields from related/joined tables based on report_type
                        report_type = self.request.GET.get("report_type", "")
                        if " with " in report_type:
                            # Get the base object name from the object_id
                            base_object_data = get_permissions(
                                self.request, tableName='object',
                                where=[{"field": "id", "operator": "=", "value": id}],
                                fields=['name'], **kwargs
                            ).get('data', [])
                            base_object_name = base_object_data[0].get('name') if base_object_data else None

                            if base_object_name:
                                # Parse related table names from report_type: "Invoice Item with Invoice" -> ["invoice"]
                                parts = report_type.split(" with ", 1)
                                related_names = [r.strip().lower().replace(" ", "_") for r in parts[1].split(" and ")]

                                # Get lookup relationships for this base table
                                relationships = get_lookup_relationships(base_object_name, **kwargs)

                                for related_name in related_names:
                                    # Find the matching relationship
                                    matched_rel = None
                                    for rel in relationships:
                                        rel_name = (rel.get('relationship_name') or '').lower()
                                        parent_obj = (rel.get('parent_object') or '').lower()
                                        obj_name = (rel.get('object_name') or '').lower()
                                        if related_name in (rel_name, parent_obj, obj_name):
                                            matched_rel = rel
                                            break

                                    if matched_rel:
                                        # Determine the related table name and relationship prefix
                                        if matched_rel['object_name'].lower() == base_object_name.lower():
                                            related_table = matched_rel['parent_object']
                                            rel_prefix = matched_rel.get('relationship_name') or related_table
                                        else:
                                            related_table = matched_rel['object_name']
                                            rel_prefix = related_table

                                        # Get the object_id of the related table
                                        related_obj = get_permissions(
                                            self.request, tableName='object',
                                            where=[{"field": "name", "operator": "=", "value": related_table}],
                                            fields=['id', 'label'], **kwargs
                                        ).get('data', [])

                                        if related_obj:
                                            related_obj_id = related_obj[0].get('id')
                                            related_obj_label = related_obj[0].get('label', related_table)
                                            # Fetch fields from the related table
                                            related_fields = get_permissions(
                                                self.request, tableName='fields',
                                                where=[{'field': 'object_id', 'operator': '=', 'value': related_obj_id}],
                                                order_by=[{'field': 'name', 'direction': 'ASC'}],
                                                **kwargs
                                            ).get('data', [])

                                            # Prefix each field name with the relationship path
                                            for field in related_fields:
                                                field['name'] = f"{rel_prefix}.{field['name']}"
                                                field['label'] = f"{related_obj_label}: {field.get('label', field['name'])}"
                                                field['relationship_name'] = rel_prefix
                                                field['related_object'] = related_table
                                                result.append(field)

                        return {
                            "fields": result,
                        }
                    return {
                        "fields": result
                    }
                
                elif param3 == 'reports':
                    return get_objects_for_report(self.request, **kwargs)
                elif param3 == 'fieldstracking':                    
                    object_name = self.request.GET.get('object_name')
                    kwargs.pop('object_name', None)
                    return get_field_tracking_data(object_name, **kwargs)                
                result = get_permissions(self.request, tableName='object', where=[{"field": "setup", "operator": "=", "value" : False}], id=id, order_by = [{'field': 'name', 'direction': 'ASC'}], **kwargs).get('data')
                return result            
            elif another_object == 'tables_information':
                search_term = self.request.GET.get('search')
                return get_information_schema(search_table=search_term, **kwargs)                    
            elif another_object == 'workflow':
                if param3 == 'new':
                    return {
                                "workflow": {
                                    "id": "",
                                    "name": "Simple Workflow",
                                    "description": "Triggers email when a new record is created",
                                    "trigger_type": "",
                                    "module_name": ""
                                },
                                "nodes": [
                                    {
                                        "id": "start_1",
                                        "type": "standard",
                                        "node_type": "start",
                                        "label": "Start Node",
                                        "data": {
                                            "label": "Start Node",
                                            "type_name": "Start",
                                            "filters": {
                                            "trigger": "",
                                            "module": "",
                                            "conditions": [
                                                {
                                                "field": {
                                                    "name": "",
                                                    "label": "",
                                                    "datatype": "",
                                                    "pickup_values": "",
                                                },
                                                "operator": "",
                                                "value": "",
                                                },
                                            ],
                                            },
                                        },
                                        "position": { "x": 300, "y": 100 },
                                    }
                                ],
                                "edges": [{ "id": "e_start_action1", "source": "", "target": "" }]
                                }
                workflow = get_permissions(self.request, tableName='workflow', fields=['id','name', 'description', 'trigger_type', 'module_name', 'created_date', 'last_modified_date', 'created_by_id'], id=id, **kwargs).get('data')
                if param3 == 'edit':                    
                    workflow = workflow[0]
                    where = [{"field": "workflow_id", "operator": "=", "value": workflow.get('id')}]
                    nodes = get_permissions(self.request, tableName='workflow_node', fields=['id','label', 'position', 'data', 'workflow_id', 'type', 'node_type'], where=where, **kwargs).get('data')
                    edges = get_permissions(self.request, tableName='workflow_edge',where=where, **kwargs).get('data')
                    for edge in edges:
                        value = edge.get('source_handle', None)
                        edge['sourceHandle'] = value
                        edge.pop('source_handle')
                    return {
                        "workflow": workflow,
                        "nodes": nodes,
                        "edges": edges
                    }                    
                return workflow
            
            elif another_object == 'loginhistory':
                limit = self.request.GET.get('limit', 150)
                offset = self.request.GET.get('offset', 0)
                columns = ['users.name', 'users.email', 'login_time', 'ip_address', 'login_type', 'location', 'platform', 'login_url']
                result = get_permissions(self.request, tableName='user_login_history', fields=columns, limit=limit, offset=offset, **kwargs)
                return result['data']
            
            
            elif another_object == 'apps':
                if param3 == 'check_name':
                    app_name = self.request.GET.get('name') or self.request.GET.get('app_name')
                    if not app_name:
                        return {
                            "exists": False,
                            "message": "App name is required."
                        }
                    existing = get_permissions(
                        self.request,
                        tableName='app',
                        fields=['id'],
                        where={
                            "or": [
                                {"field": "name", "operator": "equals", "value": app_name},
                                {"field": "label", "operator": "equals", "value": app_name}
                            ]
                        },
                        **kwargs
                    ).get('data', [])
                    if existing:
                        return {
                            "exists": True,
                            "message": "App name already exists"
                        }
                    return {
                        "exists": False
                    }
                # if param3 == 'app_users':
                #     app_name = self.request.GET.get('name') or self.request.GET.get('app_name')
                #     if not app_name:
                #         raise Exception("App name is required")
                #     app_id = get_permissions(self.request, tableName='app', where=[{"field": "name", "operator": "equals", "value": app_name}], fields=['id'], **kwargs).get('data', [])
                #     if not app_id:
                #         raise Exception("App ID is required")
                #     app_id = app_id[0].get('id')
                #     app_profiles =  run_query("SELECT profile_id FROM app_permissions WHERE app_id = %s AND access = true", [app_id], **kwargs)
                #     print("App profiles", app_profiles)
                #     users = get_permissions(self.request, tableName='users', fields=['id', 'name', 'username', 'email', 'first_name', 'last_name', 'phone', 'profile_id', 'profile.name', 'profile.profile_type', 'organization_id', 'company','is_active'], where=[{"field": "profile_id", "operator": "in", "value": [ap.get('profile_id') for ap in app_profiles]}], **kwargs).get('data', [])
                #     return users
                # if param3 == 'app_profiles':
                #     app_name = self.request.GET.get('name') or self.request.GET.get('app_name')
                #     if not app_name:
                #         raise Exception("App name is required")
                #     app_id = get_permissions(self.request, tableName='app', where=[{"field": "name", "operator": "equals", "value": app_name}], fields=['id'], **kwargs).get('data', [])
                #     if not app_id:
                #         raise Exception("App ID is required")
                #     app_id = app_id[0].get('id')
                #     app_profiles =  run_query("SELECT profile_id FROM app_permissions WHERE app_id = %s AND access = true", [app_id], **kwargs)
                #     print("App profiles", app_profiles)
                #     profiles = get_permissions(self.request, tableName='profile', fields=['id', 'name', 'profile_type'], where=[{"field": "id", "operator": "in", "value": [ap.get('profile_id') for ap in app_profiles]}], **kwargs).get('data', [])
                #     return profiles
                x = get_permissions(self.request, tableName = 'app_permissions', where = [{'field': 'profile_id', 'operator': '=', 'value': profile_id}, {'field': 'access', 'operator': '=', 'value': True}], 
                    fields = ['app.id', 'app.name', 'app.label', 'app.image', 'app.color', 'app.developer', 'app.last_modified_date', 'app.description','app.is_deleted'], **kwargs).get('data', [])
                result = [res.get("app") for res in x if not res.get("app").get("is_deleted", False)]
                if id:
                    result = get_permissions(self.request, tableName="app", id=id, **kwargs) 
                    # filters = [{"field": "app_id", "operator": "equals", "value": id}]
                    where = [{"field": "app_id", "operator": "=", "value": id}]
                    app_permissions = get_permissions(self.request, tableName='app_permissions', where = where, fields=['profile_id','profile.name','profile.profile_type','app.label', 'access'], **kwargs).get('data')
                    return {
                        "permissions": app_permissions,
                        "app": result.get('data')[0]
                    }
                return result
            
            elif another_object == 'profiles':
                if param3 == 'profile_users':
                    profile_id = self.request.GET.get('id')
                    if not profile_id:
                        raise Exception("Profile ID is required")
                    users = get_permissions(self.request, tableName='users', fields=['id', 'name', 'username', 'email', 'first_name', 'last_name', 'phone', 'profile_id', 'profile.name', 'profile.profile_type', 'organization_id', 'company','is_active'], where=[{"field": "profile_id", "operator": "=", "value": profile_id}], **kwargs).get('data', [])
                    return users
                result = get_permissions(self.request, tableName='profile', id=id, **kwargs) 
                try:
                    schema = (get_validated_schema(kwargs) or 'public')
                    for record in result.get('data', []):
                        with connection.cursor() as cursor:
                            cursor.execute("SET search_path TO %s", [schema])
                            created_by_id = record.get("created_by_id")
                            if created_by_id:
                                cursor.execute("SELECT name FROM users WHERE id = %s", [created_by_id])
                                row = cursor.fetchone()
                                record["created_by"] = row[0] if row else None
                            last_modified_by_id = record.get("last_modified_by_id")
                            if last_modified_by_id:
                                cursor.execute("SELECT name FROM users WHERE id = %s", [last_modified_by_id])
                                row = cursor.fetchone()
                                record["last_modified_by"] = row[0] if row else None
                except Exception as e:
                    pass            
                if id:
                    if param3:
                        where = [{"field": "profile_id", "operator": "=", "value": id},{"field": "object_id", "operator": "=", "value": param3}]
                        fields_permissions = get_permissions(self.request, tableName='field_permissions', where=where, fields=['read_access', 'edit_access', 'fields.name', 'fields.label', 'fields.datatype'],**kwargs )
                        object_details = get_permissions(self.request, tableName='object', id=param3, fields=['name', 'label'], **kwargs).get('data')
                        return {
                            "profile": result['data'],
                            "object": object_details[0],
                            "field_permissions": fields_permissions['data']
                        }
                    where = [{"field": "profile_id", "operator": "=", "value": id}]
                    fields = ['read', 'write', 'edit', 'delete', 'object.name', 'object.label']                    
                    object_permissions = get_permissions(self.request, tableName='object_permissions', fields=fields, where = where, **kwargs)
                    fields_permissions = get_permissions(self.request, tableName='object', where = [{"field": "setup", "operator": "=", "value": False}], fields=['name', 'label'],  **kwargs)
                    tab_permissions = get_permissions(self.request, tableName='tab_permissions', where = where, fields=['object.name','object.label', 'type'], **kwargs)
                    app_permissions = get_permissions(self.request, tableName='app_permissions', where = where, fields=['app.name','app.label', 'access'], **kwargs)
                    layout_permissions = get_permissions(self.request, tableName='layout_assignment', fields = ['profile_id', 'profile.name', 'page_layouts_id', 'page_layouts.name', 'page_layouts.label', 'page_layouts.object_name', 'object_id', 'object.name', 'object.label'], where=where, **kwargs)          
                    homepage_assignment = get_permissions(self.request, tableName='homepage_assignment', fields = ['profile_id', 'profile.name', 'page.id', 'page.name', 'page_id'], where=where, **kwargs)          
                    return {
                        "profile": result['data'],
                        "layout_permissions": layout_permissions['data'],
                        "object_permissions": object_permissions['data'],
                        "field_permissions": fields_permissions['data'],
                        "tab_permissions": tab_permissions['data'],
                        "app_permissions": app_permissions['data'],
                        "homepage_assignment": homepage_assignment['data']
                    }
                else:
                    return result
            elif another_object == 'search_layouts':
                name = self.request.GET.get('name')
                return GetSearchLayouts(self.request, name, **kwargs)                           

            elif another_object == 'dashboard':
                id = self.request.GET.get("id")  # Single dashboard fetch check
                return get_dashboards(self.request, id=id, **kwargs)
            elif another_object == 'page_builder':
                return get_pagebuilder(self.request, id=id, **kwargs)
            elif another_object == "sharing":
                result= get_permissions(self.request, tableName='sharing_records', fields=["access_level", "hierarchy_access", "object.name", "object.label"], **kwargs)
                return result.get('data') 
            
            elif another_object == 'pagelayout':
                return PageLayouts(self.request, **kwargs)  # Call the PageLayouts function defined above/.,
            
            elif another_object == 'layout_assignment':
                object_id = self.request.GET.get('object_id')
                return get_permissions(self.request, tableName='layout_assignment', fields = ['profile_id', 'profile.name', 'page_layouts_id', 'page_layouts.name', 'page_layouts.label'], where = [{"field": "object_id", "operator": "=", "value": object_id}], **kwargs).get('data')

            elif another_object == 'lead_capture':
                result = get_permissions(self.request, tableName='lead_capture', id=id, **kwargs)
                return result.get('data')[0] if id else result.get('data')
                
            elif another_object == 'pathbuilder':
                if param3 == 'check_name':
                    path_name = self.request.GET.get('name') or self.request.GET.get('path_name') or self.request.GET.get('path_builder_name')
                    if not path_name:
                        return {
                            "exists": False,
                            "message": "Path builder name is required."
                        }
                    existing = get_permissions(
                        self.request,
                        tableName='path_builder',
                        fields=['id'],
                        where={
                            "or": [
                                {"field": "name", "operator": "equals", "value": path_name},
                                {"field": "label", "operator": "equals", "value": path_name}
                            ]
                        },
                        **kwargs
                    ).get('data', [])
                    if existing:
                        return {
                            "exists": True,
                            "message": "Path builder name already exists"
                        }
                    return {
                        "exists": False
                    }
                object_id = self.request.GET.get('object_id')
                if object_id:
                    return get_permissions(self.request, tableName='path_builder', where=[{"field": "object_id", "operator": "=", "value": object_id}], **kwargs)
                elif id:
                    return get_permissions(self.request, tableName='path_builder',id=id, **kwargs)
            
            elif another_object == 'usergroup':
                result = get_permissions_with_users(self.request, 'user_group',id=id, **kwargs)                
                return result.get('data')
            
            elif another_object == "usergroupuser":
                result = get_permissions(self.request,tableName='user_group_users',id=id,**kwargs)
                return result

            elif another_object == 'profile':
                result = get_permissions_with_users(self.request, 'profile', id=id, **kwargs)                
                return result.get('data')
            elif another_object == 'target_plan':
                result = get_permissions_with_child_tables(self.request, 'target_plan', id=id, **kwargs)
                return result.get("data")

            
            elif another_object == 'relationships':
                table = self.request.GET.get('object_name')
                if not table:
                    raise Exception("Missing required parameter: object_name")
                return get_object_relationships(table, **kwargs)

            elif another_object == 'recent_report_types':
                # Step 1: Fetch recent reports created/modified by this user
                try:
                    recent_reports = get_permissions(
                        self.request,
                        tableName='report',
                        fields=['report_type', 'created_date'],
                        where=[{"field": "created_by_id", "operator": "=", "value": user_id}],
                        order_by=[{"field": "created_date", "direction": "DESC"}],
                        limit=5,
                        **kwargs
                    ).get("data", [])
                    return recent_reports
                except Exception as e:
                    print(f"Error fetching recent reports: {e}")
                    raise Exception("Could not fetch recent reports.")
        
            elif another_object == "telephony":
                objectId = self.request.GET.get("object_id",None)
                if not objectId:
                    telephony = get_permissions(self.request,
                    tableName="telephony_config",**kwargs)\
                    .get("data",[])
                    for tele in telephony:
                        obj_id = tele.get("target_object",None)
                        if not obj_id:
                            continue
                        page_object = get_permissions(
                            self.request,
                            tableName="object",
                            where=[{"field":"id","operator":"=","value":obj_id}],
                            **kwargs
                        ).get("data",[None])[0]
                        tele["target_object"] = page_object["label"] if page_object else ""
                        tele["objectID"] = page_object["id"]
                elif another_object == "landingnumber":
                    print(**kwargs)
                elif param3 == "groups":
                    groups = get_permissions(self.request,tableName="landing_numbers",fields=['group_id'],**kwargs)                
                    return groups.get("data",[])
                else:
                    telephony = get_permissions(self.request,tableName="telephony_config",where=[{"field":"id","operator": "=","value":objectId}],**kwargs)\
                    .get("data",[None])[0]
                    objects = get_permissions(self.request,tableName="object",where=[{"field":"id","operator":"=","value":telephony['target_object']}],**kwargs).get("data",[])[0]                    
                    telephony['target_object'] = objects['label']
                    telephony['taget_obj_name'] = objects['name']
                    telephony["objectID"] = objects['id']
                    telephony["landing"] = get_permissions(self.request,tableName="landing_numbers",where=[{"field":"telephony_id","operator": "=","value":telephony["id"]}],**kwargs)\
                    .get("data",[{}]) if telephony else {}
                return telephony            
            elif another_object == "telephony_user":
                telephonyuser_id = self.request.GET.get("telephonyuser_id")
                where= []
                if telephonyuser_id:
                    where.append({"field":"user_id","operator":"=","value":telephonyuser_id})
                return get_permissions(self.request,tableName="telephony_user",where=where,**kwargs).get("data",[])

            elif another_object == 'all_report_types':
                object_list = get_permissions(
                    self.request,
                    tableName='object',
                    where=[{"field": "setup", "operator": "=", "value": False}],
                    fields=['name'],
                    **kwargs
                ).get('data', [])
                
                base_objects = [obj['name'] for obj in object_list if obj.get('name')]

                all_report_types = set()

                for base in base_objects:
                    all_report_types.add(base) 
                    # --- CHILD PATHS ---
                    child_paths = find_relationship_paths(base, direction="child", max_depth=3, **kwargs)
                
                    for path in child_paths:
                        if len(path) > 1:
                            label = f"{base} with " + " and ".join(path[1:])
                            all_report_types.add(label)

                    # --- PARENT PATHS ---
                    parent_paths = find_relationship_paths(base, direction="parent", max_depth=3, **kwargs)
                    
                    for path in parent_paths:
                        if len(path) > 1:
                            # Rebuild from base object perspective
                            reversed_path = list(reversed(path))
                            label = f"{base} with " + " and ".join(reversed_path[1:])
                            all_report_types.add(label)
                return sorted(all_report_types)

            #Get the subfolders and dashboards inside a folder
            elif another_object == 'dashboard_folders':
                folder_id = self.request.GET.get('id')

                folders = get_permissions(self.request, tableName='dashboard_folders', **kwargs).get('data', [])
                folder_tree = build_folder_tree(folders, **kwargs)

                if folder_id:
                    # Get subfolders of the current folder
                    subfolders = [f for f in folders if f.get("parent_id") == folder_id]

                    # Get dashboards inside this folder
                    def get_all_fields(table_name, **kwargs):
                        columns_result = get_permissions(
                            self.request,
                            tableName='columns_metadata',
                            where=[{'field': 'table_name', 'operator': '=', 'value': table_name}],
                            **kwargs
                        ).get('data', [])

                        # Safely extract only those with a valid column_name
                        return [col['column_name'] for col in columns_result if 'column_name' in col]

                    
                    
                    dashboards_result = get_permissions(
                        self.request,
                        tableName='dashboard',
                        where=[{"field": "folder_id", "operator": "=", "value": folder_id}],
                        **kwargs
                    )
                    dashboards = dashboards_result.get("data", [])

                    return {
                        "subfolders": subfolders,
                        "dashboards": dashboards
                    }

                else:
                    return folder_tree

            # Get the report sidebar
            elif another_object in ['dashboard_summary', 'reports_summary']:
                return get_reports(self.request, **kwargs)

            # Get the dashboard sidebar
            elif another_object == 'dashboard_sidebar':
                # --- Dashboards ---
                dashboards = {}
                # dashboard_fields = get_all_fields('dashboard', **kwargs)
                
                dashboard_sections = {
                    "recents": {
                        "where": [{"field": "is_deleted", "operator": "=", "value": False}],
                        "order_by": [{"field": "last_modified_date", "direction": "DESC"}],
                        "limit": 15
                    },
                    "created_by_me": {
                        "where": [{"field": "created_by_id", "operator": "=", "value": user_id},
                                    {"field": "is_deleted", "operator": "=", "value": False}],
                        "order_by": None,
                        "limit": None
                    },
                    "all_dashboards": {
                        "where": [{"field": "is_deleted", "operator": "=", "value": False}],
                        "order_by": None,
                        "limit": None
                    }
                }

                # Fetch user data for enrichment
                user_map = {
                    u['id']: u['name'] for u in get_permissions(
                        self.request, tableName='users', fields=['id', 'name'], **kwargs
                    ).get('data', [])
                }

                for key, config in dashboard_sections.items():
                    result = get_permissions(
                        self.request,
                        tableName='dashboard',
                        # fields=dashboard_fields,
                        **({"where": config["where"]} if config["where"] else {}),
                        **({"order_by": config["order_by"]} if config["order_by"] else {}),
                        **({"limit": config["limit"]} if config["limit"] else {}),
                        **kwargs
                    )
                    dashboard_data = result.get("data", [])

                    for dashboard in dashboard_data:
                        dashboard['created_by'] = user_map.get(dashboard.get('created_by_id'), '')
                    dashboards[key] = dashboard_data

                # --- Dashboard Folders ---
                # folder_fields = get_all_fields('dashboard_folders', **kwargs)

                all_folders_flat = get_permissions(
                    self.request,
                    tableName='dashboard_folders',
                    # fields=folder_fields,
                    where=[{"field": "is_deleted", "operator": "=", "value": False}],
                    **kwargs
                ).get('data', [])

                # Enrich folders with `created_by` and `parent_folder_name`
                user_map = {
                    u['id']: u['name'] for u in get_permissions(
                        self.request, tableName='users', fields=['id', 'name'], **kwargs
                    ).get('data', [])
                }
                folder_name_map = {f['id']: f['name'] for f in all_folders_flat}

                for folder in all_folders_flat:
                    folder['created_by'] = user_map.get(folder.get('created_by_id'), '')
                    folder['parent_folder_name'] = folder_name_map.get(folder.get('parent_id'), '')

                # Build the tree structure
                folder_tree = build_folder_tree(all_folders_flat, **kwargs)

                # Filter tree by created_by_id
                def filter_tree_by_creator(tree, user_id, **kwargs):
                    filtered = []
                    for node in tree:
                        if node.get('is_deleted'):
                            continue
                        if node.get('created_by_id') == user_id:
                            filtered.append(node)
                        children = filter_tree_by_creator(node.get('children', []), user_id)
                        if children and node.get('created_by_id') != user_id:
                            node_copy = {**node, 'children': children}
                            filtered.append(node_copy)
                    return filtered

                # Folders shared with the current user/profile
                def get_shared_with_me_folders(user, all_folders_flat, **kwargs):
                    profile_id = user['profile_id']
                    shared_records = get_permissions(
                        self.request,
                        tableName="dashboard_folder_sharing",
                        where=[{
                            "field": "shared_with_id",
                            "operator": "in",
                            "value": [user_id, profile_id]
                        }],
                        **kwargs
                    ).get("data", [])

                    valid_ids = set()
                    for rec in shared_records:
                        if rec["shared_with_type"] == "user" and rec["shared_with_id"] == user_id:
                            valid_ids.add(rec["folder_id"])
                        elif rec["shared_with_type"] == "profile" and rec["shared_with_id"] == profile_id:
                            valid_ids.add(rec["folder_id"])
                    folder_map = {folder["id"]: folder for folder in all_folders_flat}
                    return [folder_map[fid] for fid in valid_ids if fid in folder_map and not folder_map[fid].get("is_deleted")]

                folders = {
                    "all_folders": folder_tree,
                    "created_by_me": filter_tree_by_creator(folder_tree, user_id),
                    "shared_with_me": get_shared_with_me_folders(kwargs.get('user_', {}), all_folders_flat, **kwargs)
                }

                return {
                    "dashboards": dashboards,
                    "folders": folders
                }
            
            elif another_object == 'audit_trail_track':
                return get_permissions(self.request, tableName='audit_trail_track', offset=0, limit=150, **kwargs).get('data', [])            
            elif another_object == 'bin':
                return get_deleted_records(**kwargs)     
            elif another_object == 'users':
                if id is not None:
                    return UserBussinessLogic(self.request, **kwargs).get_user_by_id(id)
                return UserBussinessLogic(self.request, **kwargs).get_all_users()   
            elif another_object == 'target_item':
                return get_permissions(self.request, tableName='target_item', id=id, **kwargs).get('data', [])
            elif another_object == 'email_templates':
                objectname = self.request.GET.get('object_name')
                where = []
                try:
                    objectname = get_permissions(self.request, tableName='object', where=[{"field": "name", "operator": "=", "value": objectname}], fields=['id'], **kwargs).get('data', [])[0].get('id') if objectname else None
                except:
                    pass
                if objectname:
                    return get_permissions(self.request, tableName='email_templates', where=[{"field": "selected_object", "operator": "=", "value": objectname}], **kwargs).get('data', [])  
                data = get_permissions(self.request, tableName=another_object, id=id,fields=['id','name','description','selected_object','available_for_use','template_type','updated_at','subject','body','created_at','author.name'] ,**kwargs).get('data')    
                for emails in data:
                    objectname = emails.get('selected_object') 
                    object_label = get_permissions(self.request, tableName='object', where=[{"field": "id", "operator": "=", "value": objectname}], fields=['label'], **kwargs).get('data', [])[0].get('label') if objectname else None
                    emails['selected_object'] = object_label if object_label else ""
                return data 
            elif another_object == 'telephony_config':
                return get_permissions(self.request, tableName='telephony_config', id=id, **kwargs).get('data', [])
            else:
                return get_permissions(self.request, tableName=another_object, id=id ,**kwargs).get('data')    
        elif self.object_name == 'object':
            setup = self.request.GET.get("setup")
            allObjects = get_permissions(self.request, tableName=self.object_name, where=[{"field": "setup", "operator": "=", "value" : False}], id=id, **kwargs).get('data')       
            if setup == "telephony":
                return [obj for obj in allObjects if get_permissions(self.request,tableName="fields",where=[{"field":"object_id","operator":"=","value":obj['id']},{"field":"datatype","operator":"=","value":"phone"}],**kwargs).get("data")]
            return allObjects
        elif self.object_name == "telephony":
            if another_object == "calllogs":
                objectid = self.request.GET.get("objectid")
                calls = get_permissions(self.request,tableName="call_logs",where=[{"field":"object_id","operator":"=","value":objectid}],**kwargs).get("data")
                return calls
        # Add your GET-specific logic here
        result = get_permissions(self.request, tableName=self.object_name, id=id, **kwargs)
        if result.get('data'):  # ✅ If permission-based retrieval returns data, return it
            return result['data']                   

    #Send notification to specific user
    def send_to_user(self,**kwargs):
        print(kwargs)
        another_object = kwargs.get('another_object') or self.object_name
        user_id = kwargs.get('user_',{}).get("id")
        send_to = kwargs.get("assigned_to_id")
        trigger_notication(
            owner_id=send_to,
            channel_layer=self.channel,
            title=another_object,
            notification_type="alert",
            user_id=user_id,
            channel="push",
            request=self.request,
            **kwargs
        )
    def _handle_shared_record(self, create_data, **kwargs):
        kwargs['setup_check'] = False
        result = post_permission(self.request, self.object_name, create_data=create_data, **kwargs)
        self.send_to_user(
            assigned_to_id=create_data['user_id'],
            message="You have new file received",
            data={
                "id": create_data.get("record_id"),
                "object_name": create_data.get("object_name"),
            },
            **kwargs
        )
        return result
    def post_business_logic(self, data, **kwargs):
            # Add your POST-specific logic here
            another_object = kwargs.get('another_object')
            param3 = kwargs.get('param3')
            create_data = data.get('data')
            referer = kwargs.get("referer")
            user_id = kwargs.get('user_',{}).get("id")

            # kwargs["message"]= f"New {self.object_name} created by user"
            # self.generate_notication(**kwargs)

            if self.object_name == 'leads' and another_object == 'convert':
                # Extract data from payload (handle both wrapped and unwrapped)
                print(f"[DEBUG] Raw data: {data}")
                input_params = create_data if create_data else data
                print(f"[DEBUG] input_params: {input_params}")
                lead_id = input_params.get('lead_id')
                if not lead_id:
                    raise Exception("Lead ID is required for conversion.")
                
                # Fetch Lead Data
                lead_data_list = get_permissions(self.request, tableName='leads', id=lead_id, **kwargs).get('data')
                print(f"[DEBUG] lead_data_list: {lead_data_list}")
                if not lead_data_list or len(lead_data_list) == 0:
                    raise Exception("Lead not found.")
                lead_data = lead_data_list[0]
                print(f"[DEBUG] lead_data: {lead_data}")
                already_converted = (
                    lead_data.get('is_converted') is True
                    or bool(lead_data.get('accounts_id'))
                    or bool(lead_data.get('contact_id'))
                    or bool(lead_data.get('opportunity_id'))
                )
                if already_converted:
                    raise Exception("Lead is already converted.")
                
                # Get names from payload or fallback to lead data
                account_name = input_params.get('account_name') or lead_data.get('name')
                contact_name = input_params.get('contact_name') or lead_data.get('name')
                raw_opportunity_name = input_params.get('opportunity_name')

                raw_create_opportunity = input_params.get('create_opportunity')
                if isinstance(raw_create_opportunity, str):
                    create_opportunity = raw_create_opportunity.strip().lower() in ('true', '1', 'yes', 'on')
                else:
                    create_opportunity = bool(raw_create_opportunity is True)

                opportunity_name = None
                if create_opportunity:
                    opportunity_name = (raw_opportunity_name or lead_data.get('name'))
                
                # Get custom owner and status from payload
                record_owner_id = (
                    input_params.get('record_owner_id')
                    or input_params.get('owner_id')
                    or input_params.get('assigned_to_id')
                    or lead_data.get('owner_id')
                )
                requested_converted_status = str(input_params.get('converted_status') or '').strip()
                if requested_converted_status and requested_converted_status.lower() != 'closed - converted':
                    raise Exception("Converted status must be 'Closed - Converted'.")
                converted_status = "Closed - Converted"
                
                # Calculate end of financial year (March 31st)
                now = datetime.now()
                if now.month > 3:
                    fy_end_year = now.year + 1
                else:
                    fy_end_year = now.year
                close_date = f"{fy_end_year}-03-31"
                print(f"[DEBUG] Calculated close_date: {close_date}")
                
                # Each post_permission/patch_permission call manages its own DB transaction,
                # so we do NOT wrap them in an outer transaction.atomic() to avoid
                # nested-transaction errors ("current transaction is aborted").

                # 1. Create Account
                account_payload = {
                    'name': account_name,
                    'phone': lead_data.get('phone'),
                    'email': lead_data.get('email'),
                    'industry': lead_data.get('industry'),
                    'owner_id': record_owner_id,
                }

                account_result = post_permission(self.request, 'accounts', create_data=account_payload, **kwargs)
                print(f"[DEBUG] account_result: {account_result}")
                if not account_result.get('success'):
                    error_msg = account_result.get('error', {}).get('message', 'Unknown error creating account')
                    raise Exception(f"Failed to create Account: {error_msg}")
                account_record = account_result.get('data', [{}])[0]
                account_id = account_record.get('id')
                print(f"[DEBUG] account_id: {account_id}")

                # 2. Create Contact
                contact_payload = {
                    'name': contact_name,
                    'account_id': account_id,
                    'email': lead_data.get('email'),
                    'phone': lead_data.get('phone'),
                    'salutation': lead_data.get('salutation'),
                    'owner_id': record_owner_id,
                }

                contact_result = post_permission(self.request, 'contact', create_data=contact_payload, **kwargs)
                if not contact_result.get('success'):
                    error_msg = contact_result.get('error', {}).get('message', 'Unknown error creating contact')
                    raise Exception(f"Failed to create Contact: {error_msg}")
                contact_record = contact_result.get('data', [{}])[0]
                contact_id = contact_record.get('id')

                # 3. Create Opportunity (Optional)
                opportunity_id = None
                opportunity_record = None
                if opportunity_name:
                    opportunity_payload = {
                        'name': opportunity_name,
                        'account_name_id': account_id,
                        'contact_id': contact_id,
                        'lead_source': lead_data.get('lead_source'),
                        'close_date': datetime.now(),
                        'owner_id': record_owner_id,
                    }

                    opportunity_result = post_permission(self.request, 'opportunity', create_data=opportunity_payload, **kwargs)
                    if not opportunity_result.get('success'):
                        error_msg = opportunity_result.get('error', {}).get('message', 'Unknown error creating opportunity')
                        raise Exception(f"Failed to create Opportunity: {error_msg}")
                    opportunity_record = opportunity_result.get('data', [{}])[0]
                    opportunity_id = opportunity_record.get('id')

                # 4. Update Lead Status
                updaterec = patch_permission(self.request, 'leads', update_data={
                    "id":lead_id,
                    'owner_id': record_owner_id,
                    'status': converted_status,
                    'is_converted': True,
                    'converted_date': datetime.now(),
                    'accounts_id': account_id,
                    'contact_id': contact_id,
                    'opportunity_id': opportunity_id
                }, **kwargs)
                return {
                    "success": True,
                    "message": "Lead converted successfully.",
                    "data": {
                        "account": account_record,
                        "contact": contact_record,
                        "opportunity": opportunity_record,
                        "lead_id": lead_id
                    }
                }

            elif another_object == 'task':
                try:
                    object_name = self.object_name
                    now = datetime.now()
                    kwargs["assigned_to_id"] = create_data["assigned_to_id"]
                    user_details = get_user_details(user_id, self.request, **kwargs)
                    if user_details:
                        name, _ = user_details
                    else:
                        name = "Unknown"
                    kwargs["message"] = f"New {another_object} is assigned from {name.strip().capitalize() if name else 'Unknown User'}"
                    modified_data = {
                        **create_data,
                        'created_by_id': user_id,
                        'last_modified_by_id': user_id,
                        'created_date': now,
                        'last_modified_date': now,
                    }
                    if create_data.get('app_id'):
                        modified_data['app_id'] = create_data.get('app_id')
                    if not modified_data.get('status'):
                        modified_data['status'] = 'Open'
                    result = post_data_sql('task', modified_data, user=self.request.user, section=self.object_name, enable_lookup_validation=True, **kwargs)
                    kwargs["data"] = result
                    self.send_to_user(**kwargs)
                except Exception as e:
                    print(f"Error in task creation: {e}")
                    raise Exception(str(e))
                return result
                    
            elif self.object_name == 'file':
                file = self.request.FILES.get('file')                
                if not file:
                    raise Exception('Please provide file to upload.')    
                name = file.name
                            
                # Assuming handle_file_upload returns a dictionary
                result = handle_file_upload(file, **kwargs)
                create_data = json.loads(create_data)
                file_path = result.get('file_path', None)
                size = result.get('size')                
                
                if not file_path:
                    raise Exception('Unable to upload file')                   
                modified_data = {
                    **create_data,
                    'type': result.get("type", "Unknown"),
                    'size': size,
                    'name': name,
                    'file_path': file_path,
                    'owner_id': user_id,
                    'created_by_id': user_id
                }                
                response = post_permission(self.request, 'file', create_data=modified_data, **kwargs)
                return response 
            if self.object_name == 'listview':
                list_ =  list(create_data.get('visible_columns') or [])
                if len(list_)<1:
                    list_.append('name')
                    create_data['visible_columns'] = list_     
                filters_ = create_data.get('filters', [])
                filter_logic = create_data.get('filter_logic', '')
                if filter_logic and filter_logic.strip() != "":
                    validation_result = validate_filter_logic(filter_logic, len(filters_))
                    if not validation_result['valid']:
                        raise Exception(f"Invalid filter logic: {validation_result['error']}")
                    
                    # Log warnings if any
                    if validation_result['warnings']:
                        print(f"[WARNING] Filter logic warnings: {validation_result['warnings']}")        
                return post_data_sql('listviews', create_data, section=self.object_name, **kwargs)
            if self.object_name == 'target_item':
                # Get values and convert empty strings to None
                total_target = create_data.get('total_target')
                teams_target = create_data.get('team_target')
                self_target = create_data.get('self_target')
                teams_actual = create_data.get('team_actual')
                self_actual = create_data.get('self_actual')
                total_actual = create_data.get('total_actual')

                # Convert empty strings to None
                if total_target == "":
                    total_target = None
                if teams_target == "":
                    teams_target = None
                if self_target == "":
                    self_target = None
                if teams_actual == "":
                    teams_actual = None
                if self_actual == "":
                    self_actual = None
                if total_actual == "":
                    total_actual = None

                # Default teams_target to 0 if not provided and total_target is provided
                if teams_target is None and total_target is not None:
                    teams_target = 0

                # Calculate self_target if possible
                if total_target is not None and (self_target is None):
                    try:
                        create_data['self_target'] = float(total_target) - float(teams_target)
                    except Exception:
                        create_data['self_target'] = None
                else:
                    create_data['self_target'] = self_target

                # Default teams_actual to 0 if not provided and self_actual or total_actual is provided
                if teams_actual is None and (self_actual is not None or total_actual is not None):
                    teams_actual = 0

                # Calculate total_actual if possible
                if teams_actual is not None and self_actual is not None and (total_actual is None):
                    try:
                        create_data['total_actual'] = float(teams_actual) + float(self_actual)
                    except Exception:
                        create_data['total_actual'] = None
                else:
                    create_data['total_actual'] = total_actual

                # Ensure no empty strings are sent to the DB
                if create_data.get('self_target') == "":
                    create_data['self_target'] = None
                if create_data.get('total_actual') == "":
                    create_data['total_actual'] = None
                return post_permission(self.request, 'target_item', create_data=create_data, **kwargs)            
            elif self.object_name == 'whatsapp':
                whatsapp_service = WhatsAppService(self.request, kwargs)
                contact = self.request.GET.get("contact")
                if another_object == 'template':
                    return whatsapp_service.create_template(create_data)
                elif another_object == 'whatsapp_accounts':
                    return whatsapp_service.create_account(create_data)
                elif another_object == 'campaign': 
                    contacts = data.get('leads', [])
                    template = data.get('template')    
                    if not template and not template["name"]:
                        raise Exception('Please provide template.')
                    message_template = {
                        "type": "template",
                        "template": {
                            "name": template["name"],
                            "language": {
                                "code": template["language"]
                            }
                        }
                    }
                    results = []
                    for contact_ in contacts:
                        phone = contact_['phone'] 
                        name = contact_['name']
                        message_template['name'] = name
                        message_template['to'] = phone                                      
                        results.append(post_whatsapp(contact, message_template, **kwargs))                        
                    return {
                        "results": results
                    }
                elif another_object == 'register':
                    return whatsapp_service.register_account(create_data)
                if not contact:
                    raise Exception('Please login.')
                return post_whatsapp(contact, create_data, **kwargs)


            elif self.object_name == 'setup':
                if another_object == 'object':
                    if param3 == "validate":
                        formula_expression = create_data.get('formula')
                        object_name = create_data.get('module_name')
                        if not formula_expression:
                            raise Exception("Formula expression is required for validation.")
                        if not object_name:
                            raise Exception("Object name is required for validation.")
                        validate_single_formula(
                            module_name=object_name,
                            field_name='formula_field',
                            formula=formula_expression,
                            schema=(get_validated_schema(kwargs) or 'public')
                        )
                        return {"success": True, "message": "Formula expression is valid."}
                    if param3 == 'fields':
                        return create_field(create_data, user=None, section=f"Create - {self.object_name}", **kwargs) 
                    CacheService().invalidate_all_by_table('tabs')                       
                    result = post_customobject(create_data, **kwargs)
                       
                elif another_object == 'apps':     
                    file = self.request.FILES.get('file')  
                    create_data = json.loads(create_data)            
                    if file:      
                        result = handle_file_upload(file, **kwargs)                    
                        file_path = result.get('file_path', None)
                        size = result.get('size')   
                        app_data = create_data.get("app")     
                        create_data["app"] = {
                            **app_data,
                            "image": file_path
                        }               
                    data = get_permissions(self.request, tableName='app', where=[{"field": "name", "operator": "=", "value": create_data.get("app", {}).get("name")}], **kwargs).get('data', [])
                    if data and len(data)>0:
                        raise Exception('App with same name already exists.')                         
                    response = post_permission(self.request, 'app', create_data=create_data, **kwargs)
                    return response          
                                                    
                    # return post_permission(self.request, 'app',  create_data=create_data, **kwargs) 
                elif another_object == 'profile':
                    name = create_data.get('name')
                    profile_id = create_data.get('profile_id')
                    if name and profile_id:
                        return post_permission(self.request, 'profile', new_profile=profile_id, name=name, **kwargs)
                    else:
                        raise Exception('Name or Profile missing')                                    
                    
                elif another_object == 'users':
                    userService = UserBussinessLogic(self.request, **kwargs)
                    return userService.create_user(create_data)            
                elif another_object == 'workflow':
                    if param3 == 'validate':
                        try:
                            validate_single_formula(**create_data, **kwargs)
                            return {"message": "Formula Validated Successfully","success": True}
                        except Exception as e:
                            return {"message": "Formula Validation Failed","success": False, "error": str(e)}
                    try:
                        return create_workflow(self.request, create_data, **kwargs)
                    except Exception as e:
                        raise Exception(str(e))

                elif another_object == 'dashboard_folders':
                    folder_name = create_data.get('name')
                    parent_id = create_data.get('parent_id')
                    filters = {
                        "where": {
                            "and": [
                                {"field": "name", "operator": "=", "value": folder_name},
                                {"field": "parent_id", "operator": "=", "value": parent_id},
                                {"field": "is_deleted", "operator": "=", "value": False}
                            ]
                        }
                    }
                    existing_folders = get_permissions(
                        self.request,
                        tableName='dashboard_folders',
                        where=filters["where"],  # <-- Correct way
                        **kwargs
                    ).get('data', [])

                    print(f"[DEBUG] Existing folders with name '{folder_name}': {existing_folders}")
                    if existing_folders:
                        raise Exception(f"A folder with name '{folder_name}' already exists under this parent.")
                    return post_permission(self.request, 'dashboard_folders', create_data=create_data, setup_check=False, **kwargs)

                elif another_object == 'dashboard_component':
                    # Extract name and type from widget_settings if not already present
                    widget_settings = create_data.get("widget_settings", {})
                    
                    if "name" not in create_data or not create_data["name"]:
                        create_data["name"] = widget_settings.get("widget_name", "Unnamed Widget")
                        
                    if "type" not in create_data or not create_data["type"]:
                        create_data["type"] = widget_settings.get("display_as", "bar")
                    
                    return post_permission(self.request, 'dashboard_component', create_data=create_data,setup_check=False, **kwargs)                    

                elif another_object == 'dashboard':
                    dashboard_data = create_data.copy()
                    dashboard_id = dashboard_data.get("id")  # Needed for edit case

                    widgets = dashboard_data.pop("widgets", [])
                    folder = dashboard_data.pop("folder", {})

                    # Assign folder values to DB fields
                    dashboard_data["folder_id"] = folder.get("id")
                    dashboard_data["folder_name"] = folder.get("name")

                    # Collect widget names or IDs for `components`
                    dashboard_data["components"] = [w.get("name") for w in widgets if w.get("name")]

                    # dashboard_data["components"] = [w.get("id") for w in widgets if w.get("id")]

                    # Collect layout info from widgets
                    layout = {
                        "totalGrids": len(widgets),
                        "canvasSettings": {
                            w["id"]: w["layout"]
                            for w in widgets
                            if "layout" in w
                        }
                    }
                    dashboard_data["layout"] = layout

                    try:
                        if dashboard_id:
                            dashboard_result = patch_permission(
                                self.request, 'dashboard', update_data=dashboard_data, **kwargs
                            )
                            return {
                                "success": True,
                                "message": "Dashboard updated successfully",
                                "data": dashboard_result.get("updated_records", [])
                            }
                        else:
                            # CREATE new dashboard
                            dashboard_result = post_permission(
                                self.request, 'dashboard', create_data=dashboard_data, setup_check=False, **kwargs
                            )
                            # If backend indicates failure, raise specific error
                            if not dashboard_result.get("success", True):
                                error_msg = dashboard_result.get("error") or "Unknown error occurred during dashboard creation."
                                raise Exception(error_msg)
                            return {
                                "success": True,
                                "message": "Dashboard created successfully",
                                "data": dashboard_result["data"]
                            }
                    except Exception as e:
                        raise Exception(f"Dashboard save failed: {str(e)}")

                elif another_object == 'page_builder':
                    page_builder = create_data.get('page_builder', None)
                    components = create_data.get('components')
                    if page_builder is None:
                        raise Exception('Provide dashboard details.')
                    try:
                        page_builder_result = post_permission(self.request, 'page_builder', create_data=page_builder, **kwargs)
                        success = page_builder_result.get('success', False)
                        result_data = page_builder_result.get('data', None)
                        result = {}
                        if success and result_data:
                            page_id = result_data[0].get('id', None)
                            shared_profiles = create_data.get('shared_profiles', None)
                            if shared_profiles:
                                for profile in shared_profiles:
                                    profile['page_builder_id'] = page_id
                                assignment_results = post_permission(self.request, 'page_builder_assignment', create_data = shared_profiles, **kwargs)
                            if page_id:
                                for component in components:
                                    component['page_builder_id'] = page_id
                            else:
                                raise Exception("Invalid Page Builder data or Name already exists.") 
                            if components and page_id:
                                components_result = post_permission(self.request, 'page_component', create_data=components, **kwargs)
                                if not components_result.get('success', False):
                                    raise Exception(f'Error occured while creating components: {components_result.get('error', None)}')      
                            else:
                                raise Exception("Please provide some components.") 
                        else:
                            raise Exception("Invalid Page Builder data or Name already exists.")                     
                        return {
                            "page_builder": result_data[0],
                            "components": components_result.get('data', [])
                        }
                    except Exception as e:
                        raise Exception(f"Error occurred: {e}")
                                    
                elif another_object == "theme":
                    return post_permission(self.request, another_object, create_data=create_data, **kwargs)
                               
                elif another_object == "pagelayout":
                    layout = create_data.get("layout", {})
                    object_name = layout.get("object_name")
                    page_layout_name = layout.get("name")
                    label = layout.get("label")
                    id = layout.get("id", None)
                    related_lists = layout.get('relatedLists')
                    buttons = layout.get('buttons')
                    sections = layout.get('sections')                    
                    
                    all_selected_fields = []
                    for section in sections:
                        selected_fields = []
                        fields = section.get('fields', [])
                        for field in fields:
                            name = field.get('name', "unknown")
                            selected_fields.append(name)
                            all_selected_fields.append(name)
                        section['fields'] = selected_fields

                    # Validation: Ensure all mandatory fields are present
                    where_required = [
                        {"field": "object_name", "operator": "=", "value": object_name},
                        {"field": "required", "operator": "=", "value": True}
                    ]
                    required_fields_data = get_permissions(self.request, tableName='fields', where=where_required, fields=['name', 'label'], **kwargs).get('data', [])
                    
                    missing_fields = []
                    for rf in required_fields_data:
                        if rf.get('name') not in all_selected_fields:
                            missing_fields.append(rf.get('label'))
                    
                    if missing_fields:
                        raise Exception(f"The following mandatory fields are missing from the layout: {', '.join(missing_fields)}.")
                    
                    if not object_name or not page_layout_name:
                        return {"error": "Object Name and Name are required."}   
                    
                    upload_data = {
                        "related_lists": related_lists,
                        "buttons": buttons,
                        "sections": sections,
                        "name": page_layout_name,
                        "label":label,
                        "object_name": object_name,
                    }   
                    
                    response_data = {
                        "message": "Page Layout created successfully.",
                        "id": id,
                        "name": page_layout_name, 
                        "label": label,                                               
                        "layout": {
                            "sections": layout.get("sections", []),
                            "relatedLists": layout.get("relatedLists", []),
                            "buttons": layout.get("buttons", [])
                        }
                    }            
                    try:
                        if id:
                            upload_data['id'] = id
                            upload_data['last_modified_date'] = datetime.now()
                            upload_data['last_modified_by'] = user_id
                            result = patch_permission(self.request, "page_layouts", update_data=upload_data, **kwargs)
                            if result.get("success"):
                                return {
                                    **response_data,
                                    "message": "Page Layout updated successfully."
                                }
                            else:
                                return result   
                        else:
                            upload_data['created_by'] = user_id
                            result = post_permission(self.request, "page_layouts", create_data=upload_data, **kwargs)
                            if result.get("success"):
                                updated_record = result.get("data")[0]
                                return {
                                    **response_data,
                                    "id": updated_record.get('id')
                                }       
                            else:
                                return result       
                    except Exception as e:
                        return {"error": f"Database error: {str(e)}"}                       
                elif another_object == "pathbuilder":
                    return post_permission(self.request, 'path_builder', create_data=create_data, **kwargs)
                
                elif another_object == "usergroup":
                    return post_permission(self.request, "user_group", create_data=create_data, **kwargs)
                
                elif another_object == 'campaign' :
                    return post_permission(self.request, 'campaign', create_data=create_data, **kwargs)

                elif another_object == 'target_plan':
                    return post_permission(self.request, 'target_plan', create_data=create_data, **kwargs)                

                elif another_object in ['dashboard_folder_sharing', 'report_folder_sharing']:
                    shared_with_ids = create_data.get('shared_with_id')
                    if not shared_with_ids:
                        raise Exception("shared_with_id is required.")

                    # Ensure shared_with_ids is a list
                    if not isinstance(shared_with_ids, list):
                        shared_with_ids = [shared_with_ids]

                    responses = []
                    for shared_id in shared_with_ids:
                        new_data = {
                            **create_data,
                            "shared_with_id": shared_id
                        }
                        res = post_permission(self.request, another_object, create_data=new_data,setup_check=False, **kwargs)
                        responses.append(res)
                        kwargs['assigned_to_id'] = shared_id
                        kwargs['message'] = "You have new folder received"
                        url_object_name = "dashboard" if another_object == "dashboard_folder_sharing" else "reports"
                        kwargs['data'] = {"object_name": url_object_name}
                        self.send_to_user(**kwargs)
                    return {"success": True, "shared_records": responses}

                elif another_object == 'lead_capture':
                    page_id = create_data.get('lead_page_id')
                    pageAccessToken = data.get('page_access_token')
                    if not page_id and not pageAccessToken:
                        raise Exception('Please provide a lead form and Page Access Token.')
                    register_facebook_webhook(page_id, 'https://auth.bussus.com/api/facebook/leadcapture/', pageAccessToken)
                    long_lived_page_access_token = get_long_lived_page_token(pageAccessToken)
                    create_data['page_access_token'] = long_lived_page_access_token                                       
                    return post_permission(self.request, 'lead_capture', create_data=create_data, **kwargs)
                
                elif another_object == 'restore':
                    create_data = data.get("data", {})
                    records = create_data.get("records", [])
                    return restore_soft_deleted_records(records, **kwargs)
                elif another_object == 'emailtemplate':
                    if not create_data:
                        raise Exception('Please provide details.')
                    create_data['author_id'] = user_id
                    return post_permission(self.request, 'email_templates', create_data=create_data, **kwargs)

                elif another_object == 'verify_merge_fields':
                    create_data = data.get('data', {})
                    print("Verifying merge fields with data:", create_data)
                    result = send_test_email(self.request, data=create_data, **kwargs)
                    print("Merge field verification result:", result)
                    if isinstance(result, dict) and "authurl" in result:
                        return {
                            "success": True,
                            "status": "ok",
                            "result": result
                        }
                    else:
                        return {
                            "success": True, "status": "ok", "result": result
                            }
                elif another_object == 'email_provider':
                    user_id = self.request.user.id
                    provider = create_data.get("provider")
                    # Check if record exists
                    existing = run_query("SELECT id FROM email_provider_setup WHERE user_id = %s", [user_id])
                    
                    if existing:
                        # Update the provider
                        run_query(
                            "UPDATE email_provider_setup SET provider = %s, updated_at = NOW() WHERE user_id = %s",
                            [provider, user_id]
                        )
                        return {"success": True, "message": "Provider updated"}
                    else:
                        # Insert new provider
                        run_query(
                            """
                            INSERT INTO email_provider_setup (id, user_id, provider)
                            VALUES (CONCAT('eprov_', LEFT(gen_random_uuid()::text, 12)), %s, %s)
                            """,
                            [user_id, provider]
                        )
                        return {"success": True, "message": "Provider saved"}                
                elif another_object == 'config':
                    if param3 == "landingnumber":
                        result = post_data_sql(
                            'landing_numbers',
                            create_data,
                            user=self.request.user,
                            section='telephony',
                            **kwargs,
                        )
                        return result
                    elif param3 == "landingnumber":
                        # reuse post_data_sql logic or specific update logic if needed
                        # assuming update, we use patch_permission or similar
                        pass  # handled in patch_business_logic now
                    landing_numbers = create_data.pop('landing_numbers', [])

                    existing = get_permissions(
                        request=self.request,
                        tableName="telephony_config",
                        where=[
                            {"field": "authtoken", "operator": "=", "value": create_data["authtoken"]},
                            {"field": "sid", "operator": "=", "value": create_data["sid"]},
                        ],
                        **kwargs,
                    ).get("data")

                    if existing:
                        raise Exception("This config already reported!!")
                    object_exist = get_permissions(
                        request=self.request,
                        tableName="telephony_config",
                        where=[
                            {
                                "field": "target_object",
                                "operator": "=",
                                "value": create_data["target_object"],
                            }
                        ],
                        **kwargs,
                    ).get("data") or []
                    used_group_ids = set()

                    for obj in object_exist:
                        landing_exist = get_permissions(
                            request=self.request,
                            tableName="landing_numbers",
                            where=[
                                {
                                    "field": "telephony_id",
                                    "operator": "=",
                                    "value": obj["id"],
                                }
                            ],
                            field=["group_id"],
                            **kwargs,
                        ).get("data") or []

                        for row in landing_exist:
                            gid = row.get("group_id")
                            if gid:
                                used_group_ids.add(gid)
                    result = post_data_sql(
                        "telephony_config",
                        create_data,
                        user=self.request.user,
                        section="telephony",
                        **kwargs,
                    )
                    config_id = result["data"][0]["id"]
                    new_group_ids = set()
                    for landing in landing_numbers:
                        group_id = landing.get("group_id")
                        if group_id in new_group_ids:
                            raise Exception("Duplicate group in landing_numbers payload!!")
                        new_group_ids.add(group_id)
                        if not group_id:
                            raise Exception("Landing number missing group_id")
                        if group_id in used_group_ids:
                            raise Exception("This group is already configured for this object!!")

                        # Attach this config id
                        landing["telephony_id"] = config_id

                        post_data_sql(
                            "landing_numbers",
                            landing,
                            user=self.request.user,
                            section="telephony",
                            **kwargs,
                        )
                    return result
            
                elif another_object == 'report':
                    if param3 == 'preview':
                        print("Creating report with data:", create_data)
                        # Use the payload directly
                        fields = create_data.get('fields', [])
                        filters = create_data.get('filters', [])
                        # Multi-select filter UIs sometimes encode "any of N
                        # values" as a single ILIKE with the values joined by
                        # commas (e.g. invoice_id ILIKE '%a,b,c,...%'). On a
                        # 3L-row table that's a sequential scan with no
                        # match — and turns the edit-report preview into a
                        # multi-second hang. Normalise to a real IN list so
                        # Postgres can use the column's index.
                        filters = _normalize_csv_ilike_filters(filters)
                        group_by = create_data.get('group_by', [])
                        order_by = create_data.get('order_by', [])
                        filter_logic = create_data.get('filter_logic')
                        table_name = create_data.get('table_name')
                        show_row_counts = create_data.get('show_row_counts')
                        show_detail_rows = create_data.get('show_detail_rows')
                        show_subtotals = create_data.get('show_subtotals')
                        show_grand_total = create_data.get('show_grand_total')
                        # Detail-grid pagination. When the client supplies
                        # details_limit, treat it as explicit pagination and
                        # bypass the default preview ceilings + per-parent cap.
                        raw_details_limit = create_data.get('details_limit')
                        raw_details_offset = create_data.get('details_offset')
                        client_paginating_details = raw_details_limit is not None
                        try:
                            details_limit_override = int(raw_details_limit) if raw_details_limit is not None else None
                        except (TypeError, ValueError):
                            details_limit_override = None
                            client_paginating_details = False
                        try:
                            details_offset_override = int(raw_details_offset) if raw_details_offset is not None else 0
                        except (TypeError, ValueError):
                            details_offset_override = 0
                        # Opt-in: skip the expensive summary GROUP BY when the
                        # UI is only rendering the flat detail grid. Huge-
                        # object saver — the summary query scans every row.
                        skip_summary_flag = bool(create_data.get('skip_summary'))
                        skip_count_flag = bool(create_data.get('skip_count'))
                        # Filter only string fields for summary/group by
                        group_by_norm = normalize_group_by(group_by)
                        group_by_fields = group_by_norm.get("rows", []) + group_by_norm.get("columns", [])
                        filtered_fields = filter_summary_fields(fields, group_by) if group_by_fields else get_details_fields(fields)

                        # Separate computed fields (formula/rollup) from physical fields
                        schema = (get_validated_schema(kwargs) or 'public')
                        details_fields = get_details_fields(fields)
                        physical_details, computed_fields_details, extra_deps_details = process_computed_fields_for_report(details_fields, table_name, schema)

                        # Wrap extra deps in dict form so the SELECT builder
                        # emits an explicit alias (e.g. invoice_id AS invoice_id).
                        # Bare strings can get folded into JOIN/lookup logic and
                        # the raw FK column never makes it into the result row,
                        # which means apply_computed_fields_to_records can't
                        # find parent_id and the rollup stays None.
                        existing_names = set()
                        for f in physical_details:
                            if isinstance(f, dict):
                                existing_names.add(f.get("name"))
                                existing_names.add(f.get("alias"))
                            else:
                                existing_names.add(f)
                        for dep in extra_deps_details:
                            if dep not in existing_names:
                                physical_details.append({"name": dep, "alias": dep})
                                existing_names.add(dep)

                        # Separate computed filters
                        computed_base_names = {meta.get("name", k) for k, meta in computed_fields_details.items()}
                        all_computed = set(computed_fields_details.keys()) | computed_base_names
                        filters, computed_filters_preview = separate_computed_filters(filters, all_computed, schema, table_name)

                        # Convert rollup_summary computed filters into native
                        # FK-IN physical predicates UP FRONT — one SQL roundtrip
                        # per rollup filter resolves matching parent IDs, and
                        # the main detail SELECT then only fetches the rows we
                        # actually need (no 5000-row over-fetch + Python pass).
                        from api.BL.computed_fields import convert_rollup_filters_to_physical
                        extra_phys, computed_filters_preview = convert_rollup_filters_to_physical(
                            computed_filters_preview, table_name, schema,
                        )
                        if extra_phys:
                            filters = list(filters) + extra_phys

                        profile = get_permissions(self.request, tableName='profile', where=[{'field': 'id', 'value': kwargs.get('profile_id'), 'operator': '='}], **kwargs).get('data')[0]
                        filters.append({
                                "field": "is_deleted",
                                "operator": "=",
                                "value": False
                        })
                        if profile.get('profile_type') != 'admin':
                            filters.append({'field': 'owner_id', 'value': kwargs.get('user_', {}).get('id'), 'operator': '='})

                        # Fetch all detail records.
                        # If group_by.rows is set, apply the 20-row limit at the
                        # PARENT level (distinct values of the first row-group
                        # field) instead of on the flattened joined rows — so
                        # parent-child previews (e.g. invoice -> line items)
                        # don't get truncated mid-parent.
                        parent_group_rows = group_by_norm.get("rows", []) if group_by_fields else []
                        details_filters = list(filters)
                        if client_paginating_details:
                            details_limit = details_limit_override
                            details_offset = details_offset_override
                        else:
                            details_limit = 20
                            details_offset = 0
                        # Flat pagination: skip parent-scoping when client is
                        # driving the detail grid — the UI wants all rows, not
                        # a 20-parent slice.
                        filter_field = None
                        # The preview UI only consumes detail rows when the
                        # "Detail Rows" toggle is on. With it off, `previewData`
                        # (summary) drives the table render and `detailData`
                        # is unused. We still run parent_keys when grouping is
                        # set so the summary GROUP BY is scoped to the same
                        # 20-parent slice as the visible preview — running an
                        # unscoped GROUP BY against a 3L-row table is what was
                        # making the toggle hang.
                        # Detail Rows OFF used to short-circuit the detail
                        # SELECT, but the formula/rollup-aggregate bucketing
                        # below depends on those rows being available with
                        # computed values populated. Without them the summary
                        # cells (Sum/Min/Max of <formula>) render 0.00. We
                        # already cap the parent slice to 20 invoices, so the
                        # detail fetch is bounded to ~60 rows — no longer
                        # "wasted work" on lakh-scale tables.
                        skip_details_preview = False
                        # Always run parent_keys for grouped reports — even
                        # when client_paginating_details=True. The detail
                        # SQL stays paginated as the client wants, but the
                        # summary GROUP BY + computed-aggregate refetch use
                        # parent_values to align scoping. Without this the
                        # Summary view's formula/rollup cells render 0.00.
                        # When the group_by entry uses a date-bucket
                        # (grouping=Month/Year/Day/Quarter), the parent_keys
                        # probe — which groups by the underlying FK or raw
                        # field — misrepresents the parent set: each
                        # distinct invoice becomes a "parent" instead of
                        # each distinct month. The detail rows then render
                        # under raw-date headers (2024-01-22 (3)) rather
                        # than the configured month buckets. Skip the
                        # probe in that case and rely on the summary
                        # GROUP BY to bucket dates correctly.
                        date_bucket_group = (
                            isinstance(parent_group_rows[0] if parent_group_rows else None, dict)
                            and bool((parent_group_rows[0] or {}).get("grouping"))
                        )
                        if parent_group_rows and not date_bucket_group:
                            parent_key_raw = parent_group_rows[0]
                            # Rows may be either bare field names ("invoice.name")
                            # or config dicts ({"field": "created_date",
                            # "grouping": "day"}). Normalize to the field name.
                            if isinstance(parent_key_raw, dict):
                                parent_key = parent_key_raw.get("field") or parent_key_raw.get("name", "")
                            else:
                                parent_key = parent_key_raw
                            # If the group-by references a related object
                            # (e.g. "invoice.name" on table "invoice_item"),
                            # filter children by the FK column on the base
                            # table (e.g. "invoice_id") — this is reliable
                            # with the where builder, unlike dotted paths.
                            if "." in parent_key:
                                relation_name = parent_key.split(".", 1)[0]
                                fk_field = f"{relation_name}_id"
                                group_field_for_keys = fk_field
                                filter_field = fk_field
                                alias = "__parent_fk__"
                            else:
                                group_field_for_keys = parent_key
                                filter_field = parent_key
                                alias = "__parent_key__"

                            parent_keys_result = get_permissions(
                                self.request,
                                tableName=table_name,
                                fields=[{"name": group_field_for_keys, "alias": alias}],
                                where=filters,
                                group_by=[group_field_for_keys],
                                report=True,
                                order_by=order_by,
                                limit=20,
                                offset=0,
                                **kwargs
                            ).get("data", [])
                            parent_values = []
                            for row in parent_keys_result:
                                val = row.get(alias)
                                if val is None:
                                    val = row.get(group_field_for_keys)
                                if val is not None:
                                    parent_values.append(val)
                            # Only scope the DETAIL fetch to parent_values when
                            # the client isn't running its own pagination.
                            # `parent_values` is still kept around so the
                            # summary GROUP BY and the computed-aggregate
                            # refetch can align scoping in either case.
                            #
                            # IMPORTANT: when there are unresolved computed
                            # filters (formula/rollup predicates that have
                            # to run in Python), parent_keys was picked
                            # WITHOUT seeing them — so those 20 parents
                            # are not the right slice. Skip parent-scoping
                            # in that case and rely on the COMPUTED_FILTER
                            # over-fetch to sweep a wider sample of the
                            # table; otherwise lakh-scale parents with very
                            # few matches would surface zero records.
                            if computed_filters_preview and not client_paginating_details:
                                details_limit = REPORT_MAX_DETAIL_ROWS
                                details_offset = 0
                            elif parent_values and not client_paginating_details:
                                details_filters.append({
                                    "field": filter_field,
                                    "operator": "in",
                                    "value": parent_values,
                                })
                                details_limit = 20
                                details_offset = 0
                            elif not parent_values and not client_paginating_details:
                                details_filters = None

                        # Ensure the parent FK is selected so we can cap per-parent
                        # in Python. It won't be in physical_details unless the
                        # user explicitly added it. Track whether we injected it
                        # so we can strip it from the response rows after trimming.
                        fk_cap_alias = "__cap_parent_fk__"
                        fk_injected = False
                        details_fields_for_fetch = list(physical_details)
                        if parent_group_rows and filter_field and not client_paginating_details:
                            existing_names = set()
                            for f in details_fields_for_fetch:
                                if isinstance(f, dict):
                                    existing_names.add(f.get("name"))
                                    existing_names.add(f.get("alias"))
                                else:
                                    existing_names.add(f)
                            if filter_field not in existing_names and fk_cap_alias not in existing_names:
                                details_fields_for_fetch.append({
                                    "name": filter_field,
                                    "alias": fk_cap_alias,
                                })
                                fk_injected = True

                        details_truncated = False
                        # When the UI has Detail Rows turned off, the detail
                        # fetch is wasted work — `previewData` (summary) drives
                        # the table render. Skip the SQL but keep the parent_keys
                        # filter we already added to `details_filters` so the
                        # summary GROUP BY below stays scoped to the same 20
                        # parents (avoiding a 3L-row unscoped scan).
                        pre_filter_fetch_count_pv = 0
                        effective_limit = None
                        post_computed_filter_count_pv = None
                        # Default the requested page size — defined here so
                        # the post-Python-filter trim block can reference it
                        # even when the SQL fetch branch is skipped (Detail
                        # Rows OFF / details_filters None).
                        requested_limit = details_limit
                        if details_filters is None or skip_details_preview:
                            details_result = []
                        else:
                            get_kwargs = {}
                            # When the filter pushed down to SQL (no entries
                            # left in `computed_filters_preview`), the WHERE
                            # clause is already running against the whole 1L
                            # table — fetch exactly `details_limit` rows and
                            # we're done.
                            #
                            # When the filter HAS to run in Python (formula
                            # uses functions/string ops we can't inline),
                            # over-fetch a wider sample so the post-Python
                            # trim still has 20 matches to surface. Without
                            # the over-fetch, "apply filter to 20 then trim"
                            # is what produces the "fewer than 20 visible"
                            # behaviour the user just flagged.
                            COMPUTED_FILTER_FETCH_CAP = 5000
                            if computed_filters_preview and details_limit is not None:
                                effective_limit = max(details_limit, COMPUTED_FILTER_FETCH_CAP)
                            else:
                                effective_limit = details_limit
                            if effective_limit is not None:
                                get_kwargs["limit"] = effective_limit
                                get_kwargs["offset"] = details_offset
                            details_result = get_permissions(
                                self.request,
                                tableName=table_name,
                                fields=details_fields_for_fetch,
                                where=details_filters,
                                report=True,
                                order_by=order_by,
                                **get_kwargs,
                                **kwargs
                            ).get("data", [])
                            pre_filter_fetch_count_pv = len(details_result)
                            if parent_group_rows and filter_field and not client_paginating_details:
                                cap_key = fk_cap_alias if fk_injected else filter_field
                                details_result, details_truncated = _cap_details_per_parent(
                                    details_result, cap_key
                                )
                            if not client_paginating_details and details_limit is not None and len(details_result) >= details_limit:
                                details_truncated = True
                            if fk_injected:
                                for row in details_result:
                                    row.pop(fk_cap_alias, None)

                        # Compute formula/rollup values
                        if computed_fields_details:
                            details_result = apply_computed_fields_to_records(details_result, computed_fields_details, table_name, schema)
                        if computed_filters_preview:
                            print("Total rows",len(details_result))
                            details_result = apply_computed_filters(
                                details_result,
                                computed_filters_preview,
                                computed_fields=computed_fields_details,
                                table_name=table_name,
                                schema=schema,
                            )
                            post_computed_filter_count_pv = len(details_result)
                            # New-report preview always shows the requested
                            # page size (default 20). The over-fetch above is
                            # only there to *find* enough matches when the
                            # filter has to run in Python — it isn't the
                            # visible payload. Trim to `requested_limit` in
                            # both paginated and unpaginated paths so the
                            # response carries 20 rows, not however many
                            # matched out of the 5000-row sweep.
                            display_cap_pv = requested_limit
                            if display_cap_pv is not None and len(details_result) > display_cap_pv:
                                details_result = details_result[:display_cap_pv]
                                details_truncated = True

                        # Build summary if group_by exists. Skipped on paginated
                        # pages > 0 (client has it) or when skip_summary=true.
                        skip_summary_preview = bool(
                            (client_paginating_details and details_offset_override > 0)
                            or skip_summary_flag
                        )
                        report_result = details_result
                        if group_by_fields and not skip_summary_preview:
                            # group_by_fields may contain dicts like
                            # {"field": "invoice.invoice_date", "grouping": "month"};
                            # extract the field name before the set-membership
                            # check so dicts don't hit "unhashable type: 'dict'".
                            def _gb_name(g):
                                if isinstance(g, dict):
                                    return g.get("field") or g.get("name", "")
                                return g
                            # Resolve formula `formula_expression`s for
                            # computed group_by columns so the SQL builder
                            # can inline them. Without this, a pivot's
                            # column-axis formula (e.g. `tax_amount`) gets
                            # silently stripped here and the pivot's column
                            # buckets render as empty cells. Rollups still
                            # drop (correlated subqueries aren't safe to
                            # inline at this layer).
                            from api.BL.dashboards.dashboard import _SQL_FUNCTION_TOKENS as _GB_SQL_TOKENS_PV, _list_table_columns as _ltc_pv
                            import re as _re_gb_pv
                            _gb_base_columns_pv = _ltc_pv(table_name, schema)

                            def _qualify_and_coalesce_gb_pv(expr, tname, columns):
                                """Same NULL-safe formula inliner as the
                                saved-report path — wraps every column
                                reference in COALESCE(col, 0) so a single
                                NULL operand doesn't drop the row's
                                column-axis value to NULL."""
                                if not expr:
                                    return expr
                                def _repl(m):
                                    ident = m.group(0)
                                    if ident.upper() in _GB_SQL_TOKENS_PV:
                                        return ident
                                    if ident in columns:
                                        return f'COALESCE("{tname}"."{ident}", 0)'
                                    return ident
                                return _re_gb_pv.sub(r"\b[a-zA-Z_]\w*\b", _repl, expr)

                            _resolved_pv = []
                            for g in group_by_fields:
                                gname = _gb_name(g)
                                if gname not in all_computed:
                                    _resolved_pv.append(g)
                                    continue
                                meta_pv = (computed_fields_details or {}).get(gname)
                                if not meta_pv:
                                    meta_pv = next(
                                        (m for k, m in (computed_fields_details or {}).items()
                                         if (m.get("name") == gname or k == gname)),
                                        None,
                                    )
                                if meta_pv and meta_pv.get("datatype") == "formula" and meta_pv.get("formula_expression"):
                                    expr_sql_pv = _qualify_and_coalesce_gb_pv(
                                        meta_pv["formula_expression"], table_name, _gb_base_columns_pv,
                                    )
                                    new_g_pv = dict(g) if isinstance(g, dict) else {"field": gname}
                                    new_g_pv["expression"] = expr_sql_pv
                                    _resolved_pv.append(new_g_pv)
                                # else: drop (rollup or unresolved formula).
                            group_by_fields = _resolved_pv
                            if group_by_fields:
                                physical_filtered, computed_fields_summary, _ = process_computed_fields_for_report(filtered_fields, table_name, schema)
                                # Re-attach computed group_by fields to
                                # the SELECT so the result rows carry
                                # their column-axis values under the
                                # alias the frontend pivot reads.
                                _existing_pf_pv = set()
                                for _pf in physical_filtered:
                                    if isinstance(_pf, dict):
                                        _existing_pf_pv.add(_pf.get("name"))
                                        _existing_pf_pv.add(_pf.get("alias"))
                                    else:
                                        _existing_pf_pv.add(_pf)
                                for _g in group_by_fields:
                                    if not isinstance(_g, dict) or not _g.get("expression"):
                                        continue
                                    _gname = _g.get("field") or _g.get("name", "")
                                    if not _gname:
                                        continue
                                    _galias = _gname.replace(".", "_") if "." in _gname else _gname
                                    if _galias in _existing_pf_pv:
                                        continue
                                    # `expression: True` shape so the SQL
                                    # builder emits the formula SQL
                                    # directly and `get_permissions`
                                    # doesn't strip it as a computed
                                    # column.
                                    physical_filtered.append({
                                        "name": _g["expression"],
                                        "expression": True,
                                        "alias": _galias,
                                    })
                                physical_filtered.append({
                                    "aggregate": "count",
                                    "name": "id",
                                    "alias": "row_count",
                                })
                                # Scope the summary GROUP BY to the same
                                # parent_values the parent_keys probe picked
                                # — even when client_paginating_details=True
                                # (Detail Rows OFF or saved-report preview).
                                # Otherwise the summary returns one set of
                                # groups while the computed-agg refetch
                                # populates a DIFFERENT set, and the Python
                                # bucketing finds no overlap → 0.00 cells.
                                summary_filters = list(filters)
                                if parent_group_rows and filter_field and parent_values:
                                    summary_filters.append({
                                        "field": filter_field,
                                        "operator": "in",
                                        "value": parent_values,
                                    })
                                result = get_permissions(
                                    self.request,
                                    tableName=table_name,
                                    fields=physical_filtered,
                                    where=summary_filters,
                                    group_by=group_by_fields,
                                    report=True,
                                    order_by=order_by,
                                    # Preview surface only renders 20 rows;
                                    # cap the GROUP BY result accordingly.
                                    limit=20,
                                    offset=0,
                                    **kwargs
                                )
                                report_result = result.get("data", [])

                                # SQL GROUP BY can't aggregate formula/rollup
                                # fields (they have no physical column). Pull
                                # the same parent-scoped detail rows, evaluate
                                # the computed fields per record, then bucket
                                # by group keys and apply the aggregator. This
                                # is what fills "Sum of Invoice : Grand Total"
                                # type cells when grand_total is a rollup.
                                # Same logic as the saved-report path: pick
                                # up every formula/rollup column from the
                                # full `fields` list (filter_summary_fields
                                # drops non-aggregate variants), defaulting
                                # to SUM and writing to `sum_<alias>` so
                                # the frontend's `${aggregate}_${apiName}`
                                # cell lookup hits the right key.
                                _full_details_pv = get_details_fields(fields)
                                _, _full_computed_pv, _ = process_computed_fields_for_report(
                                    _full_details_pv, table_name, schema
                                )
                                _merged_pv = dict(computed_fields_summary or {})
                                for _k, _v in (_full_computed_pv or {}).items():
                                    if _k not in _merged_pv:
                                        _merged_pv[_k] = _v
                                computed_agg_fields_pv = {}
                                for _k, _v in _merged_pv.items():
                                    if _v.get("aggregate"):
                                        computed_agg_fields_pv[_k] = _v
                                        continue
                                    if _v.get("datatype") in ("formula", "rollup_summary"):
                                        _meta = dict(_v)
                                        _meta["aggregate"] = "sum"
                                        _base = _v.get("alias") or _k
                                        _agg_key = (
                                            _base if _base.startswith("sum_") else f"sum_{_base}"
                                        )
                                        _meta["alias"] = _agg_key
                                        computed_agg_fields_pv[_agg_key] = _meta
                                if computed_agg_fields_pv and report_result:
                                    # Always refetch with parent_values scope
                                    # for aggregation, regardless of
                                    # client_paginating_details. The detail
                                    # grid stays paginated separately; this
                                    # refetch is purely for filling the
                                    # summary's formula/rollup cells.
                                    agg_where = list(filters)
                                    if parent_group_rows and filter_field and parent_values:
                                        agg_where.append({
                                            "field": filter_field,
                                            "operator": "in",
                                            "value": parent_values,
                                        })
                                    agg_get_kwargs = {
                                        "where": agg_where,
                                        "limit": REPORT_MAX_DETAIL_ROWS,
                                        "offset": 0,
                                    }
                                    detail_rows_for_agg = get_permissions(
                                        self.request,
                                        tableName=table_name,
                                        fields=details_fields_for_fetch,
                                        report=True,
                                        **agg_get_kwargs,
                                        **kwargs,
                                    ).get("data", [])
                                    if computed_fields_details:
                                        detail_rows_for_agg = apply_computed_fields_to_records(
                                            detail_rows_for_agg,
                                            computed_fields_details,
                                            table_name,
                                            schema,
                                        )

                                    def _gb_key_pv(gb):
                                        if isinstance(gb, dict):
                                            n = gb.get("field") or gb.get("name") or ""
                                        else:
                                            n = str(gb)
                                        return n.replace(".", "_")

                                    group_keys_pv = [_gb_key_pv(g) for g in group_by_fields]
                                    has_date_grouping_pv = any(
                                        isinstance(g, dict)
                                        and (g.get("grouping") or g.get("grouping_unit"))
                                        for g in group_by_fields
                                    )

                                    def _extract_raw_pv(record, meta):
                                        # `apply_computed_fields_to_records`
                                        # stores the evaluated formula/
                                        # rollup value on each record under
                                        # the ORIGINAL alias (e.g.
                                        # "invoice_grand_total"). The agg
                                        # meta we receive here, however,
                                        # was rewritten with the SUM-
                                        # prefixed alias ("sum_invoice_
                                        # grand_total") so the SQL builder
                                        # could push the aggregate. Without
                                        # also trying the dotted-to-
                                        # underscore alias and the
                                        # `sum_`-stripped alias, this
                                        # extractor never finds the value
                                        # and every grouped cell renders
                                        # 0.00 even though the underlying
                                        # detail rows have the right value
                                        # populated.
                                        fname = meta.get("name", "")
                                        alias = meta.get("alias") or ""
                                        candidates = [
                                            fname,
                                            fname.split(".")[-1] if fname else None,
                                            fname.replace(".", "_") if fname else None,
                                            alias,
                                            alias[len("sum_"):] if alias.startswith("sum_") else None,
                                        ]
                                        for key in candidates:
                                            if key and record.get(key) is not None:
                                                return record.get(key)
                                        return None

                                    def _apply_agg_pv(values, agg):
                                        agg = (agg or "sum").lower()
                                        if not values:
                                            return 0
                                        if agg == "sum":
                                            return round(sum(values), 2)
                                        if agg == "min":
                                            return round(min(values), 2)
                                        if agg == "max":
                                            return round(max(values), 2)
                                        if agg == "count":
                                            return len(values)
                                        if agg == "avg":
                                            return round(sum(values) / len(values), 2)
                                        if agg == "median":
                                            sv = sorted(values)
                                            n = len(sv)
                                            mid = n // 2
                                            m = sv[mid] if n % 2 else (sv[mid - 1] + sv[mid]) / 2
                                            return round(m, 2)
                                        return round(sum(values), 2)

                                    # Build a per-record transform for each
                                    # group key. Date-grouped fields need the
                                    # raw timestamp on the detail row to be
                                    # reformatted to match the SQL alias on
                                    # the summary side (Postgres emits
                                    # TO_CHAR(date, 'Mon') etc., so a detail
                                    # row's "2024-09-01..." must become "Sep"
                                    # before bucketing). Without this each
                                    # group ends up with the same global
                                    # aggregate.
                                    from datetime import datetime as _dt
                                    _MONTH_ABBR = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
                                    def _grouping_unit_for(g):
                                        if isinstance(g, dict):
                                            return (g.get("grouping") or g.get("grouping_unit") or "").lower()
                                        return ""
                                    def _coerce_date_value(val, unit):
                                        if val is None:
                                            return None
                                        d = None
                                        if hasattr(val, "year"):
                                            d = val
                                        elif isinstance(val, str):
                                            try:
                                                d = _dt.fromisoformat(val.replace("Z", "+00:00"))
                                            except Exception:
                                                try:
                                                    d = _dt.strptime(val[:10], "%Y-%m-%d")
                                                except Exception:
                                                    return val
                                        if d is None:
                                            return val
                                        # Match the SQL TO_CHAR formats
                                        # in `complexGetSql.GROUPING_FORMAT_MAP`
                                        # so the detail-side bucket key
                                        # compares equal to the
                                        # summary-side group value.
                                        if unit == "year":
                                            return d.strftime("%Y")
                                        if unit == "quarter":
                                            return f"Q{((d.month - 1) // 3) + 1}-{d.year}"
                                        if unit == "month":
                                            return f"{_MONTH_ABBR[d.month - 1]}-{d.year}"
                                        if unit in ("day", "date"):
                                            return d.strftime("%d-%m-%Y")
                                        if unit == "hour":
                                            return d.strftime("%d-%m-%Y %H")
                                        if unit == "minute":
                                            return d.strftime("%d-%m-%Y %H:%M")
                                        return val
                                    grouping_units = [_grouping_unit_for(g) for g in group_by_fields]

                                    from collections import defaultdict
                                    grouped_details_pv = defaultdict(list)
                                    for rec in detail_rows_for_agg:
                                        key_parts = []
                                        for idx, k in enumerate(group_keys_pv):
                                            v = rec.get(k)
                                            unit = grouping_units[idx] if idx < len(grouping_units) else ""
                                            if unit:
                                                v = _coerce_date_value(v, unit)
                                            key_parts.append(v)
                                        grouped_details_pv[tuple(key_parts)].append(rec)
                                    for row in report_result:
                                        key = tuple(row.get(k) for k in group_keys_pv)
                                        matching = grouped_details_pv.get(key, [])
                                        for alias, meta in computed_agg_fields_pv.items():
                                            values = []
                                            for rec in matching:
                                                raw = _extract_raw_pv(rec, meta)
                                                if raw is None:
                                                    continue
                                                try:
                                                    values.append(float(raw))
                                                except (TypeError, ValueError):
                                                    pass
                                            row[alias] = _apply_agg_pv(values, meta.get("aggregate"))

                        # Unpaginated total for the detail grid so the frontend
                        # can size its pagination UI without a follow-up call.
                        # Skipped on paginated pages > 0, when skip_count=true,
                        # or when Detail Rows is off (count is only meaningful
                        # for the detail grid — the summary has its own
                        # row_count column from the GROUP BY).
                        skip_count_preview = bool(
                            (client_paginating_details and details_offset_override > 0)
                            or skip_count_flag
                            or skip_details_preview
                        )
                        # Always try the direct SQL count first against the
                        # physical filter set — `convert_rollup_filters_to_physical`
                        # has already pushed the rollup predicate down to a
                        # native FK-IN where possible, so even computed-filter
                        # reports get an accurate count. Fall back to the
                        # post-Python-filter count when a leftover computed
                        # filter remains.
                        total_count = None
                        cap_hit_pv = bool(
                            effective_limit is not None
                            and pre_filter_fetch_count_pv >= effective_limit
                        )
                        if not skip_count_preview:
                            total_count = direct_report_count(
                                table_name, filters, get_validated_schema(kwargs)
                            )
                            if total_count is None:
                                try:
                                    count_res = get_permissions(
                                        self.request,
                                        tableName=table_name,
                                        fields=[{"aggregate": "count", "name": "id", "alias": "total"}],
                                        where=filters,
                                        report=True,
                                        **kwargs,
                                    )
                                    count_rows = count_res.get("data") or []
                                    if count_rows:
                                        total_raw = (count_rows[0] or {}).get("total")
                                        if total_raw is not None:
                                            total_count = int(total_raw)
                                except Exception as count_exc:
                                    print(f"[report-preview] total_count SQL failed: {count_exc!r}")
                                    total_count = None
                            # When a computed filter is still pending in
                            # Python, the SQL count above ignores it. The
                            # post-Python-filter count reflects what's
                            # actually rendered — prefer it when the SQL
                            # count would mislead.
                            if computed_filters_preview and post_computed_filter_count_pv is not None:
                                total_count = post_computed_filter_count_pv
                                if cap_hit_pv:
                                    details_truncated = True
                            # Last-resort fallback: when every count path
                            # failed AND we know the main fetch returned
                            # the complete result set (didn't hit the
                            # limit), use the rendered row count.
                            if (
                                total_count is None
                                and effective_limit is not None
                                and not skip_details_preview
                                and details_filters is not None
                                and pre_filter_fetch_count_pv < effective_limit
                            ):
                                total_count = pre_filter_fetch_count_pv

                        # Group count for Summary View pagination: distinct
                        # values of the parent group key under the same filter
                        # set. Mirrors the GET-report path so the preview UI
                        # can size summary pagination ("1-50 of N groups")
                        # without a follow-up call.
                        group_count = None
                        if parent_group_rows and not skip_count_preview:
                            parent_key_raw_gc = parent_group_rows[0]
                            if isinstance(parent_key_raw_gc, dict):
                                parent_key_gc = parent_key_raw_gc.get("field") or parent_key_raw_gc.get("name", "")
                            else:
                                parent_key_gc = parent_key_raw_gc
                            if parent_key_gc:
                                if "." in parent_key_gc:
                                    gc_field = f"{parent_key_gc.split('.', 1)[0]}_id"
                                else:
                                    gc_field = parent_key_gc
                                try:
                                    group_count = direct_group_count(
                                        table_name, filters, gc_field, get_validated_schema(kwargs)
                                    )
                                except Exception as gc_exc:
                                    print(f"[report-preview] group_count SQL failed: {gc_exc!r}")
                                    group_count = None
                                # Fallback: distinct parent FKs in the
                                # post-filter detail set. Bounded by the
                                # over-fetch cap so this is a lower bound
                                # when the filter pushed Python-side, but
                                # better than null.
                                if group_count is None and details_result:
                                    keys = set()
                                    cap_alias = "__cap_parent_fk__"
                                    for r in details_result:
                                        v = r.get(gc_field) or r.get(cap_alias)
                                        if v is not None:
                                            keys.add(v)
                                    if keys:
                                        group_count = len(keys)

                        # Final hard cap for the new-report preview surface:
                        # the user's preview message says "Previewing 20
                        # records" so the response must carry at most 20
                        # rows of `data` (summary) AND 20 rows of `details`
                        # — regardless of how many filters or group_by
                        # fields are configured. Any branch above
                        # (parent-scoped detail fetch, summary GROUP BY,
                        # over-fetch + Python trim) can otherwise leak more
                        # than 20 rows into the visible preview when
                        # grouping multiplies child rows per parent.
                        PREVIEW_HARD_CAP = (
                            details_limit_override
                            if client_paginating_details and details_limit_override is not None
                            else 20
                        )
                        if isinstance(report_result, list) and len(report_result) > PREVIEW_HARD_CAP:
                            report_result = report_result[:PREVIEW_HARD_CAP]
                            details_truncated = True
                        if isinstance(details_result, list) and len(details_result) > PREVIEW_HARD_CAP:
                            details_result = details_result[:PREVIEW_HARD_CAP]
                            details_truncated = True

                        # Step 3: Return the same structure as GET report
                        return {
                            "id": create_data.get("id"),
                            "name": create_data.get("name"),
                            "report_type": create_data.get("report_type"),
                            "fields": fields,
                            "filters": filters,
                            "group_by": normalize_group_by(group_by),
                            "filter_logic": filter_logic,
                            "filter_json": filters,
                            "created_at": None,
                            "updated_at": None,
                            "table_name": table_name,
                            "show_row_counts": show_row_counts,
                            "show_detail_rows": show_detail_rows,
                            "show_subtotals": show_subtotals,
                            "show_grand_total": show_grand_total,
                            "data": report_result,
                            "details": details_result,
                            "truncated": details_truncated,
                            "total_count": total_count,
                            "group_count": group_count,
                        }

                    report_data = create_data or data  # accept top-level or nested
                    return post_permission(self.request, 'report', create_data=report_data, setup_check=False, **kwargs)                

                elif another_object == 'report_folder':
                    folder_data = create_data or data   # accept top-level or nested
                    print("Creating report folder with data:", folder_data)
                    return post_permission(self.request, 'report_folder', create_data=folder_data, setup_check=False, **kwargs)

                elif another_object == "telephony_user":
                    return post_permission(self.request, another_object, create_data=create_data, **kwargs)                 
                else:
                    if not create_data:
                        raise Exception('Please provide details.')
                    result = post_permission(self.request, another_object, create_data=create_data, **kwargs)
                    return result
                

            elif self.object_name == "telephony":
                if another_object == "makecall":
                    objectid = create_data["object_id"]
                    targeted_object = create_data["targeted_object"]
                    targeted_field = create_data["targeted_field"]
                    target_object_id = create_data["target_object_id"]
                    telephony_id = create_data["telephony_id"]
                    try:
                        object_details = get_permissions(self.request, tableName='telephony_config', where =[{'field': 'id', 'value': telephony_id, 'operator': '='}], **kwargs).get('data',[None])[0]
                        if object_details and object_details.get("provider") == "voxbay":
                            obj = get_permissions(self.request,tableName=targeted_object,where=[{"field":"id","operator":"=","value":target_object_id}],fields=[targeted_field],**kwargs).get("data",[None])[0]
                            if obj:
                                landingnumber = get_permissions(self.request,tableName="landing_numbers",where=[{"field":"id","operator":"=","value":objectid},{"field":"profile_id","operator":"=","value":kwargs.get("profile_id")}],**kwargs).get("data",[])
                                obje = get_permissions(self.request,tableName='telephony_user',where=[{"field":"user_id","operator":"=","value":user_id}],**kwargs).get("data",None)
                                calluser={}
                                if obje:
                                    calluser = obje[0]
                                    if not calluser.get("status"):
                                        return {"data":{},"status":"failed","message":"User account not active to make a call!"}
                                else:
                                    return {"data":{},"status":"failed","message":"Extension number not found"}
                                # if not userObject:
                                #     return {"data":{},"status":"failed","message":"Account not configure to make a call"}
                                if len(landingnumber) == 0:
                                    return {"data":{},"status":"failed","message":"Object not configure to make a call"}
                                target = obj[targeted_field]
                                UID =  object_details.get("authtoken","")
                                PIN = object_details.get("sid","")
                                detail_str = calluser.get("details")
                                if isinstance(detail_str,str):
                                    try:
                                        details = json.loads(detail_str)
                                    except json.JSONDecodeError:
                                        return {"data":{},"status":"failed","message":"Parse ext failed"}
                                else:
                                    details = detail_str or  {}
                                EXT = details.get("ext_no")                                
                                CALLER_ID = "914847172533"
                                TELEPHONYID=object_details.get("id")
                                objid = object_details.get("target_object")
                                org = get_validated_schema(kwargs)
                                DESTINATIONNUMBER = "91"+target
                                # encrypted = encrypt_dict()
                                query = """INSERT INTO {}.call_logs (call_type, landing_number, customer_number, object_id, agent_id, associated_department, start_time, call_status)
                                VALUES('Outbound', %s, %s, %s, %s, %s, %s,'Connecting') RETURNING id""".format(get_validated_schema(kwargs))
                                values = run_query(query,[CALLER_ID,target,objid,user_id,kwargs.get("profile_id"),datetime.now()])[0]
                                logID = values.get("id","")
                                try:
                                    VOXBAY_API_URL = f"https://x.voxbay.com/api/click_to_call?id_dept=0&uid={UID}&upin={PIN}&user_no={EXT}&destination={DESTINATIONNUMBER}&telephony={logID}&org={org}"
                                    response = requests.get(VOXBAY_API_URL)
                                    print(response.text)
                                    displayfields = object_details.get("display_fields")
                                    dispostionvalues = object_details.get("disposition_values")
                                    return {"status":"pending","sourcenumber":target,"logid":logID,"display_fields":displayfields,"accepted":False,"object":target_object_id,"tabName":targeted_object,"dispostionvalues":dispostionvalues}
                                except Exception as er:
                                    return {"data":{},"status":"failed","message":str(er)}
                    except Exception as er:
                        print("Exception",er)
                        return {"data":{},"message":str(er)}
                    return {} 
            elif self.object_name == "shared_records":  
                return self._handle_shared_record(create_data, **kwargs)
            else:        
                result = post_permission(self.request, self.object_name, create_data=create_data, **kwargs)
            return result
    


    def patch_business_logic(self, data, **kwargs):        
        update_data_ = data.get('data')
        another_object = kwargs.get('another_object')
        param3 = kwargs.get('param3')
        user_id = kwargs.get('user_',{}).get('id')


        if not update_data_:
            raise Exception('Unable to update without any details.')   
        
        if self.object_name == "listview":
            is_pinned = update_data_.get('is_pinned')
            listview_id = update_data_.get('id')
            
            # 1) Handle pinning for dynamic listviews (they might not have a DB id yet)
            dynamic_names = ["all", "today", "yesterday", "this_week", "last_week", "this_month", "last_month"]
            if is_pinned and listview_id in dynamic_names:
                # Check if it already exists in DB
                existing = get_permissions(self.request, tableName='listviews', 
                                         where=[{'field': 'object.name', 'value': another_object, 'operator': '='},
                                                {'field': 'name', 'value': listview_id, 'operator': '='},
                                                {'field': 'owner_id', 'value': user_id, 'operator': '='}], 
                                         **kwargs).get('data')
                
                if existing:
                    # Already in DB — unpin others then pin this one
                    obj_id = existing[0].get('object_id')
                    existing_record_id = existing[0].get('id')
                    with connection.cursor() as cursor:
                        cursor.execute("SET search_path TO %s", [get_validated_schema(kwargs)])
                        cursor.execute(
                            "UPDATE listviews SET is_pinned = FALSE WHERE object_id = %s AND owner_id = %s",
                            [obj_id, user_id]
                        )
                    # Now set this one as pinned
                    return patch_permission(self.request, 'listviews', update_data={'id': existing_record_id, 'is_pinned': True}, setup_check=False, **kwargs)
                else:
                    # Create the record for this dynamic listview
                    dynamic_config = get_dynamic_listview(listview_id, object_name=another_object, **kwargs)
                    if dynamic_config:
                        # Fetch object_id
                        try:
                            obj_data = get_permissions(self.request, tableName='object', where=[{'field': 'name', 'value': another_object, 'operator': '='}], **kwargs).get('data')[0]
                            obj_id = obj_data.get('id')
                        except Exception:
                            raise Exception("Object not found.")

                        create_data = {
                            "name": listview_id,
                            "label": dynamic_config["label"],
                            "object_id": obj_id,
                            "filters": dynamic_config["filters"],
                            "visible_columns": dynamic_config["visible_columns"],
                            "is_pinned": True,
                            "owner_id": user_id
                        }
                        # We need to unpin others first
                        with connection.cursor() as cursor:
                            cursor.execute("SET search_path TO %s", [get_validated_schema(kwargs)])
                            cursor.execute(
                                "UPDATE listviews SET is_pinned = FALSE WHERE object_id = %s AND owner_id = %s",
                                [obj_id, user_id]
                            )
                        return post_permission(self.request, 'listviews', create_data=create_data, setup_check=False, **kwargs)
                # If dynamic_config returned None, fall through to normal patch


            if is_pinned:
                # 1) Get object_id and user_id to unpin others
                object_id = update_data_.get('object_id')
                
                if listview_id and not object_id:
                    existing = get_permissions(self.request, tableName='listviews', where=[{'field': 'id', 'value': listview_id, 'operator': '='}], **kwargs).get('data')
                    if existing:
                        object_id = existing[0].get('object_id')
                
                if object_id:
                    # Unpin all other listviews for this object and user
                    with connection.cursor() as cursor:
                        cursor.execute("SET search_path TO %s", [get_validated_schema(kwargs)])
                        cursor.execute(
                            "UPDATE listviews SET is_pinned = FALSE WHERE object_id = %s AND owner_id = %s",
                            [object_id, user_id]
                        )

            filter_logic = update_data_.get('filter_logic', None)
            filters_ = update_data_.get('filters', [])  
            if filter_logic and filter_logic.strip() != "":
                validation_result = validate_filter_logic(filter_logic, len(filters_))
                if not validation_result['valid']:
                    raise Exception(f"Invalid filter logic: {validation_result['error']}")
                
                # Log warnings if any
                if validation_result['warnings']:
                    print(f"[WARNING] Filter logic warnings: {validation_result['warnings']}")
            return patch_permission(self.request, 'listviews', update_data = update_data_, setup_check=False, **kwargs)
        
        elif self.object_name == 'task':
            update_data_['last_modified_by_id'] = user_id
            update_data_['last_modified_date'] = datetime.now()

            return patch_permission(self.request,self.object_name,update_data=update_data_, **kwargs)
        
        elif self.object_name == 'file':
            # file = self.request.FILES.get('file')            
            
            # if not file:
            #     raise Exception('Please provide file to upload.') 
            
            # name = file.name            
            # update_data_ = json.loads(update_data_)
            id = update_data_.get('id')  
            name = update_data_.get('name')
            # prev_file = update_data_.get('prev_file')      
            # if not id or not prev_file:
            #     raise Exception('Please provide valid details.')  
                    
            # Assuming handle_file_upload returns a dictionary
            # result = handle_file_update(file, prev_file)
            # file_path = result.get('file_path', None)    
            # size = result.get('size', None)           
            
            # if not file_path:
            #     raise Exception('Unable to upload file')
            
            modified_data = {
                'id': id,
                'name': name,
            }                
            response = patch_permission(self.request, 'file', update_data=modified_data, **kwargs)
            return response
        elif self.object_name == 'clicked':  
            table = update_data_.get('object')
            id_ = update_data_.get('id')
            try:
                patch_permission(self.request, table, update_data={"id": id_, "recently_viewed": datetime.now()}, **kwargs) 
            except Exception as e:
                print(f"Error updating recently_viewed for {table} id {id_}: {e}")
            return {"success": True, "message": "Updated recently viewed."} 

        elif self.object_name == 'target_item':
            record_id = update_data_.get('id')
            total_target = update_data_.get('total_target')
            teams_target = update_data_.get('team_target')
            self_target = update_data_.get('self_target')
            teams_actual = update_data_.get('team_actual')
            self_actual = update_data_.get('self_actual')
            total_actual = update_data_.get('total_actual')

            # Convert empty strings to None
            if total_target == "":
                total_target = None
            if teams_target == "":
                teams_target = None
            if self_target == "":
                self_target = None
            if teams_actual == "":
                teams_actual = None
            if self_actual == "":
                self_actual = None
            if total_actual == "":
                total_actual = None

            # Always fetch db_record if record_id is present
            db_record = None
            if record_id:
                db_record = get_permissions(self.request, tableName='target_item', id=record_id, **kwargs).get('data', [{}])[0]

            # Calculate self_target if possible
            t_target = total_target if total_target is not None else db_record.get('total_target') if db_record else None
            tm_target = teams_target if teams_target is not None else db_record.get('team_target') if db_record else None
            if t_target is not None and tm_target is not None and (self_target is None):
                try:
                    update_data_['self_target'] = float(t_target) - float(tm_target)
                except Exception:
                    update_data_['self_target'] = None
            else:
                update_data_['self_target'] = self_target

            # Calculate total_actual if possible
            tm_actual = teams_actual if teams_actual is not None else db_record.get('team_actual') if db_record else None
            s_actual = self_actual if self_actual is not None else db_record.get('self_actual') if db_record else None
            if tm_actual is not None and s_actual is not None and (total_actual is None):
                try:
                    update_data_['total_actual'] = float(tm_actual) + float(s_actual)
                except Exception:
                    update_data_['total_actual'] = None
            else:
                update_data_['total_actual'] = total_actual

            # Ensure no empty strings are sent to the DB
            if update_data_.get('self_target') == "":
                update_data_['self_target'] = None
            if update_data_.get('total_actual') == "":
                update_data_['total_actual'] = None
            return patch_permission(self.request, 'target_item', update_data=update_data_, **kwargs)
        elif self.object_name == 'users':
            userService = UserBussinessLogic(self.request, **kwargs)
            return userService.update_user_by_himself(update_data_)

        elif self.object_name == 'setup':     
            if another_object == 'profiles':   
                return update_profiles(self.request, update_data_, **kwargs)           
            elif another_object == 'users':
                userService = UserBussinessLogic(self.request, **kwargs)
                return userService.update_user_by_admin(update_data_) 
            elif another_object == 'fields':
                print("Updating field with data", update_data_)
                update_field_in_table(schema=get_validated_schema(kwargs), data=update_data_)  # Update the field in the actual table
                # update_data_.pop("name", None)  # Remove if exists
                update_data_.pop("datatype", None)
                update_data_.pop("object_name", None)
                update_data_.pop("old_name", None)
                update_data_.pop("new_name", None)
                return patch_permission(self.request, 'fields', update_data=update_data_, **kwargs)
            elif another_object == 'object':
                update_data_.pop("name", None)
                show_tab = update_data_.get("show_tab", None)
                object_id = update_data_.get('id', None)
                if show_tab is not None and object_id:
                    # If show_tab is True, ensure a tab permission exists
                    existing_tabs = get_permissions(self.request, tableName='tab_permissions', where=[{"field":"object_id", "operator": "=", "value": object_id}], **kwargs).get('data', [])
                    new_tabs = []
                    for tab in existing_tabs:
                        new_tabs.append({
                            "id": tab.get("id"),
                            "type": "Default ON" if show_tab else "Off"
                        })                    
                    result = patch_permission(self.request, 'tab_permissions', update_data=new_tabs, **kwargs)
                print("Updating datas",update_data_)
                CacheService().invalidate_all_by_table('tabs', schema=get_validated_schema(kwargs))
                return patch_permission(self.request, 'object', update_data=update_data_, **kwargs)                 
            
            elif another_object == 'workflow':
                return update_workflow(self.request, update_data_, **kwargs)
            elif another_object == 'layout_assignment':
                for data in update_data_:
                    data.pop("profile", None)
                    data.pop("page_layouts", None)                 
                   
                return patch_permission(self.request, 'layout_assignment', update_data=update_data_, **kwargs)                
            
            elif another_object == 'page_builder':
                return update_page_builder(update_data_, **kwargs)              
            
            elif another_object == 'dashboard':
                    dashboard = update_data_.get('dashboard')
                    components = update_data_.get('components')
                    if dashboard is None:
                        raise Exception('Provide dashboard details.')
                    try:
                        with transaction.atomic():
                            patch_permission(self.request, 'dashboard', update_data=dashboard, **kwargs)
                            if components:
                                # Split components into new and update lists
                                new_components = [comp for comp in components if 'id' not in comp]
                                update_components = [comp for comp in components if 'id' in comp]

                                # Extract component names from the new list
                                new_component_names = {comp.get('name') for comp in components if 'name' in comp}
                                existing_component_names = set(dashboard.get('components', []))  
                                name_to_id_mapping = {comp['name']: comp['id'] for comp in components if 'id' in comp}
                                delete_component_names = [name for name in new_component_names if name not in existing_component_names]
                                delete_component_ids = [name_to_id_mapping[name] for name in delete_component_names if name in name_to_id_mapping]
                                new_components = [comp for comp in components if 'id' not in comp and comp.get('name') not in name_to_id_mapping]
                                
                                # Update existing components
                                if update_components:
                                    patch_permission(self.request, 'component', update_data=update_components, **kwargs)

                                # Create new components (only those that truly don’t exist)
                                if new_components:
                                    for component in new_components:
                                        filters = component.get("filters", [])
                                        for filter in filters:
                                            field = filter.get("field")
                                            value = filter.get('value')
                                            operator = filter.get('operator')
                                            # Validate filters
                                            if not all([field, operator, value]):
                                                raise ValueError(f"Invalid filters in new component: {component['name']}")
                                    post_permission(self.request, 'component', create_data=new_components, **kwargs)
                                # Delete removed components
                                if delete_component_ids:
                                    delete_permission(self.request, 'component', ids=delete_component_ids, **kwargs)
                        return 'Updated Successfully'
                    except Exception as e:
                        raise Exception(f"Error occurred: {e}")  
            
            elif another_object == "sharing":
                # Ensure update_data_ is a list
                data_list = update_data_ if isinstance(update_data_, list) else update_data_.get("data", [])

                if not data_list:
                    raise Exception("No data provided for update.")

                if not isinstance(data_list, list):
                    raise Exception("Invalid request: 'data' should be a list of objects.")

                for obj in data_list:
                    sharing_id = obj.get("id")
                    if not sharing_id:
                        raise Exception("Missing 'id' for updating sharing record.")
                    obj.pop("object__name", None)  
                    obj.pop("object__label", None)  

                response = patch_permission(self.request, 'sharing_records', update_data=data_list, **kwargs)
                return response
            
            elif another_object == 'apps':
                file = self.request.FILES.get('file')  
                update_data_ = json.loads(update_data_)  
                app_data = update_data_.get("app")            
                if file:                         
                    # Assuming handle_file_upload returns a dictionary
                    result = handle_file_upload(file, **kwargs)
                    file_path = result.get('file_path', None)
                    # size = result.get('size')                            
                    update_app_data = {
                        **app_data,
                        "image": file_path
                    }   
                    app_data = update_app_data                                     
                profiles = update_data_.get('profiles')    
                cache = CacheService()
                cache.invalidate_all_by_table('tabs', schema=get_validated_schema(kwargs))            
                patch_permission(self.request, 'app_permissions', update_data=profiles, **kwargs) 
                data = get_permissions(self.request, tableName='app', where=[{'field': 'is_deleted', 'operator': '=', 'value': False}],**kwargs).get('data', [])
                excluded_ids = [app for app in data if app_data['id'] != app['id']]
                print("Excluded IDs:", excluded_ids)
                exits_name = [app for app in excluded_ids if app['name'].lower() == app_data['name'].lower()]
                if exits_name:
                    raise Exception('App name already exists.')
                return patch_permission(self.request, 'app', update_data=app_data, **kwargs)
            
            elif another_object == 'theme':
                return patch_permission(self.request, another_object, update_data=update_data_,**kwargs )            
            elif another_object == "pagelayout":
                if isinstance(update_data_, list):
                    layouts = update_data_
                else:
                    layouts = [update_data_]
                
                for layout in layouts:
                    sections = layout.get('sections')
                    if sections:
                        all_selected_fields = []
                        for section in sections:
                            fields = section.get('fields', [])
                            for field in fields:
                                # field could be a dict or a string depending on where it called from
                                if isinstance(field, dict):
                                    all_selected_fields.append(field.get('name', "unknown"))
                                else:
                                    all_selected_fields.append(field)
                        
                        object_name = layout.get('object_name')
                        if not object_name:
                            # Try to fetch object_name if not provided
                            layout_id = layout.get('id')
                            if layout_id:
                                existing = get_permissions(self.request, tableName='page_layouts', id=layout_id, fields=['object_name'], **kwargs).get('data', [])
                                if existing:
                                    object_name = existing[0].get('object_name')
                        
                        if object_name:
                            where_required = [
                                {"field": "object_name", "operator": "=", "value": object_name},
                                {"field": "required", "operator": "=", "value": True}
                            ]
                            required_fields_data = get_permissions(self.request, tableName='fields', where=where_required, fields=['name', 'label'], **kwargs).get('data', [])
                            
                            missing_fields = []
                            for rf in required_fields_data:
                                if rf.get('name') not in all_selected_fields:
                                    missing_fields.append(rf.get('label'))
                            
                            if missing_fields:
                                raise Exception(f"The following mandatory fields are missing from the layout: {', '.join(missing_fields)}.")

                return patch_permission(self.request, "page_layouts", update_data=update_data_,**kwargs)
            elif another_object == 'pathbuilder':
                return patch_permission(self.request, 'path_builder', update_data=update_data_, **kwargs)            
            elif another_object == 'usergroup':
                return patch_user_group(update_data=update_data_,**kwargs)   
                # return patch_permission(self.request, 'user_groups', update_data=update_data_, **kwargs)         
            elif another_object == 'email_provider':
                return patch_permission(self.request, 'email_provider_setup', update_data=update_data_, **kwargs)

            elif another_object == 'target_plan':
                # Update the parent record
                parent_result = patch_permission(self.request, 'target_plan', update_data=update_data_, **kwargs)
                

                # Handle child tables if present
                child_tables = update_data_.get('child_tables', [])
                for child in child_tables:
                    table = child.get('table')
                    records = child.get('records', [])
                    to_update = [rec for rec in records if rec.get('id')]
                    to_create = [rec for rec in records if not rec.get('id')]

                    if to_update:
                        patch_permission(self.request, table, update_data=to_update, **kwargs)
                    if to_create:
                        post_permission(self.request, table, create_data=to_create, **kwargs)

                return parent_result
            elif another_object == 'trackedfields':
                object_name = self.request.GET.get('object_name')
                selected_field_ids = update_data_.get('tracked_fields', [])
                return update_tracked_fields(object_name, selected_field_ids,**kwargs)            
            elif another_object == 'report_folder':
                return patch_permission(self.request, 'report_folder', update_data=update_data_, **kwargs)
            
            elif another_object == 'emailtemplate':
                if not update_data_:
                    raise Exception('Please provide details.')
                id = update_data_.get('id')
                if not id:
                    raise Exception('Please provide valid details.')
                return patch_permission(self.request, 'email_templates', update_data=update_data_, **kwargs)
            
            elif another_object == "masstransfer":
                from_user_id = update_data_.get("from_user_id")
                to_user_id = update_data_.get("to_user_id")
                record_ids = update_data_.get("record_ids")  # Expecting a list of record IDs
                object_name = update_data_.get("object_name")
                kwargs['transfer'] = True  # Indicate that this is a transfer operation
                if not from_user_id or not to_user_id or not record_ids or not object_name:
                    raise Exception("Missing required data: from_user_id, to_user_id, record_ids, object_name")
                update_data = []
                for record_id in record_ids:
                    update_data.append({
                        "id": record_id,
                        "owner_id": to_user_id
                    })
                response = patch_permission(self.request, object_name, update_data=update_data,**kwargs)
                kwargs["assigned_to_id"] = to_user_id
                kwargs["message"] = f"You have new records transferred in {object_name}."
                kwargs['another_object'] = "Mass transfer"
                self.send_to_user(**kwargs)
                return {"message": "Records transferred successfully.", "updated_count": len(update_data)}
            elif another_object == "telephony_user":
                return patch_permission(self.request,another_object,update_data=update_data_,**kwargs)

            if another_object == "telephony":
                res = patch_permission(self.request,"telephony_config",update_data=update_data_,**kwargs)
                return res
            elif another_object == "config":
                if param3 == "landingnumber":
                     return patch_permission(self.request, 'landing_numbers', update_data=update_data_, **kwargs)
            # if another_object == "telephony_user":
            #     return patch_permission(self.request,another_object,update_data=update_data_,**kwargs)
            else:
                return patch_permission(self.request, another_object, update_data = update_data_, **kwargs)
        elif self.object_name == "telephony":
            if another_object == "notes":
                return patch_permission(self.request,'call_logs',update_data = update_data_,**kwargs)
        elif self.object_name == "telephony_user":
            if another_object == "status":
                return patch_permission(self.request,self.object_name,update_data=update_data_,**kwargs)
        else:
            return patch_permission(self.request, self.object_name, update_data = update_data_, **kwargs)



    def delete_business_logic(self, data, **kwargs):
        # Add your DELETE-specific logic here 
        ids = data.get('ids')
        permanent = data.get('permanent', False)         
        another_object = kwargs.get('another_object')
        param3 = kwargs.get('param3')

        data = data.get('data')

        if self.object_name == "sharing":
            if not ids:
                raise Exception("Missing 'ids' for deleting sharing records.")
            return delete_permission(self.request, 'Sharing', ids=ids,**kwargs)

        if self.object_name == "listview":
            if not ids:
                raise Exception("Unable to delete.")
            result = delete_data_sql('listviews', ids, **kwargs)

        elif self.object_name == 'file': 
            if not data:
                raise Exception('Please provide valid details to delete.')                
            id = data.get('id')  
            file_path = data.get('file_path')      
            if not id or not file_path:
                raise Exception('Please provide valid details.')  
            ids =[data.get('id')]             
            result = delete_permission(self.request, 'file', ids=ids,**kwargs)
            return result
        
        elif self.object_name == 'setup':
            if another_object == 'config':
                if param3 == 'landingnumber':
                     return delete_permission(self.request, 'landing_numbers', ids=ids,**kwargs)
            
            if another_object == 'object':
                if param3 == 'fields':
                    return delete_field(data, user=self.request.user, section=f"Deleted field - {self.object_name}",**kwargs) 
                result = delete_customobject(data.get("name"),**kwargs)
                CacheService().invalidate_all_by_table('tabs', schema=get_validated_schema(kwargs))   
                return result
            elif another_object == 'users':
                if not ids:
                    raise Exception("Please provide valid user ID(s) to delete.")
                return UserBussinessLogic(self.request, **kwargs).delete_user(ids)                  
            elif another_object == 'pathbuilder':
                record_id = self.request.GET.get('id')
                if not record_id:
                    raise Exception("Missing ID for deleting pathbuilder record.")
                return delete_permission(self.request, 'path_builder', ids=[record_id],**kwargs)
            
            elif another_object == 'usergroup':
                record_id = self.request.GET.get('id')
                if not record_id:
                    raise Exception("Missing ID for deleting usergroup record.")
                return delete_permission(self.request, 'user_group', ids=[record_id],**kwargs)

            elif another_object == 'deletebin':
                records = data.get("records", [])
                return permanently_delete_records(records, **kwargs)

            elif another_object == 'emptybin':
                return empty_recycle_bin(**kwargs)
        
            elif another_object == 'emailtemplate':
                if not ids:
                    raise Exception('Please provide valid details to delete.')                
                id = data.get('id')  
                if not id:
                    raise Exception('Please provide valid details.')  
                ids =[data.get('id')] 
                result = delete_permission(self.request, 'email_templates', ids=ids, **kwargs)
                return result
            
            elif another_object == 'report_folder':
                if not ids:
                    raise Exception("Please provide valid folder ID(s) to delete.")

                with connection.cursor() as cursor:
                    for folder_id in ids:
                        # Step 1: Get reports in folder
                        cursor.execute("""
                            SELECT id FROM report WHERE folder_id = %s
                        """, [folder_id])
                        report_ids = [row[0] for row in cursor.fetchall()]

                        if report_ids:
                            # Step 2: Check if any report is used in dashboard_component
                            cursor.execute("""
                                SELECT report_id FROM dashboard_component
                                WHERE report_id = ANY(%s)
                            """, [report_ids])
                            used_reports = cursor.fetchall()

                            if used_reports:
                                used_ids = [r[0] for r in used_reports]
                                raise Exception(
                                    f"Cannot delete folder. Report used in dashboards: {used_ids}"
                                )
                # Step 3: Safe to delete
                return delete_permission(self.request, 'report_folder', ids=ids, **kwargs)
            
            elif another_object == 'report':
                if not ids:
                    raise Exception("Please provide valid report ID(s) to delete.")
                
                with connection.cursor() as cursor:
                    # Step 1: Check if report is used in any dashboard_component
                    cursor.execute("""
                        SELECT report_id FROM dashboard_component
                        WHERE report_id = ANY(%s)
                    """, [ids])
                    used_reports = cursor.fetchall()

                    if used_reports:
                        used_ids = [r[0] for r in used_reports]
                        raise Exception(f"Cannot delete report(s). Used in dashboard components: {used_ids}")

                # Step 2: Safe to delete
                return delete_permission(self.request, 'report', ids=ids, **kwargs)
            else:
                result = delete_permission(self.request, another_object, ids=ids, **kwargs)
                return result
        else:
            result = delete_permission(self.request, self.object_name, ids=ids,permanent=permanent, **kwargs)
            return result
    
 
    

def run_query(query, params=None, fetch_one=False, commit=False, **kwargs):
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO %s, public", [get_validated_schema(kwargs)])
        cursor.execute(query, params or [])
        if commit:
            return {"status": "success"}
        if cursor.description:
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            if fetch_one:
                return dict(zip(columns, rows[0])) if rows else None
            return [dict(zip(columns, row)) for row in rows]
        return []


def remove_aggregate_from_fields(fields):
    """
    For details query: include all fields.
    - If it's a dict with an 'aggregate', remove 'aggregate' key.
    - Include all others as-is.
    """
    processed = []
    for field in fields:
        if isinstance(field, dict):
            field_copy = dict(field)
            field_copy.pop('aggregate', None)
            processed.append(field_copy)
        else:
            processed.append(field)
    return processed


from api.BL.computed_fields import process_computed_fields_for_report, apply_computed_fields_to_records, separate_computed_filters, apply_computed_filters, direct_report_count, direct_group_count
from api.security.schema_authority import get_validated_schema


def get_details_fields(fields):
    processed = ['id']
    for field in fields:
        if isinstance(field, dict):
            field_copy = dict(field)
            field_copy.pop("aggregate", None)  # remove aggregate if present
            processed.append(field_copy)
        else:
            processed.append(field)
    return processed


def normalize_group_by(group_by):
    if isinstance(group_by, dict):
        return {
            "rows": group_by.get("rows", []),
            "columns": group_by.get("columns", [])
        }
    elif isinstance(group_by, list):
        return {
            "rows": group_by,
            "columns": []
        }
    return {
        "rows": [],
        "columns": []
    }


def filter_summary_fields(fields, group_by):
    try:
        group_fields = []
        if isinstance(group_by, dict):
            group_fields = list(group_by.get("rows", [])) + list(group_by.get("columns", []))
        elif isinstance(group_by, list):
            group_fields = list(group_by)

        def _gb_field_name(item):
            if isinstance(item, dict):
                return item.get("field") or item.get("name", "")
            return item

        group_field_names = {_gb_field_name(g) for g in group_fields if _gb_field_name(g)}

        filtered = []
        present_names = set()
        present_aliases = set()
        for field in fields:
            if isinstance(field, dict):
                fname = field.get("name")
                falias = field.get("alias")
                if field.get("aggregate"):
                    filtered.append(field)
                    if fname:
                        present_names.add(fname)
                    if falias:
                        present_aliases.add(falias)
                elif fname in group_field_names or falias in group_field_names:
                    filtered.append(field)
                    if fname:
                        present_names.add(fname)
                    if falias:
                        present_aliases.add(falias)
            elif isinstance(field, str):
                if field in group_field_names:
                    filtered.append(field)
                    present_names.add(field)

        # Ensure every group_by field (rows AND columns) is present in
        # the SELECT list — otherwise the SQL result rows don't carry
        # the column-axis values, the frontend's `getColCombos` returns
        # no unique values, and the pivot table renders an empty
        # column-grouping. Group-Column fields that the user added ONLY
        # to the column-grouping panel (not to the main Columns list)
        # used to silently drop here, leaving the pivot's "Tax Amount /
        # Total Amount" headers without buckets.
        for gb in group_fields:
            gb_name = _gb_field_name(gb)
            if not gb_name:
                continue
            if gb_name in present_names or gb_name in present_aliases:
                continue
            alias = gb_name.replace(".", "_") if "." in gb_name else gb_name
            filtered.append({"name": gb_name, "alias": alias})
            present_names.add(gb_name)
            present_aliases.add(alias)

        return filtered
    except Exception as e:
        print(f"Error filtering summary fields: {e}")
        return fields  # fallback to original if any error occurs


def get_all_objects():
    with connection.cursor() as cursor:
        cursor.execute("SELECT DISTINCT object_name FROM objects ORDER BY object_name")
        return [row[0] for row in cursor.fetchall()]

def get_records_for_object(object_name):
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT id, name FROM public."{object_name}" WHERE is_deleted IS DISTINCT FROM true LIMIT 100')
        return [{"id": row[0], "name": row[1]} for row in cursor.fetchall()]
    










