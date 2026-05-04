"""Dynamic-object delete pipeline.

Phase 4.B wave 1: dual-path. The legacy raw-cursor implementation
stays in place as ``_delete_data_raw``; a new ``_delete_data_orm``
routes through ``api.ORM.dynamic.dynamic_table`` (the Phase 1
gateway). Public ``delete_data_sql`` dispatches between the two
behind the ``USE_DYNAMIC_GATEWAY`` flag.

Both paths support soft-delete (UPDATE is_deleted = TRUE +
deleted_by_id + deleted_date) when the table has those columns,
and fall back to hard-delete (DELETE FROM ... WHERE id = ...)
otherwise. The legacy path probes for soft-delete columns via
``information_schema.columns``; the ORM path does the same probe
once and reuses the result through both branches.
"""

from datetime import datetime
from psycopg2 import sql
from django.db import connection, transaction
from django.utils import timezone

from api.ORM.sqlFunctions.utils.helpers import validate_identifier
from api.permissions._orm_dispatch import dispatch as _dispatch_path
from api.security.schema_authority import get_validated_schema


_SOFT_DELETE_PROBE_SQL = """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = %s AND table_schema = %s
"""

_AUDIT_COL_PROBE_SQL = """
    SELECT column_name
    FROM information_schema.columns
    WHERE table_name = %s
      AND column_name IN ('deleted_by_id', 'deleted_date')
      AND table_schema = %s
"""


def _resolve_actor_id(user):
    """Extract the user id from the various shapes callers pass in."""
    if user is None:
        return None
    if isinstance(user, dict):
        return user.get("id")
    return getattr(user, "id", None)


def _delete_data_raw(object_name, id_list, section, permanent, schema, user):
    """Legacy raw-cursor implementation — byte-identical to pre-Phase 4.B."""
    table_name = object_name.lower()
    validate_identifier(table_name)

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL search_path TO %s", [schema])

            cursor.execute("SELECT to_regclass(%s)", [table_name])
            if cursor.fetchone()[0] is None:
                raise Exception(f"Table '{table_name}' does not exist.")

            cursor.execute(_SOFT_DELETE_PROBE_SQL, [table_name, schema])
            columns = [row[0] for row in cursor.fetchall()]
            soft_delete_supported = "is_deleted" in columns

            deleted_count = 0

            for record_id in id_list:
                cursor.execute(
                    sql.SQL("SELECT * FROM {} WHERE id = %s").format(sql.Identifier(table_name)),
                    [record_id],
                )
                instance_data = cursor.fetchone()
                if not instance_data:
                    raise Exception(f"No data found with ID {record_id} to delete.")

                if soft_delete_supported and not permanent:
                    set_clauses = ["is_deleted = %s"]
                    values = [True]

                    cursor.execute(_AUDIT_COL_PROBE_SQL, [table_name, schema])
                    cols = [row[0] for row in cursor.fetchall()]

                    actor_id = _resolve_actor_id(user)
                    if "deleted_by_id" in cols and actor_id is not None:
                        set_clauses.append("deleted_by_id = %s")
                        values.append(actor_id)

                    if "deleted_date" in cols:
                        set_clauses.append("deleted_date = %s")
                        values.append(timezone.now())

                    values.append(record_id)
                    cursor.execute(
                        sql.SQL("UPDATE {} SET " + ", ".join(set_clauses) + " WHERE id = %s").format(
                            sql.Identifier(table_name)
                        ),
                        values,
                    )
                else:
                    cursor.execute(
                        sql.SQL("DELETE FROM {} WHERE id = %s").format(sql.Identifier(table_name)),
                        [record_id],
                    )
                deleted_count += 1

            return {"success": True, "message": f"Deleted {deleted_count} record(s)."}


def _delete_data_orm(object_name, id_list, section, permanent, schema, user):
    """Gateway-backed implementation. Uses ``api.ORM.dynamic`` primitives.

    The soft-delete decision still needs an information_schema probe
    (the gateway only knows the metadata registry, not the live
    column list), but the SQL composition for the actual UPDATE /
    DELETE goes through the gateway.
    """
    from api.ORM.dynamic import dynamic_table

    table_name = object_name.lower()
    validate_identifier(table_name)

    # One probe up front for soft-delete columns; reused per record.
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL search_path TO %s", [schema])
        cursor.execute("SELECT to_regclass(%s)", [table_name])
        if cursor.fetchone()[0] is None:
            raise Exception(f"Table '{table_name}' does not exist.")
        cursor.execute(_SOFT_DELETE_PROBE_SQL, [table_name, schema])
        columns = [row[0] for row in cursor.fetchall()]

    soft_delete_supported = "is_deleted" in columns
    has_deleted_by = "deleted_by_id" in columns
    has_deleted_date = "deleted_date" in columns
    actor_id = _resolve_actor_id(user)

    deleted_count = 0
    with transaction.atomic():
        for record_id in id_list:
            # Existence check — keep the same "raise if missing" contract
            # the legacy path has; gateway.update() returns 0 silently on
            # no-match which would mask a bad client request.
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL search_path TO %s", [schema])
                cursor.execute(
                    sql.SQL("SELECT 1 FROM {} WHERE id = %s").format(sql.Identifier(table_name)),
                    [record_id],
                )
                if cursor.fetchone() is None:
                    raise Exception(f"No data found with ID {record_id} to delete.")

            if soft_delete_supported and not permanent:
                patch = {"is_deleted": True}
                if has_deleted_by and actor_id is not None:
                    patch["deleted_by_id"] = actor_id
                if has_deleted_date:
                    patch["deleted_date"] = timezone.now()
                dynamic_table.update(
                    schema,
                    table_name,
                    record_id=record_id,
                    patch=patch,
                )
            else:
                dynamic_table.delete(
                    schema,
                    table_name,
                    record_ids=[record_id],
                )
            deleted_count += 1

    return {"success": True, "message": f"Deleted {deleted_count} record(s)."}


def delete_data_sql(object_name, id_list, section=None, permanent=False, **kwargs):
    """Public entry point — dual-path behind ``USE_DYNAMIC_GATEWAY``.

    Both paths return the same shape: ``{"success": True, "message": "..."}``.
    """
    user = kwargs.get("user_")
    schema = get_validated_schema(kwargs)
    if not schema:
        raise ValueError("Invalid user request: 'schema' is required in kwargs")

    validate_identifier(schema)

    try:
        return _dispatch_path(
            f"deleteSQLFunction.delete_data_sql.{object_name}",
            raw_impl=lambda: _delete_data_raw(
                object_name, id_list, section, permanent, schema, user,
            ),
            orm_impl=lambda: _delete_data_orm(
                object_name, id_list, section, permanent, schema, user,
            ),
            flag="USE_DYNAMIC_GATEWAY",
        )
    except Exception as e:
        raise Exception(str(e))
