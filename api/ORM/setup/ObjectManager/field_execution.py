from django.db import connection
from django.db import transaction
from typing import Dict, List, Tuple
import re
from psycopg2 import sql


_IDENTIFIER_RE = re.compile(r"[A-Za-z_][\w]*")

def _validate_identifier(value: str, field: str) -> str:
    """Basic identifier validation to block SQL injection via names."""
    if not value or not _IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"Invalid identifier for {field}: '{value}'")
    return value


def _ensure_positive_int(value, field: str, default: int) -> int:
    try:
        val = int(value) if value is not None else int(default)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid integer for {field}: '{value}'")
    if field == "decimal_places":
        if val < 0:
            raise ValueError(f"{field} must be non-negative; got {val}")
    elif val <= 0:
        raise ValueError(f"{field} must be positive; got {val}")
    return val


def _set_search_path(cursor, schema: str):
    cursor.execute(sql.SQL("SET search_path TO {};").format(sql.Identifier(schema)))

def add_field_to_table(schema: str, data: Dict):
    print(f"Adding field to table with schema: {schema} and data: {data}")
    try:
        schema = _validate_identifier(schema, "schema")
        object_name = _validate_identifier(data.get("object_name", ""), "object_name")
        field_name = _validate_identifier(data.get("name", ""), "name")
        parent_object = data.get("parent_object")
        parent_object = _validate_identifier(parent_object, "parent_object") if parent_object else None
        with connection.cursor() as cursor:
            _set_search_path(cursor, schema)

        with transaction.atomic():
            alter_queries: List[Tuple[sql.SQL, List]] = []
            datatype = data.get("datatype")
            if datatype == "lookup_relationship":
                on_delete = "CASCADE" if data.get("on_delete") else "SET NULL"
                alter_queries.append(
                    (
                        sql.SQL(
                            "ALTER TABLE {} ADD COLUMN {} VARCHAR(64) REFERENCES {}({}) ON DELETE {}"
                        ).format(
                            sql.Identifier(object_name),
                            sql.Identifier(field_name),
                            sql.Identifier(parent_object),
                            sql.Identifier("id"),
                            sql.SQL(on_delete),
                        ),
                        [],
                    )
                )
            elif datatype in ["textarealong", "address", "text_area_long"]:
                alter_queries.append(
                    (
                        sql.SQL("ALTER TABLE {} ADD {} TEXT").format(
                            sql.Identifier(object_name),
                            sql.Identifier(field_name),
                        ),
                        [],
                    )
                )
            elif datatype == "number":
                precision = _ensure_positive_int(data.get("number_length"), "number_length", 18)
                scale = _ensure_positive_int(data.get("decimal_places"), "decimal_places", 0)
                alter_queries.append(
                    (
                        sql.SQL("ALTER TABLE {} ADD {} NUMERIC({},{})").format(
                            sql.Identifier(object_name),
                            sql.Identifier(field_name),
                            sql.Literal(precision),
                            sql.Literal(scale),
                        ),
                        [],
                    )
                )
            elif datatype in ["currency", "percent"]:
                precision = _ensure_positive_int(data.get("number_length"), "number_length", 18)
                scale = _ensure_positive_int(data.get("decimal_places"), "decimal_places", 0)
                alter_queries.append(
                    (
                        sql.SQL("ALTER TABLE {} ADD {} NUMERIC({},{})").format(
                            sql.Identifier(object_name),
                            sql.Identifier(field_name),
                            sql.Literal(precision),
                            sql.Literal(scale),
                        ),
                        [],
                    )
                )
            elif datatype == "auto_number":
                sequence = _validate_identifier(f"sequence_{field_name}_{object_name}", "sequence")
                starting_number = _ensure_positive_int(data.get("starting_number"), "starting_number", 1)
                display_format = data.get("display_format") or ""
                m = re.fullmatch(r"([A-Za-z_]+-)\{(0+)\}", display_format)
                if not m:
                    raise Exception(
                        f"Invalid Auto Number format: '{display_format}'. Expected format like 'ABC-{{0000}}'."
                    )
                prefix = m.group(1)
                zero_block = m.group(2)
                padding_length = len(zero_block) + len(str(starting_number))

                default_expr = sql.SQL("{} || LPAD(nextval({})::text, {}, '0')").format(
                    sql.Literal(prefix),
                    sql.Literal(sequence),
                    sql.Literal(padding_length),
                )
                alter_queries.append(
                    (
                        sql.SQL("CREATE SEQUENCE {} START WITH %s").format(sql.Identifier(sequence)),
                        [starting_number],
                    )
                )
                alter_queries.append(
                    (
                        sql.SQL("ALTER TABLE {} ADD COLUMN {} TEXT").format(
                            sql.Identifier(object_name),
                            sql.Identifier(field_name),
                        ),
                        [],
                    )
                )
                alter_queries.append(
                    (
                        sql.SQL("ALTER TABLE {} ALTER COLUMN {} SET DEFAULT {}").format(
                            sql.Identifier(object_name),
                            sql.Identifier(field_name),
                            default_expr,
                        ),
                        [],
                    )
                )
                if data.get("auto_number"):
                    update_expr = sql.SQL("{} || LPAD(nextval({})::text, {}, '0')").format(
                        sql.Literal(prefix),
                        sql.Literal(sequence),
                        sql.Literal(padding_length),
                    )
                    alter_queries.append(
                        (
                            sql.SQL(
                                "UPDATE {} SET {} = {} WHERE {} IS NULL"
                            ).format(
                                sql.Identifier(object_name),
                                sql.Identifier(field_name),
                                update_expr,
                                sql.Identifier(field_name),
                            ),
                            [],
                        )
                    )
            elif datatype == "html":
                alter_queries.append(
                    (
                        sql.SQL("ALTER TABLE {} ADD {} VARCHAR(131072)").format(
                            sql.Identifier(object_name),
                            sql.Identifier(field_name),
                        ),
                        [],
                    )
                )
            elif datatype == "checkbox":
                alter_queries.append(
                    (
                        sql.SQL("ALTER TABLE {} ADD {} BOOLEAN DEFAULT FALSE").format(
                            sql.Identifier(object_name),
                            sql.Identifier(field_name),
                        ),
                        [],
                    )
                )
            elif datatype == "date":
                alter_queries.append(
                    (
                        sql.SQL("ALTER TABLE {} ADD {} DATE").format(
                            sql.Identifier(object_name),
                            sql.Identifier(field_name),
                        ),
                        [],
                    )
                )
            elif datatype == "datetime":
                alter_queries.append(
                    (
                        sql.SQL("ALTER TABLE {} ADD {} TIMESTAMPTZ").format(
                            sql.Identifier(object_name),
                            sql.Identifier(field_name),
                        ),
                        [],
                    )
                )
            elif datatype == "time":
                alter_queries.append(
                    (
                        sql.SQL("ALTER TABLE {} ADD {} TIME").format(
                            sql.Identifier(object_name),
                            sql.Identifier(field_name),
                        ),
                        [],
                    )
                )
            elif datatype == "email":
                alter_queries.append(
                    (
                        sql.SQL("ALTER TABLE {} ADD {} email_type").format(
                            sql.Identifier(object_name),
                            sql.Identifier(field_name),
                        ),
                        [],
                    )
                )
            elif datatype == "phone":
                alter_queries.append(
                    (
                        sql.SQL("ALTER TABLE {} ADD {} phone_type").format(
                            sql.Identifier(object_name),
                            sql.Identifier(field_name),
                        ),
                        [],
                    )
                )
            elif datatype == "url":
                length = _ensure_positive_int(data.get("length"), "length", 255)
                alter_queries.append(
                    (
                        sql.SQL("ALTER TABLE {} ADD {} VARCHAR({})").format(
                            sql.Identifier(object_name),
                            sql.Identifier(field_name),
                            sql.Literal(length),
                        ),
                        [],
                    )
                )
            elif datatype in ["text", "text_area", "picklist"]:
                length = _ensure_positive_int(data.get("length"), "length", 255)
                unique_clause = " UNIQUE" if data.get("unique_field") else ""
                alter_queries.append(
                    (
                        sql.SQL("ALTER TABLE {} ADD {} VARCHAR({}){}" ).format(
                            sql.Identifier(object_name),
                            sql.Identifier(field_name),
                            sql.Literal(length),
                            sql.SQL(unique_clause),
                        ),
                        [],
                    )
                )
            elif datatype in ["json", "picklist_multi"]:
                alter_queries.append(
                    (
                        sql.SQL("ALTER TABLE {} ADD {} JSONB").format(
                            sql.Identifier(object_name),
                            sql.Identifier(field_name),
                        ),
                        [],
                    )
                )
            elif datatype in ["formula", "rollup_summary"]:
                # Read-only computed fields — no physical column on the object table.
                # Formula: value derived from a formula expression at read time.
                # Roll-Up Summary: value computed by aggregating child records at read time.
                # Metadata is stored in the fields table only.
                pass
            elif datatype == "lookup":
                alter_queries.append(
                    (
                        sql.SQL("ALTER TABLE {} ADD {} VARCHAR(64)").format(
                            sql.Identifier(object_name),
                            sql.Identifier(field_name),
                        ),
                        [],
                    )
                )
                alter_queries.append(
                    (
                        sql.SQL(
                            "ALTER TABLE {} ADD CONSTRAINT {} FOREIGN KEY ({}) REFERENCES {}.{}(id)"
                        ).format(
                            sql.Identifier(object_name),
                            sql.Identifier(f"fk_{field_name}_{parent_object}"),
                            sql.Identifier(field_name),
                            sql.Identifier(schema),
                            sql.Identifier(parent_object),
                        ),
                        [],
                    )
                )

            with connection.cursor() as cursor:
                for query, params in alter_queries:
                    cursor.execute(query, params)
        return True

    except Exception as e:
        print(f"Error: {e}")
        raise Exception(f"Error: {e}")


def update_field_in_table(schema: str, data: Dict):
    print(f"Updating field in table with schema: {schema} and data: {data}")

    try:
        schema = _validate_identifier(schema, "schema")
        table = _validate_identifier(data.get("object_name", ""), "object_name")
        old_name = _validate_identifier(data.get("old_name", ""), "old_name")
        new_name = _validate_identifier(data.get("name", ""), "name")

        with connection.cursor() as cursor:
            _set_search_path(cursor, schema)

        with transaction.atomic():
            alter_queries: List[Tuple[sql.SQL, List]] = []

            if old_name != new_name:
                alter_queries.append(
                    (
                        sql.SQL("ALTER TABLE {} RENAME COLUMN {} TO {}" ).format(
                            sql.Identifier(table),
                            sql.Identifier(old_name),
                            sql.Identifier(new_name),
                        ),
                        [],
                    )
                )

            column_name = new_name
            if data.get("datatype"):
                datatype = data["datatype"]
                if datatype == "number":
                    precision = _ensure_positive_int(data.get("number_length"), "number_length", 18)
                    scale = _ensure_positive_int(data.get("decimal_places"), "decimal_places", 0)
                    alter_queries.append(
                        (
                            sql.SQL("ALTER TABLE {} ALTER COLUMN {} TYPE NUMERIC({},{})").format(
                                sql.Identifier(table),
                                sql.Identifier(column_name),
                                sql.Literal(precision),
                                sql.Literal(scale),
                            ),
                            [],
                        )
                    )
                elif datatype in ["currency", "percent"]:
                    precision = _ensure_positive_int(data.get("number_length"), "number_length", 18)
                    scale = _ensure_positive_int(data.get("decimal_places"), "decimal_places", 0)
                    alter_queries.append(
                        (
                            sql.SQL("ALTER TABLE {} ALTER COLUMN {} TYPE NUMERIC({},{})").format(
                                sql.Identifier(table),
                                sql.Identifier(column_name),
                                sql.Literal(precision),
                                sql.Literal(scale),
                            ),
                            [],
                        )
                    )
                elif datatype in ["text", "text_area", "picklist"]:
                    length = _ensure_positive_int(data.get("length", 255), "length", 255)
                    alter_queries.append(
                        (
                            sql.SQL("ALTER TABLE {} ALTER COLUMN {} TYPE VARCHAR({})").format(
                                sql.Identifier(table),
                                sql.Identifier(column_name),
                                sql.Literal(length),
                            ),
                            [],
                        )
                    )
                elif datatype == "checkbox":
                    alter_queries.append(
                        (
                            sql.SQL(
                                "ALTER TABLE {} ALTER COLUMN {} TYPE BOOLEAN USING {}::BOOLEAN"
                            ).format(
                                sql.Identifier(table),
                                sql.Identifier(column_name),
                                sql.Identifier(column_name),
                            ),
                            [],
                        )
                    )
                elif datatype == "date":
                    alter_queries.append(
                        (
                            sql.SQL("ALTER TABLE {} ALTER COLUMN {} TYPE DATE").format(
                                sql.Identifier(table),
                                sql.Identifier(column_name),
                            ),
                            [],
                        )
                    )
                elif datatype == "datetime":
                    alter_queries.append(
                        (
                            sql.SQL("ALTER TABLE {} ALTER COLUMN {} TYPE TIMESTAMPTZ").format(
                                sql.Identifier(table),
                                sql.Identifier(column_name),
                            ),
                            [],
                        )
                    )
                elif datatype in ["json", "picklist_multi"]:
                    alter_queries.append(
                        (
                            sql.SQL(
                                "ALTER TABLE {} ALTER COLUMN {} TYPE JSONB USING {}::JSONB"
                            ).format(
                                sql.Identifier(table),
                                sql.Identifier(column_name),
                                sql.Identifier(column_name),
                            ),
                            [],
                        )
                    )
                elif datatype == "auto_number":
                    sequence = _validate_identifier(f"sequence_{new_name}_{table}", "sequence")
                    starting_number = _ensure_positive_int(data.get("starting_number"), "starting_number", 1)
                    display_format = data.get("display_format") or ""

                    m = re.fullmatch(r"([A-Za-z_]+-)\{(0+)\}", display_format)
                    if not m:
                        raise Exception(
                            f"Invalid Auto Number format: '{display_format}'. Expected format like 'ABC-{{0000}}'."
                        )
                    prefix = m.group(1)
                    zero_block = m.group(2)
                    padding_length = len(zero_block) + len(str(starting_number))

                    alter_queries.append(
                        (
                            sql.SQL("DROP SEQUENCE IF EXISTS {} CASCADE").format(
                                sql.Identifier(sequence)
                            ),
                            [],
                        )
                    )
                    alter_queries.append(
                        (
                            sql.SQL("CREATE SEQUENCE {} START WITH %s").format(
                                sql.Identifier(sequence)
                            ),
                            [starting_number],
                        )
                    )
                    default_expr = sql.SQL("{} || LPAD(nextval({})::text, {}, '0')").format(
                        sql.Literal(prefix),
                        sql.Identifier(sequence),
                        sql.Literal(padding_length),
                    )
                    alter_queries.append(
                        (
                            sql.SQL("ALTER TABLE {} ALTER COLUMN {} SET DEFAULT ({})").format(
                                sql.Identifier(table),
                                sql.Identifier(column_name),
                                default_expr,
                            ),
                            [],
                        )
                    )
                    if data.get("auto_number"):
                        update_expr = sql.SQL("{} || LPAD(nextval({})::text, {}, '0')").format(
                            sql.Literal(prefix),
                            sql.Identifier(sequence),
                            sql.Literal(padding_length),
                        )
                        alter_queries.append(
                            (
                                sql.SQL(
                                    "UPDATE {} SET {} = {} WHERE {} IS NULL"
                                ).format(
                                    sql.Identifier(table),
                                    sql.Identifier(column_name),
                                    update_expr,
                                    sql.Identifier(column_name),
                                ),
                                [],
                            )
                        )
                elif datatype == "url":
                    length = _ensure_positive_int(data.get("length"), "length", 255)
                    alter_queries.append(
                        (
                            sql.SQL("ALTER TABLE {} ALTER COLUMN {} TYPE VARCHAR({})").format(
                                sql.Identifier(table),
                                sql.Identifier(column_name),
                                sql.Literal(length),
                            ),
                            [],
                        )
                    )
                elif datatype in ["formula", "rollup_summary"]:
                    # Read-only computed fields — no physical column to alter.
                    pass

            if "default_value" in data:
                if data["default_value"] is None or data["default_value"] == "":
                    alter_queries.append(
                        (
                            sql.SQL("ALTER TABLE {} ALTER COLUMN {} DROP DEFAULT").format(
                                sql.Identifier(table),
                                sql.Identifier(column_name),
                            ),
                            [],
                        )
                    )
                else:
                    alter_queries.append(
                        (
                            sql.SQL("ALTER TABLE {} ALTER COLUMN {} SET DEFAULT %s").format(
                                sql.Identifier(table),
                                sql.Identifier(column_name),
                            ),
                            [data["default_value"]],
                        )
                    )

            constraint_name = _validate_identifier(f"unq_{table}_{column_name}", "constraint_name")
            if "unique_field" in data:
                if data["unique_field"]:
                    alter_queries.append(
                        (
                            sql.SQL("ALTER TABLE {} DROP CONSTRAINT IF EXISTS {}").format(
                                sql.Identifier(table),
                                sql.Identifier(constraint_name),
                            ),
                            [],
                        )
                    )
                    alter_queries.append(
                        (
                            sql.SQL("ALTER TABLE {} ADD CONSTRAINT {} UNIQUE ({})").format(
                                sql.Identifier(table),
                                sql.Identifier(constraint_name),
                                sql.Identifier(column_name),
                            ),
                            [],
                        )
                    )
                else:
                    alter_queries.append(
                        (
                            sql.SQL("ALTER TABLE {} DROP CONSTRAINT IF EXISTS {}").format(
                                sql.Identifier(table),
                                sql.Identifier(constraint_name),
                            ),
                            [],
                        )
                    )

            with connection.cursor() as cursor:
                for query, params in alter_queries:
                    cursor.execute(query, params)
        return True
    except Exception as e:
        print(f"Error: {e}")
        raise Exception(f"Error: {e}")