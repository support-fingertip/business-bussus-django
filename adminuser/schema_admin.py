from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.db import connection
from django.shortcuts import render
from django.urls import path

SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")


def _fetch_schemas_with_tables(selected_schema=None):
    """
    Returns:
      schemas: list of dicts [{"name": <schema>, "table_count": int}]
      tables:  list of dicts [{"name": <table>, "row_estimate": int}] for selected_schema
               (empty list if no schema selected)
    """
    with connection.cursor() as cur:
        cur.execute(
            """
            SELECT
                n.nspname AS schema_name,
                COALESCE(t.table_count, 0) AS table_count
            FROM pg_namespace n
            LEFT JOIN (
                SELECT table_schema, COUNT(*) AS table_count
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                GROUP BY table_schema
            ) t ON t.table_schema = n.nspname
            WHERE n.nspname NOT IN %s
              AND n.nspname NOT LIKE 'pg_temp_%%'
              AND n.nspname NOT LIKE 'pg_toast_temp_%%'
            ORDER BY n.nspname
            """,
            [SYSTEM_SCHEMAS],
        )
        schemas = [
            {"name": row[0], "table_count": row[1]} for row in cur.fetchall()
        ]

        tables = []
        if selected_schema:
            cur.execute(
                """
                SELECT
                    c.relname AS table_name,
                    c.reltuples::bigint AS row_estimate
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = %s
                  AND c.relkind = 'r'
                ORDER BY c.relname
                """,
                [selected_schema],
            )
            tables = [
                {"name": row[0], "row_estimate": row[1]} for row in cur.fetchall()
            ]

    return schemas, tables


@staff_member_required
def schemas_view(request):
    selected_schema = request.GET.get("schema") or None
    schemas, tables = _fetch_schemas_with_tables(selected_schema)
    context = {
        **admin.site.each_context(request),
        "title": "Database schemas",
        "schemas": schemas,
        "tables": tables,
        "selected_schema": selected_schema,
    }
    return render(request, "admin/schemas.html", context)


_original_get_urls = admin.site.get_urls


def get_urls():
    custom = [
        path("schemas/", admin.site.admin_view(schemas_view), name="db_schemas"),
    ]
    return custom + _original_get_urls()


admin.site.get_urls = get_urls
