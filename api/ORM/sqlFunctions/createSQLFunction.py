import uuid
import re
from django.db import connection, transaction
from psycopg2 import sql
from psycopg2.extras import execute_values
from datetime import datetime, date, time
from dateutil import parser
from django.utils import timezone
from zoneinfo import ZoneInfo
import json
from api.ORM.AuditLogs.audit_trail_logs import log_audit
from api.ORM.sqlFunctions.utils.error_handlers import explain_db_error
from api.ORM.sqlFunctions.utils.helpers import validate_identifier
from api.security.schema_authority import get_validated_schema
from psycopg2.extensions import cursor as PgCursor


def _normalize_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _normalize_email(value):
    return _normalize_text(value).lower()


def _normalize_phone(value):
    return re.sub(r'\D', '', _normalize_text(value))


def validate_lead_name_contact_uniqueness(cursor, lead_item, table_column_map, table_name='leads', exclude_id=None):
    """
    Enforce rule for leads:
      - name can repeat
      - for same name, email and phone must each be unique
    """
    if table_name != 'leads' or not isinstance(lead_item, dict):
        return None

    def resolve(*candidates):
        for candidate in candidates:
            resolved = table_column_map.get(str(candidate).lower())
            if resolved:
                return resolved
        return None

    name_col = resolve('name', 'full_name', 'first_name')
    email_col = resolve('email')
    phone_col = resolve('phone', 'contact_number', 'mobile', 'mobile_number')
    is_deleted_col = resolve('is_deleted')

    if not name_col:
        return None

    name_value = _normalize_text(lead_item.get(name_col))
    email_value = _normalize_email(lead_item.get(email_col)) if email_col else ""
    phone_value = _normalize_phone(lead_item.get(phone_col)) if phone_col else ""

    if not name_value or (not email_value and not phone_value):
        return None

    conditions = [
        sql.SQL("LOWER(TRIM(COALESCE({}::text, ''))) = LOWER(TRIM(%s))").format(sql.Identifier(name_col))
    ]
    params = [name_value]

    dup_subconditions = []
    if email_col and email_value:
        dup_subconditions.append(
            sql.SQL("LOWER(TRIM(COALESCE({}::text, ''))) = LOWER(TRIM(%s))").format(sql.Identifier(email_col))
        )
        params.append(email_value)

    if phone_col and phone_value:
        dup_subconditions.append(
            sql.SQL("regexp_replace(COALESCE({}::text, ''), '\\D', '', 'g') = regexp_replace(%s, '\\D', '', 'g')").format(
                sql.Identifier(phone_col)
            )
        )
        params.append(phone_value)

    if not dup_subconditions:
        return None

    conditions.append(
        sql.SQL("(") + sql.SQL(" OR ").join(dup_subconditions) + sql.SQL(")")
    )

    if is_deleted_col:
        conditions.append(
            sql.SQL("COALESCE({}, false) = false").format(sql.Identifier(is_deleted_col))
        )

    if exclude_id is not None:
        conditions.append(sql.SQL("id <> %s"))
        params.append(exclude_id)

    duplicate_query = sql.SQL("SELECT id, {}, {} FROM {} WHERE {} LIMIT 1").format(
        sql.Identifier(email_col) if email_col else sql.SQL("NULL"),
        sql.Identifier(phone_col) if phone_col else sql.SQL("NULL"),
        sql.Identifier(table_name),
        sql.SQL(" AND ").join(conditions),
    )

    cursor.execute(duplicate_query, params)
    duplicate_row = cursor.fetchone()
    if not duplicate_row:
        return None

    existing_email = _normalize_email(duplicate_row[1]) if email_col else ""
    existing_phone = _normalize_phone(duplicate_row[2]) if phone_col else ""

    same_email = bool(email_value and existing_email and email_value == existing_email)
    same_phone = bool(phone_value and existing_phone and phone_value == existing_phone)

    if same_email and same_phone:
        return "For the same lead name, this email and phone already exist."
    if same_email:
        return "For the same lead name, this email already exists."
    if same_phone:
        return "For the same lead name, this phone already exists."
    return "For the same lead name, email or phone already exists."


def batch_lead_uniqueness_errors(cursor, rows, table_column_map, table_name='leads'):
    """Bulk-equivalent of validate_lead_name_contact_uniqueness — one query
    for the whole chunk instead of N. Returns a dict {idx: error_message}.

    Detects both DB conflicts and duplicates within the same import batch.
    """
    if table_name != 'leads' or not rows:
        return {}

    def resolve(*candidates):
        for candidate in candidates:
            resolved = table_column_map.get(str(candidate).lower())
            if resolved:
                return resolved
        return None

    name_col = resolve('name', 'full_name', 'first_name')
    email_col = resolve('email')
    phone_col = resolve('phone', 'contact_number', 'mobile', 'mobile_number')
    is_deleted_col = resolve('is_deleted')
    if not name_col:
        return {}

    # Compute a normalized signature per row; rows missing both email and
    # phone are skipped (matches the per-row function's early return).
    signatures = []  # list of (idx, name, email, phone)
    names_lower = set()
    for idx, row in rows:
        name_v = _normalize_text(row.get(name_col))
        email_v = _normalize_email(row.get(email_col)) if email_col else ""
        phone_v = _normalize_phone(row.get(phone_col)) if phone_col else ""
        if not name_v or (not email_v and not phone_v):
            continue
        signatures.append((idx, name_v, email_v, phone_v))
        names_lower.add(name_v.lower())

    if not signatures:
        return {}

    # Pull every existing lead whose (lowercased, trimmed) name matches any
    # name in our chunk, plus its email and phone. One query, fully indexed
    # if there's an index on lower(name).
    select_cols = [sql.Identifier(name_col)]
    if email_col:
        select_cols.append(sql.Identifier(email_col))
    if phone_col:
        select_cols.append(sql.Identifier(phone_col))

    where = [sql.SQL("LOWER(TRIM(COALESCE({}::text, ''))) = ANY(%s)").format(sql.Identifier(name_col))]
    params = [list(names_lower)]
    if is_deleted_col:
        where.append(sql.SQL("COALESCE({}, false) = false").format(sql.Identifier(is_deleted_col)))

    q = sql.SQL("SELECT {} FROM {} WHERE {}").format(
        sql.SQL(", ").join(select_cols),
        sql.Identifier(table_name),
        sql.SQL(" AND ").join(where),
    )
    cursor.execute(q, params)
    existing_email_keys = set()  # (name_lower, email_lower)
    existing_phone_keys = set()  # (name_lower, phone_normalized)
    for db_row in cursor.fetchall():
        db_name = _normalize_text(db_row[0])
        db_email = _normalize_email(db_row[1]) if email_col else ""
        db_phone = _normalize_phone(db_row[2 if email_col else 1]) if phone_col else ""
        n = db_name.lower() if db_name else ""
        if db_email:
            existing_email_keys.add((n, db_email))
        if db_phone:
            existing_phone_keys.add((n, db_phone))

    errors = {}
    seen_email_keys = set()
    seen_phone_keys = set()
    for idx, name_v, email_v, phone_v in signatures:
        n = name_v.lower()
        same_email = bool(email_v and ((n, email_v) in existing_email_keys or (n, email_v) in seen_email_keys))
        same_phone = bool(phone_v and ((n, phone_v) in existing_phone_keys or (n, phone_v) in seen_phone_keys))
        if same_email and same_phone:
            errors[idx] = "For the same lead name, this email and phone already exist."
        elif same_email:
            errors[idx] = "For the same lead name, this email already exists."
        elif same_phone:
            errors[idx] = "For the same lead name, this phone already exists."
        if email_v:
            seen_email_keys.add((n, email_v))
        if phone_v:
            seen_phone_keys.add((n, phone_v))
    return errors


def ensure_leads_name_not_unique(cursor, schema='public', table_name='leads'):
    """Drop legacy unique constraints/indexes on leads.name so lead-name duplicates are allowed."""
    if table_name != 'leads':
        return

    validate_identifier(schema)
    validate_identifier(table_name)

    cursor.execute(
        """
        SELECT c.conname
        FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN unnest(c.conkey) AS k(attnum) ON TRUE
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = k.attnum
        WHERE c.contype = 'u'
          AND n.nspname = %s
          AND t.relname = %s
        GROUP BY c.conname
        HAVING count(*) = 1 AND max(a.attname) = 'name'
        """,
        [schema, table_name]
    )
    unique_constraints = [row[0] for row in cursor.fetchall()]
    for constraint_name in unique_constraints:
        cursor.execute(
            sql.SQL("ALTER TABLE {} DROP CONSTRAINT IF EXISTS {}").format(
                sql.Identifier(table_name),
                sql.Identifier(constraint_name)
            )
        )

    cursor.execute(
        """
        SELECT i.relname
        FROM pg_class t
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_index ix ON ix.indrelid = t.oid
        JOIN pg_class i ON i.oid = ix.indexrelid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(ix.indkey)
        WHERE n.nspname = %s
          AND t.relname = %s
          AND ix.indisunique = true
          AND ix.indisprimary = false
        GROUP BY i.relname, ix.indnatts
        HAVING ix.indnatts = 1 AND max(a.attname) = 'name'
        """,
        [schema, table_name]
    )
    unique_indexes = [row[0] for row in cursor.fetchall()]
    for index_name in unique_indexes:
        cursor.execute(
            sql.SQL("DROP INDEX IF EXISTS {}.{}").format(
                sql.Identifier(schema),
                sql.Identifier(index_name)
            )
        )


def get_array_columns(cursor, table_name, schema='public'):
    query = """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = %s AND data_type = 'ARRAY' AND table_schema = %s
    """
    cursor.execute(query, [table_name, schema])
    return [row[0] for row in cursor.fetchall()]

def get_required_fields(cursor, table_name, schema='public'):
    try:
        cursor.execute(
            "SELECT name FROM fields WHERE object_name = %s AND required = true",
            [table_name]
        )
        return [row[0] for row in cursor.fetchall()]
    except Exception:
        return []

def find_missing_required(cleaned_item, required_fields):
    missing = []
    for field in required_fields:
        value = cleaned_item.get(field)
        if value is None:
            missing.append(field)
        elif isinstance(value, str) and value.strip() == "":
            missing.append(field)
        elif isinstance(value, (list, dict)) and len(value) == 0:
            missing.append(field)
    return missing

def get_picklist_fields(cursor, table_name, schema='public'):
    try:
        cursor.execute(
            """
            SELECT name, pickup_values, datatype
            FROM fields
            WHERE object_name = %s AND datatype IN ('picklist', 'multi_picklist')
            """,
            [table_name]
        )
        rows = cursor.fetchall()
    except Exception:
        return {}

    picklist_map = {}
    for name, pickup_values, datatype in rows:
        values = []
        if isinstance(pickup_values, list):
            values = pickup_values
        elif isinstance(pickup_values, str):
            try:
                parsed = json.loads(pickup_values)
            except Exception:
                parsed = [v.strip() for v in pickup_values.split(',') if v.strip()]
            if isinstance(parsed, list):
                values = parsed
            elif isinstance(parsed, dict):
                values = list(parsed.keys())
            elif parsed is not None:
                values = [str(parsed)]
        picklist_map[name] = {
            "values": values,
            "datatype": datatype
        }
    return picklist_map

def validate_picklist_value(value, allowed, datatype):
    if value is None:
        return []
    if isinstance(value, str) and value.strip() == "":
        return []

    if datatype == 'multi_picklist':
        if isinstance(value, str):
            separator = ';' if ';' in value else ','
            items = [v.strip() for v in value.split(separator) if v.strip()]
        elif isinstance(value, list):
            items = value
        else:
            items = [value]
        return [v for v in items if v not in allowed]

    return [] if value in allowed else [value]

def validate_picklist_record(item, picklist_map):
    errors = []
    for field, meta in picklist_map.items():
        if field not in item:
            continue
        invalid = validate_picklist_value(item.get(field), meta.get("values", []), meta.get("datatype"))
        if invalid:
            errors.append({
                "field": field,
                "invalid": invalid,
                "allowed": meta.get("values", [])
            })
    return errors

def format_picklist_error(errors):
    if not errors:
        return None
    if len(errors) == 1:
        err = errors[0]
        invalid_text = ", ".join([str(v) for v in err.get("invalid", [])])
        allowed_text = ", ".join([str(v) for v in err.get("allowed", [])])
        if allowed_text:
            return f"{err.get('field')} has invalid value: {invalid_text}. Allowed: {allowed_text}."
        return f"{err.get('field')} has invalid value: {invalid_text}."
    fields_text = ", ".join([err.get("field") for err in errors])
    return f"Invalid picklist values for: {fields_text}."

def validate_email_format(email):
    """Check if email has valid format: must have @ and proper domain."""
    if not email or not isinstance(email, str):
        return False
    email = email.strip()
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_data_type(field_name, value, field_datatype):
    """Validate if value matches the app-level field datatype from 'fields' table."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return None  # NULL is ok, will be caught by NOT NULL constraint

    value_str = str(value).strip()
    dt = (field_datatype or "").lower()
    
    # Numeric types: number, currency, percent
    if dt in ('number', 'currency', 'percent', 'integer', 'numeric', 'decimal', 'bigint', 'smallint', 'real', 'double precision'):
        try:
            float(value_str)
            return None  # Valid number
        except ValueError:
            return f"Expected numeric value but got '{value_str}'"
    
    
    
    # Email field
    if dt == 'email' or 'email' in field_name.lower():
        if value and not validate_email_format(value_str):
            return f"Invalid email format: '{value_str}'"
    
    # Date/timestamp types
    if dt in ('date', 'datetime', 'timestamp', 'time'):
        try:
            if isinstance(value, str) and ('T' in value or '-' in value):
                from dateutil import parser
                parser.parse(value_str)
            return None
        except Exception:
            try:
                datetime.strptime(value_str, '%Y-%m-%d')
                return None
            except ValueError:
                return f"Invalid date/time format: '{value_str}'"
    
    return None

 

def validate_data_types_record(item, type_map):
    """Validate data types for all fields in a record."""
    errors = []
    for field, value in item.items():
        pg_type = type_map.get(field)
        if not pg_type:
            continue
        error = validate_data_type(field, value, pg_type)
        if error:
            errors.append(f"{field}: {error}")
    return errors

def get_lookup_fields(cursor, table_name, schema='public'):
    try:
        cursor.execute(
            """
            SELECT name, parent_object, required
            FROM fields
            WHERE object_name = %s AND datatype IN ('lookup', 'lookup_relationship')
            """,
            [table_name]
        )
        rows = cursor.fetchall()
    except Exception as e:
        print(f"Error fetching lookup fields for table {table_name}: {e}")
        return []

    lookups = []
    for name, parent_object, required in rows:
        if not parent_object:
            continue
        lookups.append({
            "name": name,
            "parent_object": parent_object,
            "required": required
        })
    return lookups

def extract_lookup_value(value):
    if isinstance(value, dict):
        if "id" in value:
            return value.get("id")
        if "name" in value:
            return value.get("name")
    return value

def normalize_parent_table(parent_object):
    if parent_object == 'user':
        return 'users'
    return parent_object

def resolve_lookup_value(cursor, parent_table, raw_value):
    value = extract_lookup_value(raw_value)
    if value is None:
        return None, None
    if isinstance(value, str) and value.strip() == "":
        return None, None
    if isinstance(value, (list, dict)):
        return None, "Invalid lookup value"

    cursor.execute(
        sql.SQL("SELECT id FROM {} WHERE id = %s").format(sql.Identifier(parent_table)),
        [value]
    )
    row = cursor.fetchone()
    if row:
        return row[0], None

    cursor.execute(
        sql.SQL("SELECT id FROM {} WHERE name = %s").format(sql.Identifier(parent_table)),
        [value]
    )
    rows = cursor.fetchall()
    if not rows:
        return None, "Reference not found"
    if len(rows) > 1:
        return None, "Multiple records found for name"
    return rows[0][0], None

def validate_and_resolve_lookups(item, lookup_fields, cursor):
    errors = []
    updated = item.copy()
    for field in lookup_fields:
        field_name = field.get("name")
        required = field.get("required")
        parent_object = field.get("parent_object")
        if field_name not in updated:
            continue
        raw_value = updated.get(field_name)
        if raw_value is None or (isinstance(raw_value, str) and raw_value.strip() == ""):
            if required:
                errors.append(f"{field_name} is required.")
            continue

        parent_table = normalize_parent_table(parent_object)
        try:
            validate_identifier(parent_table)
        except Exception:
            errors.append(f"{field_name} lookup table is invalid.")
            continue

        try:
            resolved_id, error = resolve_lookup_value(cursor, parent_table, raw_value)
        except Exception:
            errors.append(f"{field_name} lookup resolution failed.")
            continue

        if error:
            if error == "Multiple records found for name":
                errors.append(f"{field_name} has multiple matches for name.")
            elif error == "Reference not found":
                errors.append(f"{field_name} reference not found.")
            else:
                errors.append(f"{field_name} has invalid value.")
            continue

        updated[field_name] = resolved_id
    return updated, errors


def build_lookup_cache(cursor, lookup_fields, cleaned_data):
    """
    Collect all FK raw values across a chunk and resolve them with one
    SELECT per parent table — collapsing N_rows * N_fk_fields * 2 queries
    into at most N_parent_tables queries.
    """
    if not lookup_fields or not cleaned_data:
        return {}

    fields_by_parent = {}
    for field in lookup_fields:
        parent_object = field.get("parent_object")
        field_name = field.get("name")
        if not parent_object or not field_name:
            continue
        parent_table = normalize_parent_table(parent_object)
        try:
            validate_identifier(parent_table)
        except Exception:
            continue
        fields_by_parent.setdefault(parent_table, []).append(field_name)

    cache = {}
    for parent_table, field_names in fields_by_parent.items():
        values = set()
        for row in cleaned_data:
            for fname in field_names:
                if fname not in row:
                    continue
                v = extract_lookup_value(row[fname])
                if v is None:
                    continue
                if isinstance(v, str) and v.strip() == "":
                    continue
                if isinstance(v, (list, dict)):
                    continue
                values.add(str(v))

        if not values:
            cache[parent_table] = {"ids": set(), "by_name": {}, "failed": False}
            continue

        try:
            value_list = list(values)
            cursor.execute(
                sql.SQL(
                    "SELECT id::text AS id, name FROM {} "
                    "WHERE id::text = ANY(%s) OR name = ANY(%s)"
                ).format(sql.Identifier(parent_table)),
                [value_list, value_list],
            )
            rows = cursor.fetchall()
            ids = set()
            by_name = {}
            for row_id, row_name in rows:
                ids.add(str(row_id))
                if row_name is not None:
                    by_name.setdefault(row_name, []).append(str(row_id))
            cache[parent_table] = {"ids": ids, "by_name": by_name, "failed": False}
        except Exception:
            # Flag as failed so callers fall back to per-row resolution.
            cache[parent_table] = {"ids": set(), "by_name": {}, "failed": True}

    return cache


def validate_and_resolve_lookups_cached(item, lookup_fields, cache, cursor):
    """
    Same semantics as validate_and_resolve_lookups, but reads resolved IDs
    from a pre-built per-chunk cache. Falls back to per-row SELECTs for any
    parent table whose batched query failed.
    """
    errors = []
    updated = item.copy()
    for field in lookup_fields:
        field_name = field.get("name")
        required = field.get("required")
        parent_object = field.get("parent_object")
        if field_name not in updated:
            continue
        raw_value = updated.get(field_name)
        if raw_value is None or (isinstance(raw_value, str) and raw_value.strip() == ""):
            if required:
                errors.append(f"{field_name} is required.")
            continue

        parent_table = normalize_parent_table(parent_object)
        try:
            validate_identifier(parent_table)
        except Exception:
            errors.append(f"{field_name} lookup table is invalid.")
            continue

        entry = cache.get(parent_table)
        if not entry or entry.get("failed"):
            try:
                resolved_id, error = resolve_lookup_value(cursor, parent_table, raw_value)
            except Exception:
                errors.append(f"{field_name} lookup resolution failed.")
                continue
            if error:
                if error == "Multiple records found for name":
                    errors.append(f"{field_name} has multiple matches for name.")
                elif error == "Reference not found":
                    errors.append(f"{field_name} reference not found.")
                else:
                    errors.append(f"{field_name} has invalid value.")
                continue
            updated[field_name] = resolved_id
            continue

        value = extract_lookup_value(raw_value)
        if value is None:
            continue
        if isinstance(value, str) and value.strip() == "":
            continue
        if isinstance(value, (list, dict)):
            errors.append(f"{field_name} has invalid value.")
            continue

        value_str = str(value)
        if value_str in entry["ids"]:
            updated[field_name] = value_str
            continue

        name_match = entry["by_name"].get(value_str)
        if not name_match:
            errors.append(f"{field_name} reference not found.")
            continue
        if len(name_match) > 1:
            errors.append(f"{field_name} has multiple matches for name.")
            continue
        updated[field_name] = name_match[0]

    return updated, errors

# def generate_id(prefix):
#     return f"{prefix}_{uuid.uuid4().hex[:9]}"

def insert_related_child_records(cursor:PgCursor, parent_table, parent_id, child_tables, user=None, **kwargs):
    schema = (get_validated_schema(kwargs) or 'public')
    for child_info in child_tables:
        child_table = child_info.get("table")
        records = child_info.get("records", [])
        if not child_table or not records:
            continue

        # Identify the parent ID field based on parent table
        parent_id_field = f"{parent_table}_id"  # e.g., usergroup_id

        for record in records:
            record[parent_id_field] = parent_id  # Set foreign key
            # Get table columns and types
            cursor.execute("""
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = %s AND table_schema = %s
            """, [child_table, schema])
            columns_info = cursor.fetchall()
            table_columns = [col[0] for col in columns_info]
            type_map = {col[0]: col[1] for col in columns_info}
            array_columns = get_array_columns(cursor, child_table, schema)

            now = datetime.utcnow()
            if 'created_date' in table_columns:
                record.setdefault('created_date', now)
            if 'last_modified_date' in table_columns:
                record.setdefault('last_modified_date', now)
            if 'author_id' in table_columns and user and hasattr(user, 'id'):
                record.setdefault('author_id', user.id)
            if 'created_by_id' in table_columns:
                record.setdefault('created_by_id', user.get('id'))
            if 'last_modified_by_id' in table_columns:
                record.setdefault('last_modified_by_id', user.get('id'))
            if 'owner_id' in table_columns:
                record.setdefault('owner_id', user.get('id'))
            if 'organization_id' in table_columns:
                record.setdefault('organization_id', kwargs.get('org', {}).get('id', None))
            cleaned_item = {}
            for key, value in record.items():
                if key not in table_columns:
                    continue
                col_type = type_map.get(key)
                if col_type in ['json', 'jsonb']:
                    cleaned_item[key] = json.dumps(value)
                elif isinstance(value, list):
                    if key in array_columns:
                        cleaned_item[key] = value
                    else:
                        cleaned_item[key] = json.dumps(value)
                elif isinstance(value, dict):
                    cleaned_item[key] = json.dumps(value)
                else:
                    cleaned_item[key] = value
            columns = list(cleaned_item.keys())
            values = [cleaned_item[col] for col in columns]

            print("Values for child table",values)

            cursor.execute("SHOW search_path;")
            data = cursor.fetchone()
            print(data,"Record")

            query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
                sql.Identifier(child_table),
                sql.SQL(', ').join(map(sql.Identifier, columns)),
                sql.SQL(', ').join(sql.Placeholder() * len(values))
            )
            cursor.execute(query, values)

def get_field_type_map(cursor, table_name):
    """Fetch app-level field datatypes from the 'fields' table."""
    try:
        cursor.execute(
            "SELECT name, datatype FROM fields WHERE object_name = %s",
            [table_name]
        )
        return {row[0]: row[1] for row in cursor.fetchall()}
    except Exception:
        return {}

def post_data_sql(table_name, data, prefix='GEN', section=None, **kwargs):
    user = kwargs.get('user_')
    schema = get_validated_schema(kwargs)
    # Only run lookup validation for object-level calls (not setup APIs)
    enable_lookup_validation = kwargs.get('enable_lookup_validation', False)
    if not schema:
        raise ValueError("Invalid user request: 'schema' is required in kwargs")
    
    # Validate schema name
    validate_identifier(schema)
    validate_identifier(table_name)
    
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                # Use SET LOCAL within transaction for search_path
                cursor.execute("SET search_path TO %s", [schema])

                now = timezone.now()
                is_bulk = isinstance(data, list) and all("child_tables" not in item for item in data)
                
                # Fetch column info once
                cursor.execute("""
                    SELECT column_name, data_type
                    FROM information_schema.columns
                    WHERE table_name = %s AND table_schema = %s
                """, [table_name, schema])
                columns_info = cursor.fetchall()
                table_columns = [col[0] for col in columns_info]
                table_column_map = {str(col).lower(): col for col in table_columns}
                type_map = {col[0]: col[1] for col in columns_info}

                if table_name == 'leads' and 'company' not in table_column_map:
                    cursor.execute(
                        sql.SQL("ALTER TABLE {} ADD COLUMN {} VARCHAR(255)").format(
                            sql.Identifier(table_name),
                            sql.Identifier('company')
                        )
                    )
                    cursor.execute("""
                        SELECT column_name, data_type
                        FROM information_schema.columns
                        WHERE table_name = %s AND table_schema = %s
                    """, [table_name, schema])
                    columns_info = cursor.fetchall()
                    table_columns = [col[0] for col in columns_info]
                    table_column_map = {str(col).lower(): col for col in table_columns}
                    type_map = {col[0]: col[1] for col in columns_info}

                if table_name == 'leads':
                    ensure_leads_name_not_unique(cursor, schema=schema, table_name=table_name)

                array_columns = get_array_columns(cursor, table_name, schema)
                required_fields = get_required_fields(cursor, table_name, schema)
                def resolve_column_name(field_name):
                    if field_name is None:
                        return None
                    return table_column_map.get(str(field_name).lower())

                if table_name == 'leads':
                    mobile_field = resolve_column_name('phone') or resolve_column_name('contact_number')
                    lead_required_fields = [
                        resolve_column_name('status'),
                        resolve_column_name('company'),
                        resolve_column_name('email'),
                    ]
                    if mobile_field:
                        lead_required_fields.append(mobile_field)
                    for field_name in lead_required_fields:
                        if field_name and field_name not in required_fields:
                            required_fields.append(field_name)
                picklist_map = get_picklist_fields(cursor, table_name, schema)
                field_type_map = get_field_type_map(cursor, table_name)
                # Only fetch lookup fields for object-level inserts
                lookup_fields = get_lookup_fields(cursor, table_name, schema) if enable_lookup_validation else []
                
                def clean_record(item):
                    item = item.copy()
                    status_column = resolve_column_name('status')
                    if table_name == 'leads':
                        status_value = item.get(status_column) if status_column else item.get('status')
                        if status_value is None or (isinstance(status_value, str) and status_value.strip() == ""):
                            if status_column:
                                item[status_column] = 'Open - Not Contacted'
                            else:
                                item['status'] = 'Open - Not Contacted'

                    created_date_col = resolve_column_name('created_date')
                    last_modified_date_col = resolve_column_name('last_modified_date')
                    last_login_col = resolve_column_name('last_login')
                    author_col = resolve_column_name('author_id')
                    created_by_col = resolve_column_name('created_by_id')
                    last_modified_by_col = resolve_column_name('last_modified_by_id')
                    owner_col = resolve_column_name('owner_id')
                    organization_col = resolve_column_name('organization_id')
                    # start_time_col = resolve_column_name('start_time')
                    # end_time_col = resolve_column_name('end_time')
                    if created_date_col:
                        item.setdefault(created_date_col, now)
                    if last_modified_date_col:
                        item.setdefault(last_modified_date_col, now)
                    if table_name == 'users' and last_login_col:
                        item.setdefault(last_login_col, now)
                    # if table_name == 'events' and start_time_col:
                    #     item.setdefault(start_time_col, now)
                    # if table_name == 'events' and end_time_col:
                    #     item.setdefault(end_time_col, now)
                    if author_col and user and hasattr(user, 'id'):
                        item.setdefault(author_col, user.get('id'))
                    if created_by_col:
                        item.setdefault(created_by_col, user.get('id'))
                    if last_modified_by_col:
                        item.setdefault(last_modified_by_col, user.get('id'))
                    if owner_col:
                        item.setdefault(owner_col, user.get('id'))
                    if organization_col:
                        item.setdefault(organization_col, kwargs.get('org', {}).get('id', None))
                    if table_name == 'visit':
                        visit_time_col = resolve_column_name('visit_time')
                        if visit_time_col:
                            item.setdefault(visit_time_col, now)
                    cleaned = {}
                    # ── helper defined ONCE, outside the loop ─────────────────────────────────────
                    def _to_db_datetime(dt_obj: datetime) -> datetime:
                        from datetime import timezone as dt_timezone
                        # Always store as UTC-aware. The event table uses TIMESTAMP (without TZ)
                        # columns; storing an IST-aware value causes PostgreSQL to convert it to
                        # the session timezone (UTC) anyway, resulting in a naive UTC value in the
                        # DB. Keeping UTC here makes the intent clear and avoids a round-trip
                        # through IST that was previously cancelling itself out.
                        if timezone.is_naive(dt_obj):
                            return dt_obj.replace(tzinfo=dt_timezone.utc)
                        return dt_obj.astimezone(dt_timezone.utc)
                    for key, value in item.items():
                        resolved_key = resolve_column_name(key)
                        if not resolved_key:
                            continue
                        col_type = type_map.get(resolved_key)
                        dtype = field_type_map.get(resolved_key)
                        if col_type in ['json', 'jsonb']:
                            cleaned[resolved_key] = json.dumps(value)
                        elif isinstance(value, list):
                            cleaned[resolved_key] = value if resolved_key in array_columns else json.dumps(value)
                        elif isinstance(value, dict):
                            cleaned[resolved_key] = json.dumps(value)

                        # ── inside your loop ──────────────────────────────────────────────────────────
                        elif dtype in ['date', 'datetime', 'timestamp', 'time'] or (
                            col_type and any(t in col_type.lower() for t in ['date', 'time', 'timestamp'])
                        ):
                            target_kind = (dtype or col_type or '').lower()

                            # Classify once, clearly — fixes the startswith('time') trap that
                            # matched 'timestamp' and routed it to .time() instead of _to_db_datetime()
                            is_date_only    = target_kind == 'date' or (col_type or '').lower().strip() == 'date'
                            is_time_only    = target_kind == 'time'
                            is_datetime_ish = not is_date_only and not is_time_only  # datetime / timestamp / timestamp tz

                            if isinstance(value, str):
                                trimmed = value.strip()
                                if not trimmed:
                                    cleaned[resolved_key] = None
                                    continue

                                dt = None
                                # dateutil first; fromisoformat as fallback for strict ISO-only values
                                try:
                                    dt = parser.parse(trimmed)
                                except Exception:
                                    try:
                                        dt = datetime.fromisoformat(trimmed)
                                    except Exception:
                                        cleaned[resolved_key] = trimmed   # unparseable — pass through as-is
                                        continue

                                if is_date_only:
                                    cleaned[resolved_key] = dt.date()
                                elif is_time_only:
                                    cleaned[resolved_key] = dt.time()
                                else:
                                    cleaned[resolved_key] = _to_db_datetime(dt)

                            # FIX: check datetime BEFORE date — datetime is a subclass of date in Python
                            # if you check `isinstance(value, date)` first, datetime objects fall into it too
                            elif isinstance(value, datetime):
                                if is_date_only:
                                    cleaned[resolved_key] = value.date()
                                elif is_time_only:
                                    cleaned[resolved_key] = value.time()
                                else:
                                    cleaned[resolved_key] = _to_db_datetime(value)

                            elif isinstance(value, date):          # pure date, not datetime
                                if is_date_only:
                                    cleaned[resolved_key] = value
                                else:
                                    # promote date → datetime at midnight so _to_db_datetime can make it aware
                                    cleaned[resolved_key] = _to_db_datetime(datetime(value.year, value.month, value.day))

                            elif isinstance(value, time):
                                if is_time_only:
                                    cleaned[resolved_key] = value
                                else:
                                    cleaned[resolved_key] = value  # best-effort passthrough

                            else:
                                cleaned[resolved_key] = value

                        else:
                            cleaned[resolved_key] = value
                    return cleaned
                
                results = []
                if is_bulk:
                    report = bulk_insert_with_report(
                        cursor=cursor,
                        table_name=table_name,
                        raw_data=data,
                        clean_record=clean_record,
                        returning_cols=("id",),
                        required_fields=required_fields,
                        picklist_map=picklist_map,
                        type_map=field_type_map,
                        lookup_fields=lookup_fields,
                        table_column_map=table_column_map,
                        **kwargs
                    )
                    return report
                    
                else:
                    # Fallback to single inserts (needed if child_tables or RETURNING)
                    if not isinstance(data, list):
                        data = [data]

                    for item in data:
                        item = item.copy()
                        child_tables = item.pop("child_tables", [])
                        cleaned_item = clean_record(item)

                        missing_required = find_missing_required(cleaned_item, required_fields)
                        if missing_required:
                            # Friendly message when telephony is not configured for calls
                            if table_name == "call" and "telephony_id" in missing_required:
                                return {
                                    "status": "error",
                                    "success": False,
                                    "error": {
                                        "message": "Please setup telephony to make calls.",
                                        "fields": missing_required,
                                    }
                                }
                            missing_text = ", ".join(missing_required)
                            return {
                                "status": "error",
                                "success": False,
                                "error": {
                                    "message": f"{missing_text} is required." if len(missing_required) == 1 else f"{missing_text} are required.",
                                    "fields": missing_required,
                                }
                            }

                        picklist_errors = validate_picklist_record(item, picklist_map)
                        if picklist_errors:
                            return {
                                "status": "error",
                                "success": False,
                                "error": {
                                    "message": format_picklist_error(picklist_errors),
                                    "fields": [err.get("field") for err in picklist_errors],
                                }
                            }

                        # Validate data types and email formats
                        datatype_errors = validate_data_types_record(item, field_type_map)
                        if datatype_errors:
                            return {
                                "status": "error",
                                "success": False,
                                "error": {
                                    "message": " | ".join(datatype_errors),
                                    "fields": [e.split(":")[0] for e in datatype_errors],
                                }
                            }

                        # Validate and resolve lookup fields (name → id) — object-level only
                        if enable_lookup_validation and lookup_fields:
                            resolved_item, lookup_errors = validate_and_resolve_lookups(cleaned_item, lookup_fields, cursor)
                            if lookup_errors:
                                return {
                                    "status": "error",
                                    "success": False,
                                    "error": {
                                        "message": " | ".join(lookup_errors),
                                        "fields": [e.split(" ")[0] for e in lookup_errors],
                                    }
                                }
                            cleaned_item = resolved_item

                        if table_name == 'leads':
                            duplicate_error = validate_lead_name_contact_uniqueness(
                                cursor=cursor,
                                lead_item=cleaned_item,
                                table_column_map=table_column_map,
                                table_name=table_name,
                            )
                            if duplicate_error:
                                return {
                                    "status": "error",
                                    "success": False,
                                    "error": {
                                        "message": duplicate_error,
                                        "fields": [
                                            field_name
                                            for field_name in [resolve_column_name('name'), resolve_column_name('email'), mobile_field]
                                            if field_name
                                        ],
                                    }
                                }

                        columns = list(cleaned_item.keys())
                        values = [cleaned_item[col] for col in columns]
                        query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING *").format(
                            sql.Identifier(table_name),
                            sql.SQL(', ').join(map(sql.Identifier, columns)),
                            sql.SQL(', ').join(sql.Placeholder() * len(values))
                        )
                        
                        cursor.execute(query, values)
                        inserted_record = dict(zip([desc[0] for desc in cursor.description], cursor.fetchone()))
                        # Parse JSON fields
                        for key, col_type in type_map.items():
                            if col_type in ['json', 'jsonb'] and isinstance(inserted_record.get(key), str):
                                try:
                                    inserted_record[key] = json.loads(inserted_record[key])
                                except json.JSONDecodeError:
                                    pass
                                
                        results.append(inserted_record)
                        # Insert related child records
                        if child_tables:
                            insert_related_child_records(cursor, table_name, inserted_record['id'], child_tables, user, **kwargs)

                return {
                    "success": True,
                    "data": results,
                    'message': f"New {table_name.capitalize()} has been created"
                }

    except Exception as e:
        print(explain_db_error(e))
        return {
            "status": "error",
            "success": False,
            "error": explain_db_error(e)
        }

def bulk_insert_with_report(cursor, table_name, raw_data, clean_record, returning_cols=("id",), required_fields=None, picklist_map=None, type_map=None, lookup_fields=None, table_column_map=None, **kwargs):
    """
    Attempts to insert each record independently using savepoints.
    Returns a detailed report including successes, failures, and reasons.
    Note: Assumes we're already inside a transaction.atomic() block.
    """

    # 1) Clean & validate input
    cleaned_data = [clean_record(item) for item in raw_data]
    required_fields = required_fields or []
    picklist_map = picklist_map or {}
    type_map = type_map or {}
    lookup_fields = lookup_fields or []
    if not cleaned_data:
        return {"success": False, "status": "error", "error": "No data to insert."}

    # Ensure consistent column order across rows (union of all keys)
    all_keys = dict.fromkeys(k for row in cleaned_data for k in row.keys())
    columns = list(all_keys)

    # Build a single-row INSERT ... RETURNING query
    insert_stmt = sql.SQL("INSERT INTO {} ({}) VALUES ({}) {}").format(
        sql.Identifier(table_name),
        sql.SQL(", ").join(map(sql.Identifier, columns)),
        sql.SQL(", ").join([sql.Placeholder()] * len(columns)),
        sql.SQL("RETURNING {}").format(
            sql.SQL(", ").join(map(sql.Identifier, returning_cols))
        ) if returning_cols else sql.SQL("")
    )

    report = {
        "success": True,
        "table": table_name,
        "attempted_count": len(cleaned_data),
        "inserted_count": 0,
        "failed_count": 0,
        "inserted": [],
        "failed": []
    }

    # 2a) Pre-validate every row in pure Python so we know which rows are
    # eligible for the fast-path bulk INSERT. Rows that fail validation are
    # recorded up-front; lookup-field resolution also happens here so the
    # rows we insert already contain resolved IDs.
    def _validate_row(idx, row):
        errs = []
        missing_required_local = find_missing_required(row, required_fields)
        if missing_required_local:
            if table_name == "call" and "telephony_id" in missing_required_local:
                errs.append("Please setup telephony to make calls.")
            else:
                missing_text = ", ".join(missing_required_local)
                errs.append(
                    f"{missing_text} is required." if len(missing_required_local) == 1 else f"{missing_text} are required."
                )
        raw_item_local = raw_data[idx] if isinstance(raw_data, list) else {}
        picklist_errors_local = validate_picklist_record(raw_item_local, picklist_map)
        if picklist_errors_local:
            errs.append(format_picklist_error(picklist_errors_local))
        datatype_errors_local = validate_data_types_record(raw_item_local, type_map)
        if datatype_errors_local:
            errs.extend(datatype_errors_local)
        return errs

    # Build a per-chunk FK lookup cache once, so per-row resolution below
    # reads from memory instead of issuing 2 SELECTs per FK field per row.
    lookup_cache = build_lookup_cache(cursor, lookup_fields, cleaned_data) if lookup_fields else {}

    eligible = []  # list of (idx, row)
    pending_after_lookup = []  # rows that pass non-DB validation
    for idx, row in enumerate(cleaned_data):
        errs = _validate_row(idx, row)
        if lookup_fields and not errs:
            resolved_row, lookup_errors = validate_and_resolve_lookups_cached(row, lookup_fields, lookup_cache, cursor)
            if lookup_errors:
                errs.extend(lookup_errors)
            else:
                row = resolved_row
                cleaned_data[idx] = resolved_row
        if errs:
            report["failed_count"] += 1
            report["failed"].append({"index": idx, "reason": " | ".join(errs), "data": row})
        else:
            pending_after_lookup.append((idx, row))

    # Batched lead-uniqueness check: one query per chunk instead of N.
    if table_name == 'leads' and pending_after_lookup:
        dup_errors = batch_lead_uniqueness_errors(
            cursor=cursor,
            rows=pending_after_lookup,
            table_column_map=table_column_map or {},
            table_name=table_name,
        )
        for idx, row in pending_after_lookup:
            if idx in dup_errors:
                report["failed_count"] += 1
                report["failed"].append({"index": idx, "reason": dup_errors[idx], "data": row})
            else:
                eligible.append((idx, row))
    else:
        eligible.extend(pending_after_lookup)

    # 2b) Fast path: attempt one multi-row INSERT via execute_values. If the
    # entire batch commits, we skip the per-row savepoint machinery and save
    # 2–3 DB round-trips per row. On any SQL failure we fall back to the
    # per-row savepoint path below for just the eligible rows — preserving
    # per-row error reporting.
    bulk_ok = False
    if eligible:
        sp_name = "sp_bulk_fast"
        try:
            cursor.execute(sql.SQL("SAVEPOINT {}").format(sql.Identifier(sp_name)))
            values_list = [tuple(row.get(col) for col in columns) for (_idx, row) in eligible]
            insert_fast = sql.SQL("INSERT INTO {} ({}) VALUES %s{}").format(
                sql.Identifier(table_name),
                sql.SQL(", ").join(map(sql.Identifier, columns)),
                sql.SQL(" RETURNING {}").format(
                    sql.SQL(", ").join(map(sql.Identifier, returning_cols))
                ) if returning_cols else sql.SQL("")
            )
            execute_values(cursor, insert_fast.as_string(cursor), values_list, fetch=bool(returning_cols))
            returned_rows = cursor.fetchall() if returning_cols else []
            cursor.execute(sql.SQL("RELEASE SAVEPOINT {}").format(sql.Identifier(sp_name)))
            for i, (idx, row) in enumerate(eligible):
                ret = returned_rows[i] if i < len(returned_rows) else None
                report["inserted_count"] += 1
                report["inserted"].append({
                    "index": idx,
                    "returning": dict(zip(returning_cols, ret)) if ret else None,
                    "data": row,
                })
            bulk_ok = True
        except Exception:
            # Roll back and fall through to the per-row path below.
            try:
                cursor.execute(sql.SQL("ROLLBACK TO SAVEPOINT {}").format(sql.Identifier(sp_name)))
                cursor.execute(sql.SQL("RELEASE SAVEPOINT {}").format(sql.Identifier(sp_name)))
            except Exception:
                pass

    if bulk_ok:
        if report["inserted_count"] == 0:
            report["success"] = False
        try:
            log_audit(
                action=f"Bulk inserted {report['inserted_count']} records into '{table_name}' with {report['failed_count']} failures.",
                section="Import - Bulk Insert",
                **kwargs
            )
        except Exception:
            pass
        return report

    # 2c) Per-row fallback (original behaviour) — only reached when the
    # fast-path bulk INSERT raised. We re-run just the previously-eligible
    # rows so already-reported validation failures aren't double-counted.
    eligible_idxs = {idx for (idx, _r) in eligible}
    for idx, row in enumerate(cleaned_data):
        if idx not in eligible_idxs:
            continue
        sp_name = f"sp_bulk_{idx}"
        try:
            # Create savepoint FIRST so lookup DB queries can be rolled back cleanly
            cursor.execute(sql.SQL("SAVEPOINT {}").format(sql.Identifier(sp_name)))

            # Collect all validation errors for this record
            validation_errors = []
            
            missing_required = find_missing_required(row, required_fields)
            if missing_required:
                # Friendly message when telephony is not configured for calls
                if table_name == "call" and "telephony_id" in missing_required:
                    validation_errors.append("Please setup telephony to make calls.")
                else:
                    missing_text = ", ".join(missing_required)
                    validation_errors.append(
                        f"{missing_text} is required." if len(missing_required) == 1 else f"{missing_text} are required."
                    )

            raw_item = raw_data[idx] if isinstance(raw_data, list) else {}
            picklist_errors = validate_picklist_record(raw_item, picklist_map)
            if picklist_errors:
                validation_errors.append(format_picklist_error(picklist_errors))

            # Validate data types and email formats
            datatype_errors = validate_data_types_record(raw_item, type_map)
            if datatype_errors:
                validation_errors.extend(datatype_errors)

            # Validate and resolve lookup fields (name → id)
            if lookup_fields:
                resolved_row, lookup_errors = validate_and_resolve_lookups(row, lookup_fields, cursor)
                if lookup_errors:
                    validation_errors.extend(lookup_errors)
                else:
                    row = resolved_row
                    cleaned_data[idx] = resolved_row

            if table_name == 'leads':
                duplicate_error = validate_lead_name_contact_uniqueness(
                    cursor=cursor,
                    lead_item=row,
                    table_column_map=table_column_map or {},
                    table_name=table_name,
                )
                if duplicate_error:
                    validation_errors.append(duplicate_error)

            # If any validation errors, rollback savepoint and skip insert
            if validation_errors:
                try:
                    cursor.execute(sql.SQL("ROLLBACK TO SAVEPOINT {}").format(sql.Identifier(sp_name)))
                    cursor.execute(sql.SQL("RELEASE SAVEPOINT {}").format(sql.Identifier(sp_name)))
                except Exception:
                    pass
                report["failed_count"] += 1
                report["failed"].append({
                    "index": idx,
                    "reason": " | ".join(validation_errors),
                    "data": row
                })
                continue

            # Execute insert for this single row
            values = [row.get(col) for col in columns]
            cursor.execute(insert_stmt, values)

            returned = cursor.fetchone() if returning_cols else None
            report["inserted_count"] += 1
            report["inserted"].append({
                "index": idx,
                "returning": dict(zip(returning_cols, returned)) if returned else None,
                "data": row
            })

            # Release savepoint on success
            cursor.execute(sql.SQL("RELEASE SAVEPOINT {}").format(sql.Identifier(sp_name)))

        except Exception as e:
            # Roll back only this row
            try:
                cursor.execute(sql.SQL("ROLLBACK TO SAVEPOINT {}").format(sql.Identifier(sp_name)))
                cursor.execute(sql.SQL("RELEASE SAVEPOINT {}").format(sql.Identifier(sp_name)))
            except Exception:
                # If releasing fails, move on; we still record the failure
                pass

            reason = explain_db_error(e)['message']
            # Enrich with column name by matching bad value to row data
            m = re.search(r"Invalid value '([^']*)' for type", reason)
            if m and row:
                bad_val = m.group(1)
                col = next((k for k, v in row.items() if str(v) == bad_val), None)
                if col:
                    reason = reason.replace("Invalid value", f"Field '{col}': invalid value")

            report["failed_count"] += 1
            report["failed"].append({
                "index": idx,
                "reason": reason,
                "data": row
            })

    # 3) Overall success flag & optional audit log
    if report["inserted_count"] == 0:
        report["success"] = False  # nothing got inserted

    try:
        log_audit(
            action=f"Bulk inserted {report['inserted_count']} records into '{table_name}' with {report['failed_count']} failures.",
            section="Import - Bulk Insert",
            **kwargs
        )
    except Exception:
        # Don't block the main result if audit logging fails
        pass

    return report
