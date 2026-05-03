import re

from CacheService.cache import CacheService
from api.permissions.permissions import get_permissions
from api.BL.computed_fields import (
    process_computed_fields_for_report,
    apply_computed_fields_to_records,
    separate_computed_filters,
)
from django.db import connection


_AGG_KEY_TO_SQL = {"avg": "avg", "max": "max", "min": "min", "total": "sum"}
_SQL_FUNCTION_TOKENS = {
    "ROUND", "ABS", "CEIL", "FLOOR", "COALESCE", "GREATEST", "LEAST",
    "CASE", "WHEN", "THEN", "ELSE", "END", "IF", "AND", "OR", "NOT",
    "TRUE", "FALSE", "NULL", "IS", "IN", "BETWEEN", "LIKE", "ILIKE",
    "TO_CHAR", "EXTRACT", "DATE", "TIMESTAMP",
}


def _list_table_columns(table_name, schema):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO %s", [schema])
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                """,
                [schema, table_name],
            )
            return {row[0] for row in cursor.fetchall()}
    except Exception:
        return set()


def _qualify_formula_expr(expr, table_name, columns):
    """Wrap bare column refs in a formula expression with `"table"."col"`
    so the formula stays unambiguous when the GROUP BY query joins parent
    tables. Reserved SQL tokens and unknown identifiers pass through."""
    if not expr:
        return expr

    def _repl(m):
        ident = m.group(0)
        if ident.upper() in _SQL_FUNCTION_TOKENS:
            return ident
        if ident in columns:
            return f'"{table_name}"."{ident}"'
        return ident

    return re.sub(r"\b[a-zA-Z_]\w*\b", _repl, expr)


def _compute_widget_data(request, component, limit=None, offset=None, **kwargs):
    """
    Fetch and compute data for a dashboard component/widget.

    `limit` / `offset` enable infinite-scroll pagination of widget data.
    Defaults: limit=500 for non-aggregated widgets, no limit for aggregations.

    Fast path: when the widget asks for SUM/AVG/MIN/MAX(metric_field)
    optionally grouped by a dimension AND the metric field is a physical
    column or a formula whose expression is pure arithmetic, push the
    aggregation into SQL. The `SUM(<formula_expr>)` is inlined so a
    1L+ row source table aggregates in PostgreSQL instead of being
    pulled into Python and bucketed there.

    Fallback: the legacy per-record path when the formula is non-trivial
    (uses unsupported functions, references related fields via dot
    notation, etc.).
    """
    data_source = component.get("data_source")
    if not data_source:
        return []

    schema = kwargs.get("schema", "public")
    filters = component.get("filters") or []
    metric_config = component.get("metric_config") or {}
    chart_config = component.get("chart_config") or {}
    widget_settings = component.get("widget_settings") or {}

    # Pagination — clamp to safe bounds
    try:
        page_limit = int(limit) if limit is not None else 500
        page_offset = int(offset) if offset is not None else 0
    except (TypeError, ValueError):
        page_limit, page_offset = 500, 0
    page_limit = max(1, min(page_limit, 5000))
    page_offset = max(0, page_offset)

    # Collect plain-field references for the aggregate metric + grouping.
    metric_fields = {}  # agg_key -> source field name (avg/max/min/total)
    referenced_fields = set()
    for key in ("avg", "max", "min", "total"):
        v = metric_config.get(key)
        if v:
            metric_fields[key] = v
            referenced_fields.add(v)
    group_by_field = chart_config.get("group_by")
    if group_by_field:
        referenced_fields.add(group_by_field)
    for col in chart_config.get("visible_columns", []) or []:
        referenced_fields.add(col)
    for key in ("x_axis", "y_axis", "value_field", "label_field"):
        v = widget_settings.get(key)
        if v:
            referenced_fields.add(v)

    fields_list = list(referenced_fields) if referenced_fields else ["id", "name"]

    # Identify computed fields among the references so we can decide
    # whether to push the aggregation into SQL.
    _, computed_fields, _ = process_computed_fields_for_report(
        fields_list, data_source, schema
    )

    # ── FAST PATH: aggregate pushdown ────────────────────────────────
    # Inline each metric (physical or formula) into SQL as
    # `SUM(<expr>)` / `AVG(<expr>)` etc., GROUP BY the dimension, and
    # let Postgres return one row per group across the entire table.
    if metric_fields or group_by_field:
        table_columns = _list_table_columns(data_source, schema)
        sql_fields = []
        ok = True
        for agg_key, source in metric_fields.items():
            agg_sql = _AGG_KEY_TO_SQL.get(agg_key, "sum")
            cf_meta = computed_fields.get(source)
            if cf_meta and cf_meta.get("datatype") == "formula" and cf_meta.get("formula_expression"):
                expr_sql = _qualify_formula_expr(
                    cf_meta["formula_expression"], data_source, table_columns,
                )
                sql_fields.append({
                    "name": f"{agg_sql.upper()}({expr_sql})",
                    "expression": True,
                    "alias": f"{agg_key}_{source.replace('.', '_')}",
                })
            elif cf_meta:
                # Rollup or related-formula: SQL pushdown is unsafe — fall
                # back to the per-record path so the rollup batcher runs.
                ok = False
                break
            elif "." in source:
                sql_fields.append({
                    "name": source,
                    "aggregate": agg_sql,
                    "alias": f"{agg_key}_{source.replace('.', '_')}",
                })
            else:
                sql_fields.append({
                    "name": source,
                    "aggregate": agg_sql,
                    "alias": f"{agg_key}_{source}",
                })

        if ok:
            # Always emit a count so charts with only group_by have a value.
            sql_fields.append({
                "aggregate": "count",
                "name": "id",
                "alias": "row_count",
            })
            sql_group_by = []
            if group_by_field:
                sql_fields.insert(0, group_by_field)
                sql_group_by.append(group_by_field)
            try:
                # Strip any computed filters before sending to SQL.
                physical_filters, computed_filters = separate_computed_filters(
                    filters, set(computed_fields.keys()), schema, data_source,
                )
                # Aggregate pushdown emits one row per group; the result
                # is already bounded by the number of unique group keys
                # (typically tens or low hundreds). Capping at page_limit
                # truncates the chart's category axis to the first 500
                # groups. Skip the cap entirely when the request didn't
                # ask for explicit pagination — chart widgets need every
                # group to render correctly.
                use_paging = limit is not None
                result = get_permissions(
                    request,
                    tableName=data_source,
                    fields=sql_fields,
                    where=physical_filters,
                    group_by=sql_group_by or None,
                    report=True,
                    limit=page_limit if use_paging else None,
                    offset=page_offset if use_paging else 0,
                    **kwargs,
                )
                return result.get("data", []) or []
            except Exception as e:
                print(f"[DEBUG] Widget aggregate pushdown failed for '{component.get('name')}': {e}")
                # fall through to the row-by-row path

    # ── FALLBACK: per-record path (computed-field heavy) ─────────────
    physical_fields, computed_fields, extra_deps = process_computed_fields_for_report(
        fields_list, data_source, schema
    )
    for dep in extra_deps:
        if dep not in physical_fields:
            physical_fields.append(dep)
    if "id" not in physical_fields:
        physical_fields.append("id")

    filters, computed_filters = separate_computed_filters(
        filters, set(computed_fields.keys()), schema, data_source,
    )

    try:
        result = get_permissions(
            request,
            tableName=data_source,
            fields=physical_fields,
            where=filters,
            limit=page_limit,
            offset=page_offset,
            **kwargs,
        )
        records = result.get("data", [])
    except Exception as e:
        print(f"[DEBUG] Widget data fetch error for '{component.get('name')}': {e}")
        return []

    if computed_fields and records:
        records = apply_computed_fields_to_records(
            records, computed_fields, data_source, schema,
        )

    if computed_filters and records:
        from api.BL.computed_fields import apply_computed_filters
        records = apply_computed_filters(records, computed_filters)

    return records


def get_dashboards(request, id=None, **kwargs):
    try:
        # Pagination params for widget data — used for infinite scroll
        widget_limit = request.GET.get("limit") if hasattr(request, "GET") else None
        widget_offset = request.GET.get("offset") if hasattr(request, "GET") else None
        # Optional: only paginate one specific widget (by name/id) to avoid
        # re-fetching every widget when scrolling a single chart
        target_widget = request.GET.get("widget") if hasattr(request, "GET") else None

        cache = CacheService()
        enriched_dashboards = None
        if enriched_dashboards is None:
            enriched_dashboards = []
            dashboards_data = get_permissions(request, tableName='dashboard', **kwargs)
            dashboards = dashboards_data.get('data', [])
            for dashboard in dashboards:
                component_names = dashboard.get("components", [])  # These are widget names
                canvas_settings = (dashboard.get("layout") or {}).get("canvasSettings", {})
                enriched_components = []
                if component_names:
                    filter = {
                        "where": {
                            "and": [
                                {"field": "name", "operator": "in", "value": component_names}
                            ]
                        }
                    }
                    components_data = get_permissions(
                        request, tableName='dashboard_component', filters=filter, **kwargs
                    )
                    raw_components = components_data.get('data', [])

                    # Only include components that match the names exactly
                    name_set = set(component_names)
                    for component in raw_components:
                        if component.get("name") in name_set:
                            comp_id = component.get("id")
                            layout = canvas_settings.get(comp_id, {})
                            # Apply pagination only to the targeted widget (if specified)
                            apply_paging = (
                                target_widget is None
                                or component.get("name") == target_widget
                                or component.get("id") == target_widget
                            )
                            widget_data = _compute_widget_data(
                                request,
                                component,
                                limit=widget_limit if apply_paging else None,
                                offset=widget_offset if apply_paging else None,
                                **kwargs,
                            )
                            enriched_components.append({
                                **component,
                                "layout": layout,
                                "data": widget_data,
                            })
                dashboard["widgets"] = enriched_components
                enriched_dashboards.append(dashboard)
            cache.set('dash_123', enriched_dashboards, "dashboard", kwargs.get('schema'))  # Cache for 5 minutes
        # Return single dashboard or full list
        if id:
            for d in enriched_dashboards:
                if d["id"] == id:
                    return {"dashboard": d}
            return {"error": "Dashboard not found"}
        else:
            return enriched_dashboards
    except Exception as e:
        raise Exception(f"Failed to fetch dashboard(s): {e}")
    
