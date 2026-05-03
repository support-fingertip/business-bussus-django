# recycle_bin.py
"""Recycle-bin operations.

Hardened in Phase 0:
  - Table names are passed through `psycopg2.sql.Identifier`, never f-string
    interpolated into the SQL text. Validated against `validate_identifier`
    before use.
  - Permanently-delete and empty-recycle-bin paths now require the caller to
    have delete permission on each object via `delete_permission`. Restoring
    soft-deleted records likewise routes through `patch_permission`.
"""

import logging

from django.db import connection
from psycopg2 import sql

from api.ORM.sqlFunctions.utils.helpers import validate_identifier
from api.permissions.permissions import (
    delete_permission,
    patch_permission,
)
from api.security.schema_authority import get_validated_schema

logger = logging.getLogger(__name__)


def _is_deleted_column_exists(cursor, schema, table_name):
    cursor.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s
          AND column_name = 'is_deleted'
          AND table_schema = %s
        """,
        [table_name, schema],
    )
    return cursor.fetchone() is not None


def permanently_delete_records(records, **kwargs):
    if not records:
        raise Exception("No records provided for permanent delete.")

    delete_summary = {}
    schema = (get_validated_schema(kwargs) or 'public')
    request = kwargs.get("request")

    for rec in records:
        object_name = rec.get("object_name")
        record_id = rec.get("record_id")
        if not object_name or not record_id:
            continue

        # Reject anything that isn't a safe SQL identifier before we use it.
        validate_identifier(object_name, "object_name")

        with connection.cursor() as cursor:
            if not _is_deleted_column_exists(cursor, schema, object_name):
                continue
            cursor.execute("SET search_path TO %s", [schema])
            select_q = sql.SQL(
                "SELECT id, is_deleted FROM {} WHERE id = %s"
            ).format(sql.Identifier(object_name))
            cursor.execute(select_q, [record_id])
            row = cursor.fetchone()
            if not (row and row[1]):
                logger.info(
                    "Recycle-bin: record %s not found or not soft-deleted in %s",
                    record_id, object_name,
                )
                continue

        # Permission-gated delete. Pushes audit logging + workflow execution
        # into the canonical delete path instead of doing a raw DELETE here.
        try:
            result = delete_permission(
                request,
                object_name,
                ids=[record_id],
                schema=schema,
                hard_delete=True,
                **{k: v for k, v in kwargs.items() if k != "schema"},
            )
            if result and result.get("success"):
                delete_summary.setdefault(object_name, []).append(record_id)
        except Exception as exc:
            logger.error(
                "Recycle-bin permanent delete failed for %s id=%s: %s",
                object_name, record_id, exc,
            )

    return {
        "success": True,
        "message": f"Permanently deleted records from {len(delete_summary)} object(s).",
        "details": delete_summary,
    }


def empty_recycle_bin(**kwargs):
    delete_summary = {}
    schema = (get_validated_schema(kwargs) or 'public')
    request = kwargs.get("request")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.columns
            WHERE column_name = 'is_deleted'
              AND table_schema = %s
            """,
            [schema],
        )
        tables = [row[0] for row in cursor.fetchall()]

    for table in tables:
        try:
            validate_identifier(table, "table_name")
        except ValueError:
            logger.warning("Recycle-bin: skipping unsafe table name %r", table)
            continue

        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO %s", [schema])
            select_q = sql.SQL(
                "SELECT id FROM {} WHERE is_deleted = TRUE"
            ).format(sql.Identifier(table))
            cursor.execute(select_q)
            record_ids = [row[0] for row in cursor.fetchall()]

        if not record_ids:
            continue

        try:
            result = delete_permission(
                request,
                table,
                ids=record_ids,
                schema=schema,
                hard_delete=True,
                **{k: v for k, v in kwargs.items() if k != "schema"},
            )
            if result and result.get("success"):
                delete_summary[table] = record_ids
        except Exception as exc:
            logger.error(
                "Recycle-bin empty failed for %s: %s", table, exc,
            )

    return {
        "success": True,
        "message": f"Recycle bin emptied. Deleted records from {len(delete_summary)} table(s).",
        "details": delete_summary,
    }


def get_deleted_records(**kwargs):
    schema = (get_validated_schema(kwargs) or 'public')
    deleted_data = {}

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
            """,
            [schema],
        )
        tables = [row[0] for row in cursor.fetchall()]

    for table_name in tables:
        try:
            validate_identifier(table_name, "table_name")
        except ValueError:
            continue

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = %s AND table_schema = %s
                """,
                [table_name, schema],
            )
            columns = [col[0] for col in cursor.fetchall()]

        if "is_deleted" not in columns:
            continue

        has_name = "name" in columns
        has_deleted_by = "deleted_by" in columns
        has_deleted_by_id = "deleted_by_id" in columns
        has_deleted_date = "deleted_date" in columns

        select_parts = [sql.SQL("{}.id AS id").format(sql.Identifier(table_name))]
        mapped_columns = ["id"]
        if has_name:
            select_parts.append(
                sql.SQL("{}.name AS name").format(sql.Identifier(table_name))
            )
            mapped_columns.append("name")
        if has_deleted_by:
            select_parts.append(
                sql.SQL("{}.deleted_by AS deleted").format(
                    sql.Identifier(table_name)
                )
            )
        if has_deleted_by_id:
            select_parts.append(sql.SQL("u.name AS deleted_by_username"))
            mapped_columns.append("deleted_by")
        if has_deleted_date:
            select_parts.append(
                sql.SQL("{}.deleted_date AS deleted_date").format(
                    sql.Identifier(table_name)
                )
            )
            mapped_columns.append("deleted_date")
        select_clause = sql.SQL(", ").join(select_parts)

        records = []
        with connection.cursor() as cursor:
            cursor.execute("SET search_path TO %s", [schema])
            try:
                cursor.execute(
                    sql.SQL(
                        "SELECT {select_clause} "
                        "FROM {table} "
                        "LEFT JOIN public.users u ON {table}.deleted_by_id = u.id "
                        "WHERE {table}.is_deleted = TRUE LIMIT 25"
                    ).format(
                        select_clause=select_clause,
                        table=sql.Identifier(table_name),
                    )
                )
                records = cursor.fetchall()
            except Exception as exc:
                logger.debug(
                    "Falling back to non-join recycle-bin query for %s: %s",
                    table_name, exc,
                )
                cursor.execute(
                    sql.SQL(
                        "SELECT {select_clause} "
                        "FROM {table} "
                        "WHERE is_deleted = TRUE LIMIT 25"
                    ).format(
                        select_clause=select_clause,
                        table=sql.Identifier(table_name),
                    )
                )
                records = cursor.fetchall()

        if records:
            deleted_data[table_name] = [
                dict(zip(mapped_columns, r)) for r in records
            ]
    return deleted_data


def restore_soft_deleted_records(records, **kwargs):
    if not records:
        raise Exception("No records provided for restore.")

    schema = (get_validated_schema(kwargs) or 'public')
    request = kwargs.get("request")
    restored_summary = {}

    for rec in records:
        table_name = rec.get("table_name") or rec.get("object_name")
        record_id = rec.get("record_id")
        if not table_name or not record_id:
            continue

        try:
            validate_identifier(table_name, "table_name")
        except ValueError:
            logger.warning(
                "Restore: skipping unsafe table name %r", table_name,
            )
            continue

        # Confirm soft-delete column exists before we ask the permissions
        # layer to perform the update.
        with connection.cursor() as cursor:
            if not _is_deleted_column_exists(cursor, schema, table_name):
                continue

        try:
            patch_permission(
                request,
                table_name,
                update_data={"id": record_id, "is_deleted": False},
                schema=schema,
                **{k: v for k, v in kwargs.items() if k != "schema"},
            )
            restored_summary.setdefault(table_name, []).append(record_id)
        except Exception as exc:
            logger.error(
                "Restore failed for %s id=%s: %s", table_name, record_id, exc,
            )

    return {
        "success": True,
        "message": f"Restored records from {len(restored_summary)} object(s).",
        "details": restored_summary,
    }
