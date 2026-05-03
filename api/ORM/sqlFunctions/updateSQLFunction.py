import json
import re
from django.db import connection, transaction
from django.utils import timezone
from api.ORM.sqlFunctions.utils.error_handlers import explain_db_error
from api.ORM.sqlFunctions.createSQLFunction import (
    post_data_sql,
    get_picklist_fields,
    validate_picklist_record,
    format_picklist_error,
    get_lookup_fields,
    validate_and_resolve_lookups,
    validate_and_resolve_lookups_cached,
    build_lookup_cache,
    validate_data_types_record,
    validate_lead_name_contact_uniqueness,
    ensure_leads_name_not_unique,
)
from api.ORM.sqlFunctions.utils.helpers import validate_identifier
from api.security.schema_authority import get_validated_schema
from psycopg2 import sql
from psycopg2.extras import Json, execute_values


def run_raw_query(query, params=None, fetchone=False, fetchall=False, schema='public'):
    validate_identifier(schema)
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL search_path TO %s", [schema])
        cursor.execute(query, params or [])
        if fetchone:
            return cursor.fetchone()
        if fetchall:
            return cursor.fetchall()


def get_tracked_fields(object_name, schema='public'):
    # Match case-insensitively + trimmed so a tracking config saved as
    # "Invoice"/"INVOICE"/" invoice " still matches an update issued
    # with a different casing. Without this, a config row stored with
    # one casing and an update call using another casing silently
    # returned an empty list and no field changes were ever recorded
    # in `field_history_log`.
    query = """
        SELECT field_name FROM field_tracking_config
        WHERE LOWER(TRIM(object_name)) = LOWER(TRIM(%s))
          AND is_tracked = true
    """
    return [row[0] for row in run_raw_query(query, [object_name], fetchall=True, schema=schema)]


def get_instance_by_id(table_name, pk, schema='public'):
    validate_identifier(schema)
    validate_identifier(table_name)
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL search_path TO %s", [schema])
        cursor.execute(
            sql.SQL("SELECT * FROM {} WHERE id = %s").format(sql.Identifier(table_name)),
            [pk]
        )
        row = cursor.fetchone()
        if not row:
            return None
        columns = [desc[0] for desc in cursor.description]
        return dict(zip(columns, row))


def log_field_history(object_name, record_id, field_name, old_value, new_value, changed_at, user_id, schema='public'):
    query = """
        INSERT INTO field_history_log
        (object_name, record_id, field_name, old_value, new_value, changed_at, user_id)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    run_raw_query(
        query,
        [object_name, str(record_id), field_name, str(old_value), str(new_value), changed_at, user_id],

        schema=schema,
    )


def log_field_changes_sql(object_name, table_name, pk, updated_fields, user_id=None, **kwargs):
    schema = (get_validated_schema(kwargs) or 'public')
    tracked_fields = get_tracked_fields(object_name, schema=schema)
    changes = []

    current = get_instance_by_id(table_name, pk, schema=(get_validated_schema(kwargs) or 'public'))
    if not current:
        return []

    current_data = current

    for field_name in tracked_fields:
        if field_name in updated_fields:
            old_value = current_data.get(field_name)
            new_value = updated_fields[field_name]
            if str(old_value) != str(new_value):
                log_field_history(
                    object_name, pk, field_name,
                    old_value if old_value is not None else None,
                    new_value if new_value is not None else None,
                    timezone.now(),
                    user_id,
                    schema=schema,
                )
                changes.append({
                    "field_name": field_name,
                    "old_value": str(old_value),
                    "new_value": str(new_value),
                })
    return changes


def get_column_types_from_db(table_name, schema='public'):
    query = """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
    """
    with connection.cursor() as cursor:
        cursor.execute(query, [schema, table_name])
        return {row[0]: row[1] for row in cursor.fetchall()}


def ensure_leads_company_column(schema='public'):
    validate_identifier(schema)
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL search_path TO %s", [schema])
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = 'leads' AND lower(column_name) = 'company'
            """,
            [schema],
        )
        exists = cursor.fetchone()
        if not exists:
            cursor.execute(sql.SQL("ALTER TABLE {} ADD COLUMN {} VARCHAR(255)").format(
                sql.Identifier('leads'),
                sql.Identifier('company')
            ))


def get_label_from_db(table_name, record_id, schema='public'):
    validate_identifier(schema)
    validate_identifier(table_name)
    possible_fields = [
        'name', 'full_name', 'provider', 'first_name', 'email',
        'subject', 'label', 'view_name', 'display_name', 'access_level'
    ]
    with connection.cursor() as cursor:
        cursor.execute("SET search_path TO %s", [schema])
        cursor.execute( 
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            """,
            [schema, table_name]
        )
        existing_columns = {row[0] for row in cursor.fetchall()}

        for field in possible_fields:
            if field not in existing_columns:
                continue
            try:
                cursor.execute(
                    sql.SQL('SELECT {} FROM {} WHERE id = %s').format(
                        sql.Identifier(field),
                        sql.Identifier(table_name)
                    ),
                    [record_id]
                )
                result = cursor.fetchone()
                if result and result[0]:
                    return result[0]
            except Exception:
                continue
    return record_id

def bulk_fetch_current_rows(cursor, table_name, ids):
    """Fetch existing rows for a set of ids in a single query.

    Returns {id_as_str: row_dict}. Used to eliminate per-row
    get_instance_by_id() calls inside the update loop.
    """
    if not ids:
        return {}
    validate_identifier(table_name)
    cursor.execute(
        sql.SQL("SELECT * FROM {} WHERE id::text = ANY(%s)").format(sql.Identifier(table_name)),
        [[str(i) for i in ids]],
    )
    columns = [desc[0] for desc in cursor.description]
    out = {}
    for row in cursor.fetchall():
        row_dict = dict(zip(columns, row))
        out[str(row_dict.get("id"))] = row_dict
    return out


def resolve_label_column(cursor, table_name, existing_columns=None):
    """Pick the best label column for a table once per chunk."""
    candidates = [
        'name', 'full_name', 'provider', 'first_name', 'email',
        'subject', 'label', 'view_name', 'display_name', 'access_level',
    ]
    if existing_columns is None:
        cursor.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s
            """,
            [table_name],
        )
        existing_columns = {row[0] for row in cursor.fetchall()}
    for field in candidates:
        if field in existing_columns:
            return field
    return None


def flush_field_history(cursor, pending):
    """Batch-insert all accumulated field history rows in one execute_values."""
    if not pending:
        return
    execute_values(
        cursor,
        "INSERT INTO field_history_log "
        "(object_name, record_id, field_name, old_value, new_value, changed_at, user_id) "
        "VALUES %s",
        pending,
    )


def record_field_changes(object_name, pk, updated_fields, tracked_fields, current_data, user_id, pending_history):
    """Compute tracked field diffs and append INSERT rows to pending_history.

    Replaces log_field_changes_sql inside the loop. Does no DB work itself —
    callers flush pending_history once via flush_field_history() at the end.
    """
    if not current_data:
        return []
    changes = []
    now = timezone.now()
    # Build case-insensitive lookups so a tracked-field name stored as
    # `Status` still matches the `update_fields`/`current_data` keys
    # (which are the actual DB column names, typically lowercase).
    # Without this normalisation, casing drift between
    # `field_tracking_config.field_name` and the actual column name
    # caused `field_name in updated_fields` to be False for every
    # tracked field and no history rows were ever logged.
    updated_lower = {str(k).lower(): k for k in updated_fields.keys()}
    current_lower = {str(k).lower(): k for k in (current_data.keys() if hasattr(current_data, "keys") else [])}
    for field_name in tracked_fields:
        f_lower = str(field_name).lower()
        upd_key = updated_lower.get(f_lower)
        if upd_key is None:
            continue
        cur_key = current_lower.get(f_lower, field_name)
        old_value = current_data.get(cur_key)
        new_value = updated_fields[upd_key]
        if str(old_value) == str(new_value):
            continue
        pending_history.append((
            object_name,
            str(pk),
            # Preserve the actual column name in the log so the history
            # popup can join it back to the field metadata.
            upd_key,
            None if old_value is None else str(old_value),
            None if new_value is None else str(new_value),
            now,
            user_id,
        ))
        changes.append({
            "field_name": upd_key,
            "old_value": str(old_value),
            "new_value": str(new_value),
        })
    return changes


def updateRawSQL(object_name, editable_fields=None, section=None, **kwargs):
    user = kwargs.get('user_', {})
    user_id = user.get('id')
    schema = get_validated_schema(kwargs)
    documents = kwargs.get('update_data')
    fields_metadata = kwargs.get('fields_metadata', [])
    transfer = kwargs.get('transfer', False)

    print("Recordds to update:", documents)

    if not documents:
        return {"success": False, "error": "No data provided for update."}

    if isinstance(documents, dict):
        documents = [documents]

    validate_identifier(schema)
    table_name = object_name.lower()
    if object_name == 'user':
        table_name = "users"
    validate_identifier(table_name)
    if table_name == 'leads':
        ensure_leads_company_column(schema=schema)
    ignored_fields = ['id', 'created_date', 'created_by_id', 'owner_id']
    if transfer:
        ignored_fields.remove('owner_id')  # Allow updating owner_id during transfer
    # Only run lookup validation for object-level calls (not setup APIs)
    enable_lookup_validation = kwargs.get('enable_lookup_validation', False)
    db_field_type_map = get_column_types_from_db(table_name, schema=schema)
    db_column_name_map = {str(col).lower(): col for col in db_field_type_map.keys()}

    def resolve_column_name(field_name):
        if field_name is None:
            return None
        return db_column_name_map.get(str(field_name).lower())

    # Datatype map for validation can still use metadata when present
    if fields_metadata:
        field_type_map = {f['name']: f['datatype'] for f in fields_metadata}
    else:
        field_type_map = db_field_type_map
    report = {
        "success": True,
        "table": table_name,
        "attempted_count": len(documents),
        "updated_count": 0,
        "failed_count": 0,
        "created_count": 0,
        "updated": [],
        "created": [],
        "failed": []
    }

    with transaction.atomic():
        with connection.cursor() as cursor:
            # Use SET LOCAL for search_path within transaction
            cursor.execute("SET LOCAL search_path TO %s", [schema])
            if table_name == 'leads':
                ensure_leads_name_not_unique(cursor, schema=schema, table_name=table_name)
            picklist_map = get_picklist_fields(cursor, table_name, schema)
            # Only fetch lookup fields for object-level updates
            lookup_fields = get_lookup_fields(cursor, table_name, schema) if enable_lookup_validation else []

            # Build FK lookup cache once for the whole chunk instead of
            # issuing 2 SELECTs per FK field per row inside the loop below.
            lookup_cache = build_lookup_cache(cursor, lookup_fields, documents) if lookup_fields else {}

            # Cache tracked-fields list once, prefetch existing rows once, and
            # pick the label column once — hoists ~4 DB roundtrips per row out
            # of the loop (get_tracked_fields, get_instance_by_id ×2, label
            # column resolution). Field history rows are accumulated and
            # batch-inserted at the end instead of one INSERT per changed field.
            tracked_fields_cache = get_tracked_fields(object_name, schema=schema)
            prefetch_ids = [doc.get("id") for doc in documents if doc.get("id")]
            current_rows_cache = bulk_fetch_current_rows(cursor, table_name, prefetch_ids)
            label_column = resolve_label_column(cursor, table_name, existing_columns=set(db_field_type_map.keys()))
            pending_history = []

            for idx, doc in enumerate(documents):
                doc_id = doc.get("id")

                if not doc_id:
                    name_value = doc.get("name")
                    if not name_value:
                        report["failed"].append({
                            "index": idx,
                            "id": None,
                            "reason": "Missing 'id' or 'name' field"
                        })
                        report["failed_count"] += 1
                        continue

                    name_column = resolve_column_name("name")
                    if not name_column:
                        report["failed"].append({
                            "index": idx,
                            "id": None,
                            "reason": "'name' field is not available for lookup"
                        })
                        report["failed_count"] += 1
                        continue

                    cursor.execute(
                        sql.SQL("SELECT id FROM {} WHERE {} = %s").format(
                            sql.Identifier(table_name),
                            sql.Identifier(name_column)
                        ),
                        [name_value]
                    )
                    name_rows = cursor.fetchall()

                    if not name_rows:
                        create_result = post_data_sql(
                            table_name,
                            doc,
                            section=f"Create - {table_name}",
                            enable_lookup_validation=enable_lookup_validation,
                            **kwargs
                        )
                        if not create_result.get("success"):
                            error_message = create_result.get("error")
                            if isinstance(error_message, dict):
                                error_message = error_message.get("message")
                            error_message = error_message or "Failed to create record"
                            # Enrich with column name by matching bad value to doc fields
                            m = re.search(r"Invalid value '([^']*)' for type", error_message)
                            if m and doc:
                                bad_val = m.group(1)
                                col = next((k for k, v in doc.items() if str(v) == bad_val), None)
                                if col:
                                    error_message = error_message.replace("Invalid value", f"Field '{col}': invalid value")
                            report["failed"].append({
                                "index": idx,
                                "id": None,
                                "reason": error_message
                            })
                            report["failed_count"] += 1
                            continue

                        created_records = create_result.get("data", [])
                        created_record = created_records[0] if created_records else {}
                        created_id = created_record.get("id")
                        report["created_count"] += 1
                        report["created"].append({
                            "index": idx,
                            "id": created_id,
                            "created_data": created_record
                        })
                        continue

                    if len(name_rows) > 1:
                        report["failed"].append({
                            "index": idx,
                            "id": None,
                            "reason": "Multiple records found with provided 'name'"
                        })
                        report["failed_count"] += 1
                        continue

                    doc_id = name_rows[0][0]
                    doc["id"] = doc_id

                sp_name = f"sp_update_{idx}"

                try:
                    # Create savepoint FIRST so lookup DB queries can be rolled back cleanly
                    cursor.execute(sql.SQL("SAVEPOINT {}").format(sql.Identifier(sp_name)))

                    resolved_doc, lookup_errors = validate_and_resolve_lookups_cached(doc, lookup_fields, lookup_cache, cursor)
                    if lookup_errors and enable_lookup_validation:
                        cursor.execute(sql.SQL("ROLLBACK TO SAVEPOINT {}").format(sql.Identifier(sp_name)))
                        cursor.execute(sql.SQL("RELEASE SAVEPOINT {}").format(sql.Identifier(sp_name)))
                        report["failed"].append({
                            "index": idx,
                            "id": doc_id,
                            "reason": lookup_errors[0]
                        })
                        report["failed_count"] += 1
                        continue

                    doc = resolved_doc
                    picklist_errors = validate_picklist_record(doc, picklist_map)
                    if picklist_errors:
                        cursor.execute(sql.SQL("ROLLBACK TO SAVEPOINT {}").format(sql.Identifier(sp_name)))
                        cursor.execute(sql.SQL("RELEASE SAVEPOINT {}").format(sql.Identifier(sp_name)))
                        report["failed"].append({
                            "index": idx,
                            "id": doc_id,
                            "reason": format_picklist_error(picklist_errors)
                        })
                        report["failed_count"] += 1
                        continue

                    # Validate data types and email formats
                    datatype_errors = validate_data_types_record(doc, field_type_map)
                    if datatype_errors:
                        cursor.execute(sql.SQL("ROLLBACK TO SAVEPOINT {}").format(sql.Identifier(sp_name)))
                        cursor.execute(sql.SQL("RELEASE SAVEPOINT {}").format(sql.Identifier(sp_name)))
                        report["failed"].append({
                            "index": idx,
                            "id": doc_id,
                            "reason": " | ".join(datatype_errors)
                        })
                        report["failed_count"] += 1
                        continue

                    if table_name == 'leads':
                        existing_record = current_rows_cache.get(str(doc_id))
                        if existing_record is None:
                            existing_record = get_instance_by_id(table_name, doc_id, schema=schema) or {}
                            if existing_record:
                                current_rows_cache[str(doc_id)] = existing_record
                        merged_lead_data = existing_record.copy()
                        merged_lead_data.update(doc)
                        duplicate_error = validate_lead_name_contact_uniqueness(
                            cursor=cursor,
                            lead_item=merged_lead_data,
                            table_column_map=db_column_name_map,
                            table_name=table_name,
                            exclude_id=doc_id,
                        )
                        if duplicate_error:
                            cursor.execute(sql.SQL("ROLLBACK TO SAVEPOINT {}").format(sql.Identifier(sp_name)))
                            cursor.execute(sql.SQL("RELEASE SAVEPOINT {}").format(sql.Identifier(sp_name)))
                            report["failed"].append({
                                "index": idx,
                                "id": doc_id,
                                "reason": duplicate_error
                            })
                            report["failed_count"] += 1
                            continue

                    # Auto-set timestamps and user metadata
                    last_modified_date_col = resolve_column_name('last_modified_date')
                    last_modified_by_col = resolve_column_name('last_modified_by_id')
                    modified_at_col = resolve_column_name('modified_at')

                    if last_modified_date_col:
                        doc[last_modified_date_col] = timezone.now()
                    if last_modified_by_col and user:
                        doc[last_modified_by_col] = user_id
                    if modified_at_col:
                        doc[modified_at_col] = timezone.now()

                    # Build update fields
                    update_fields = {}
                    for k, v in doc.items():
                        resolved_key = resolve_column_name(k)
                        if not resolved_key:
                            continue

                        if resolved_key in ignored_fields:
                            continue

                        datatype = db_field_type_map.get(resolved_key) or field_type_map.get(k)

                        if datatype in ['json', 'jsonb']:
                            try:
                                v = json.dumps(v)
                            except Exception as e:
                                raise ValueError(f"Invalid JSON for '{k}': {str(e)}")
                        if datatype in ['picklist_multi']:
                            try:
                                v = json.dumps(v)
                            except Exception as e:
                                raise ValueError(f"Invalid JSON for '{k}': {str(e)}")
                        update_fields[resolved_key] = v
                    # Track field history BEFORE update — accumulates into
                    # pending_history; one batched INSERT happens after the loop.
                    current_data = current_rows_cache.get(str(doc_id))
                    if current_data is None and tracked_fields_cache:
                        current_data = get_instance_by_id(table_name, doc_id, schema=schema)
                        if current_data:
                            current_rows_cache[str(doc_id)] = current_data
                    field_changes = record_field_changes(
                        object_name=object_name,
                        pk=doc_id,
                        updated_fields=update_fields,
                        tracked_fields=tracked_fields_cache,
                        current_data=current_data,
                        user_id=user_id,
                        pending_history=pending_history,
                    )
                    # Build SQL using sql.Identifier for column names
                    set_parts = [sql.SQL("{} = %s").format(sql.Identifier(field)) for field in update_fields.keys()]
                    set_clause = sql.SQL(', ').join(set_parts)
                    params = list(update_fields.values()) + [doc_id]

                    update_query = sql.SQL("UPDATE {} SET {} WHERE id = %s").format(
                        sql.Identifier(table_name),
                        set_clause
                    )

                    cursor.execute(update_query, params)

                    # Success — resolve label from prefetched row + the update
                    # we just wrote, avoiding a per-row SELECT.
                    report["updated_count"] += 1
                    if label_column and label_column in update_fields:
                        record_label = update_fields[label_column]
                    elif current_data and label_column:
                        record_label = current_data.get(label_column) or doc_id
                    else:
                        record_label = doc_id
                    report["updated"].append({
                        "index": idx,
                        "id": doc_id,
                        "updated_data": {**update_fields, "id": doc_id, "name": record_label},
                        # "updated_data": {**update_fields, "id": doc_id, "name": record_label},
                        "field_changes": field_changes
                    })
                    cursor.execute(sql.SQL("RELEASE SAVEPOINT {}").format(sql.Identifier(sp_name)))

                except Exception as e:
                    print(f"Error updating record id {doc_id}: {str(e)}")
                    cursor.execute(sql.SQL("ROLLBACK TO SAVEPOINT {}").format(sql.Identifier(sp_name)))
                    cursor.execute(sql.SQL("RELEASE SAVEPOINT {}").format(sql.Identifier(sp_name)))

                    reason = explain_db_error(e)['message']
                    # Enrich with column name by matching bad value to update_fields
                    m = re.search(r"Invalid value '([^']*)' for type", reason)
                    if m and update_fields:
                        bad_val = m.group(1)
                        col = next((k for k, v in update_fields.items() if str(v) == bad_val), None)
                        if col:
                            reason = reason.replace("Invalid value", f"Field '{col}': invalid value")

                    report["failed_count"] += 1
                    report["failed"].append({
                        "index": idx,
                        "id": doc_id,
                        "reason": reason
                    })

            # Flush accumulated field history in one batched INSERT.
            try:
                flush_field_history(cursor, pending_history)
            except Exception:
                # Never let audit-log failures block the main update result.
                pass

    # Final success check
    if report["updated_count"] == 0 and report["created_count"] == 0:
        report["success"] = False
    return report

