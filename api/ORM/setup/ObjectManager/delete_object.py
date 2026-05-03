import logging

from django.db import connection, transaction
from psycopg2 import sql

from api.ORM.AuditLogs.audit_trail_logs import log_audit
from api.ORM.sqlFunctions.utils.helpers import validate_identifier
from api.security.schema_authority import get_validated_schema

logger = logging.getLogger(__name__)


def delete_customobject(name, **kwargs):
    """Delete a custom object and all related records using safe SQL."""
    schema = (get_validated_schema(kwargs) or 'public')

    if not name:
        raise Exception("Object name is required.")

    # Both `name` (the user-defined object/table) and `schema` flow into
    # SQL identifiers below. Reject anything that isn't a strict
    # identifier before we touch the DB. The DDL/DML below still uses
    # `sql.Identifier` so this is defence-in-depth.
    validate_identifier(name, "object_name")
    validate_identifier(schema, "schema")

    try:
        with connection.cursor() as cursor, transaction.atomic():
            cursor.execute("SET search_path TO %s", [schema])

            # Object existence + standard-vs-custom guard.
            cursor.execute(
                "SELECT id, type FROM object WHERE name = %s",
                [name],
            )
            row = cursor.fetchone()
            if not row:
                raise Exception(f"Object '{name}' does not exist.")
            if row[1] == "standard":
                raise Exception(
                    f"Object '{name}' is a standard object and cannot be deleted."
                )

            object_id = row[0]

            # Delete dependent metadata rows. All values are parameterized.
            cursor.execute("DELETE FROM fields WHERE object_id = %s", [object_id])
            cursor.execute(
                "DELETE FROM field_permissions WHERE object_id = %s", [object_id]
            )
            cursor.execute(
                "DELETE FROM object_permissions WHERE object_id = %s", [object_id]
            )
            cursor.execute(
                "DELETE FROM listviews WHERE object_id = %s", [object_id]
            )
            cursor.execute(
                "DELETE FROM page_layouts WHERE object_name = %s", [name]
            )
            cursor.execute(
                "DELETE FROM search_layouts WHERE object_id = %s", [object_id]
            )
            cursor.execute(
                "DELETE FROM sharing_records WHERE object_id = %s", [object_id]
            )
            cursor.execute(
                "DELETE FROM tab_permissions WHERE object_id = %s", [object_id]
            )
            cursor.execute("DELETE FROM object WHERE id = %s", [object_id])

            try:
                remove_tab_from_apps(name, schema)
            except Exception as exc:
                # Failure to clean tabs shouldn't abort the rest of the delete,
                # but the partial state must surface in logs.
                logger.error("remove_tab_from_apps failed for %s: %s", name, exc)

            # SAFE DDL: identifier is escaped, never interpolated as text.
            try:
                drop_q = sql.SQL("DROP TABLE IF EXISTS {} CASCADE").format(
                    sql.Identifier(name)
                )
                cursor.execute(drop_q)
            except Exception as exc:
                logger.error("DROP TABLE failed for %s: %s", name, exc)
                raise

            log_audit(
                f"Deleted custom object {name} and its related records",
                "Custom Object Deletion",
                **kwargs,
            )

        return {
            "success": True,
            "message": (
                f"Custom object '{name}' and its related records have "
                "been deleted successfully."
            ),
        }

    except Exception as e:
        raise Exception(str(e))


def remove_tab_from_apps(name: str, schema: str):
    """Remove an entry from the JSONB ``tabs`` array in <schema>.app."""
    validate_identifier(schema, "schema")

    query = sql.SQL(
        """
        UPDATE {}.app
        SET tabs = (
            SELECT COALESCE(jsonb_agg(elem), '[]'::jsonb)
            FROM jsonb_array_elements(tabs) AS elem
            WHERE elem->>'name' <> %s
        )
        WHERE tabs IS NOT NULL
        """
    ).format(sql.Identifier(schema))

    with connection.cursor() as cursor:
        cursor.execute(query, [name])
