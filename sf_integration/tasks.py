from celery import shared_task
from django.utils.timezone import now
import psycopg2
from sf_integration.salesforce_client import sync_metadata_and_data
from sync_salesforce import DB_CONFIG, sync_to_salesforce
from .models import SalesforceSync

# Phase 6 adoption: AdminTask is the explicit opt-out base for tasks
# that legitimately span multiple tenants (e.g. nightly sync sweeps).
# Using it makes the cross-tenant intent visible in every PR.
from api.celery_tasks.base import AdminTask

# NOTE for tenant context:
# `SalesforceSync` lives in `public` (Django-managed model), so the
# top-level scan does not need a tenant pin. However, the per-object
# work (`copy_salesforce_data_to_app` etc.) writes into per-tenant
# `sf_integration_<object>` tables; those callers MUST open a
# `with_tenant_schema(...)` context for the relevant org before
# touching them. See `api.security.tenant_context`.
#
# Phase 6 adoption FOLLOW-UP: the inner loop `sync_salesforce_object`
# does NOT currently open `with_tenant_schema` before calling
# `copy_salesforce_data_to_app`. That's a gap — under Phase 4 part 1
# (per-tenant Postgres roles), the inner writes against
# `sf_integration_<object>` either need to run as the main role OR be
# wrapped in a tenant pin. Tracked in
# docs/SEC_PHASE6_ADOPTION_OPERATOR_NOTES.md as a Phase 6+ follow-up.


@shared_task(base=AdminTask)
def process_salesforce_sync():
    sync_objects = SalesforceSync.objects.filter(is_enabled=True)

    for sync_obj in sync_objects:
        if sync_obj.is_sync_due():  # Check if sync is due based on frequency
            sync_salesforce_object(sync_obj)

    return "Sync completed"

def sync_salesforce_object(sync_obj):
    if sync_obj.salesforce_pull:
        sync_metadata_and_data(sync_obj.object_name)  # Pull data from Salesforce
        copy_salesforce_data_to_app(sync_obj)
    if sync_obj.salesforce_push:
        push_data_to_salesforce(sync_obj.object_name)
    
    sync_obj.last_synced_at = now()
    sync_obj.save()


def column_exists(table_name, column_name, cursor, schema='public'):
    query = f"""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = '{table_name}' AND column_name = '{column_name}' AND table_schema = {schema};
    """
    cursor.execute(query)
    return cursor.fetchone() is not None

def push_data_to_salesforce(object_name):
    """
    Fetch unsynced or recently modified records from the database and push them to Salesforce.
    """
    table_name = f"sf_integration_{object_name.lower()}"
    
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            # Check if 'updated_at' column exists
            if column_exists(table_name, "updated_at", cur):
                query = f'SELECT * FROM {table_name} WHERE "Id" IS NULL OR updated_at > last_synced_at;'
            else:
                query = f'SELECT * FROM {table_name} WHERE "Id" IS NULL;'
            
            cur.execute(query)
            records = cur.fetchall()
            columns = [desc[0] for desc in cur.description]
            
            for row in records:
                record_data = dict(zip(columns, row))
                sync_data = {
                    "operation": "INSERT" if record_data.get("Id") is None else "UPDATE",
                    "table": table_name,
                    "data": record_data
                }
                sync_to_salesforce(sync_data)  # Push each record to Salesforce



# import logging
# from django.apps import apps
# from django.db import connection, IntegrityError

# logger = logging.getLogger(__name__)

# def copy_salesforce_data_to_app(sync_obj):
#     model_name = sync_obj.object_name.capitalize()

#     try:
#         model = apps.get_model('custom_models', model_name)
#         logger.warning(f"✅ Model '{model_name}' found in custom_models.")
#     except LookupError:
#         logger.warning(f"❌ Model for Salesforce object '{sync_obj.object_name}' not found.")
#         return

#     model_fields = [f.name for f in model._meta.get_fields()]
#     logger.warning(f"🧩 Fields in {model_name} model: {model_fields}")

#     with connection.cursor() as cursor:
#         cursor.execute(f'SELECT * FROM sf_integration_{sync_obj.object_name.lower()}')
#         columns = [col[0] for col in cursor.description]
#         rows = cursor.fetchall()
#         logger.warning(f"📥 Fetched {len(rows)} records from sf_integration_{sync_obj.object_name.lower()}.")

#         created_count = 0
#         updated_count = 0
#         error_count = 0

#         for row in rows:
#             row_data = dict(zip(columns, row))
#             external_id = row_data.get("Id")  # Salesforce ID
#             filtered_data = {field: value for field, value in row_data.items() if field in model_fields}
#             filtered_data["external_id"] = external_id

#             if not external_id:
#                 logger.warning("⚠️ Skipping record with no external_id.")
#                 continue

#             # Map Salesforce 'Email' to model 'email' if present
#             if "email" in model_fields:
#                 filtered_data["email"] = row_data.get("Email")  # Map Salesforce Email to model email

#             # Skip if email is unique and missing
#             if "email" in model_fields and not filtered_data.get("email"):
#                 logger.warning(f"⚠️ Skipping record with Id={external_id} due to missing email (unique constraint).")
#                 continue

#             try:
#                 obj, created = model.objects.update_or_create(
#                     external_id=external_id,
#                     defaults=filtered_data
#                 )
#                 if created:
#                     created_count += 1
#                     logger.warning(f"🆕 Created record with external_id={external_id}")
#                 else:
#                     updated_count += 1

#             except IntegrityError as e:
#                 error_count += 1
#                 logger.warning(f"❌ Error syncing record with Id={external_id}: {str(e).strip()}")

#         logger.warning(f"✅ Sync Summary for {model_name}: {created_count} created, {updated_count} updated, {error_count} errors.")



import logging
from django.apps import apps
from django.db import connection, IntegrityError

logger = logging.getLogger(__name__)

def copy_salesforce_data_to_app(sync_obj):
    model_name = sync_obj.object_name.capitalize()

    try:
        model = apps.get_model('custom_models', model_name)
        logger.warning(f"✅ Model '{model_name}' found in custom_models.")
    except LookupError:
        logger.warning(f"❌ Model for Salesforce object '{sync_obj.object_name}' not found.")
        return

    # Get your Django model’s field names (all lowercase)
    model_fields = {f.name for f in model._meta.get_fields()}
    logger.warning(f"🧩 Fields in {model_name} model: {sorted(model_fields)}")

    table = f"sf_integration_{sync_obj.object_name.lower()}"

    with connection.cursor() as cursor:
        cursor.execute(f'SELECT * FROM {table}')
        raw_cols = [col[0] for col in cursor.description]
        rows = cursor.fetchall()

    logger.warning(f"📥 Fetched {len(rows)} records from {table}.")

    created, updated, errors = 0, 0, 0

    for row in rows:
        # Zip and then lowercase and remove __c for every key in Salesforce data
        raw = dict(zip(raw_cols, row))
        data = {col.lower().replace('__c', ''): val for col, val in raw.items()}


        # Use 'Id' from Salesforce or fall back to 'id' for the external_id
        sf_id = data.get('id') or data.get('id')
        if not sf_id:
            logger.warning("⚠️ Skipping record with no 'Id'.")
            continue

        # Build only the keys your model actually has, except 'id'
        defaults = {
            k: v
            for k, v in data.items()
            if k in model_fields and k != 'id'
        }
        # Ensure we set external_id
        defaults['external_id'] = sf_id

        # If your model requires email or phone (and they're unique) you can skip if missing
        for u in ('email', 'phone'):
            if u in model_fields and not defaults.get(u):
                logger.warning(f"⚠️ Skipping {model_name} {sf_id}—missing {u}.")
                break
        else:
            try:
                obj, created_flag = model.objects.update_or_create(
                    external_id=sf_id,
                    defaults=defaults
                )
                if created_flag:
                    created += 1
                    logger.warning(f"🆕 Created {model_name} {sf_id}")
                else:
                    updated += 1
            except IntegrityError as e:
                errors += 1
                logger.warning(f"❌ IntegrityError on {model_name} {sf_id}: {e}")

    logger.warning(
        f"✅ Sync Summary for {model_name}: "
        f"{created} created, {updated} updated, {errors} errors."
    )