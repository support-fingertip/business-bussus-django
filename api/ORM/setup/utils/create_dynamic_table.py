import re


# Allowed identifier characters — used to whitelist schema/table/prefix inputs
_IDENTIFIER_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _validate_identifier(value, label):
    """Raise ValueError if value is not a safe SQL identifier."""
    if not value or not _IDENTIFIER_RE.match(value):
        raise ValueError(
            f"Invalid {label} '{value}'. "
            "Only letters, digits, and underscores are allowed, and it must not start with a digit."
        )


def create_dynamic_table(cursor, schema_name, table_name, prefix, datatype, display_format, starting_number):

    # ── 1. SQL INJECTION — validate every identifier used in DDL ──────────────
    _validate_identifier(schema_name, "schema_name")
    _validate_identifier(table_name,  "table_name")
    _validate_identifier(prefix,      "prefix")

    full_table_name = f"{schema_name}.{table_name}"
    sequence_name   = f"{schema_name}.sequence_{table_name}"
    name_unique_sql = "" if str(table_name).lower() == "leads" else " UNIQUE"

    name_default = ""

    if datatype in ["auto_number", "number"]:
        starting_number = int(starting_number) if starting_number else 1

        m = re.fullmatch(r"([A-Za-z]+-)\{(0+)\}", display_format or "")
        if not m:
            raise ValueError(
                f"Invalid Auto Number format: '{display_format}'. "
                "Expected format like 'ABC-{0000}'."
            )

        prefix      = m.group(1)   # e.g. "ABC-"
        zero_block  = m.group(2)   # e.g. "0000"
        # FIX: pad width is just the number of zeros — not zeros + digits of start
        padding_length = len(zero_block)
        create_sequence_sql = f"""
        CREATE SEQUENCE IF NOT EXISTS {sequence_name} START WITH {starting_number};
        ALTER SEQUENCE {sequence_name} RESTART WITH {starting_number};
        """
        cursor.execute(create_sequence_sql)

        name_default = (
            f" DEFAULT ('{prefix}' || "
            f"LPAD(nextval('{sequence_name}')::text, {padding_length}, '0'))"
        )
    create_sql = f"""
    CREATE TABLE IF NOT EXISTS {full_table_name} (
        id                   VARCHAR(64) PRIMARY KEY DEFAULT CONCAT('{prefix}_', LEFT(gen_random_uuid()::text, 12)),
        name                 VARCHAR(255) NOT NULL{name_default}{name_unique_sql},
        created_date         TIMESTAMP DEFAULT NOW(),
        last_modified_date   TIMESTAMP DEFAULT NOW(),
        deleted_date         TIMESTAMP DEFAULT NULL,
        is_deleted           BOOLEAN DEFAULT FALSE,
        deleted_by_id        VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
        created_by_id        VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
        last_modified_by_id  VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
        owner_id             VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
        recently_viewed      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """
    cursor.execute(create_sql)