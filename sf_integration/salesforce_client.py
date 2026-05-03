# from django.apps import apps
# from django.db import models, connection, transaction
# from simple_salesforce import Salesforce
# import requests

# def register_dynamic_model(app_label, model_name, attrs):
#     """Registers a dynamically created model in Django's app registry and ensures it is accessible."""
    
#     # Check if the model is already registered
#     if model_name.lower() in apps.all_models[app_label]:
#         return apps.get_model(app_label, model_name)

#     # Create a new model class dynamically
#     model_class = type(model_name, (models.Model,), attrs)

#     # Explicitly register the model
#     apps.all_models[app_label][model_name.lower()] = model_class

#     # Ensure Django recognizes it
#     try:
#         apps.get_app_config(app_label).models[model_name.lower()] = model_class
#     except KeyError:
#         print(f"⚠️ App '{app_label}' not found in Django. Ensure it's in INSTALLED_APPS.")

#     # Clear Django’s cache to reflect model registration
#     apps.clear_cache()

#     return model_class

# import requests
# from django.conf import settings
# from simple_salesforce import Salesforce

# def get_salesforce_client():
#     """Authenticate with Salesforce using credentials from settings.py."""
    
#     username = settings.SALESFORCE_USERNAME
#     password = settings.SALESFORCE_PASSWORD
#     client_id = settings.SALESFORCE_CLIENT_ID
#     client_secret = settings.SALESFORCE_CLIENT_SECRET

#     if not all([username, password, client_id, client_secret]):
#         raise Exception("One or more Salesforce credentials are missing from settings.")

#     payload = {
#         "grant_type": "password",
#         "client_id": client_id,
#         "client_secret": client_secret,
#         "username": username,
#         "password": password,
#     }

#     response = requests.post("https://login.salesforce.com/services/oauth2/token", data=payload)

#     if response.status_code == 200:
#         auth_response = response.json()
#         return Salesforce(
#             instance_url=auth_response["instance_url"],
#             session_id=auth_response["access_token"]
#         )
#     else:
#         raise Exception(f"Salesforce Authentication Failed: {response.json()}")



# def fetch_salesforce_metadata():
#     """Fetch metadata from Salesforce for both custom and standard objects."""
#     sf = get_salesforce_client()
    
#     # Fetch all Salesforce objects' metadata
#     all_objects = sf.describe()["sobjects"]
    
#     # Custom objects (end with '__c')
#     custom_objects = [obj["name"] for obj in all_objects if obj["name"].endswith("__c")]

#     # Standard objects needed for syncing
#     standard_objects = ["Account", "Lead", "Opportunity", "Product2", "Task", "Contact", "Pricebook2"]

#     # Combine both lists
#     objects_to_sync = standard_objects + custom_objects  

#     metadata = {}
#     for obj_name in objects_to_sync:
#         metadata[obj_name] = sf.__getattr__(obj_name).describe()
    
#     return metadata


# from django.db import models, connection, transaction
# from django.apps import apps

# def sync_metadata_and_data(single_object=None):
#     """Fetch metadata, register models, update schema, and sync records."""
#     metadata = fetch_salesforce_metadata()
#     sf = get_salesforce_client()

#     objects_to_sync = {single_object: metadata[single_object]} if single_object else metadata

#     for obj_name, obj_metadata in objects_to_sync.items():
#         table_name = f"sf_integration_{obj_name.lower()}"
#         columns = {field["name"]: field["type"] for field in obj_metadata["fields"]}
        
#         if not columns:
#             continue

#         # Register model dynamically
#         attrs = {
#             "__module__": "sf_integration.models",
#             "Meta": type("Meta", (), {"app_label": "sf_integration"}),
#         }

#         for column_name, column_type in columns.items():
#             field_type = models.CharField(max_length=2000, null=True, blank=True)
#             # Check for External ID field
#             is_external_id = any(field.get("externalId", False) for field in obj_metadata["fields"] if field["name"] == column_name)
#             if column_type == "double":
#                 field_type = models.FloatField(null=True, blank=True)
#             elif column_type == "boolean":
#                 field_type = models.BooleanField(null=True, blank=True)
#             elif column_type == "int":
#                 field_type = models.IntegerField(null=True, blank=True)
#             elif column_type == "datetime":
#                 field_type = models.DateTimeField(null=True, blank=True)
#             elif column_type == "string":
#                 max_length = next(
#                     (field["length"] for field in obj_metadata["fields"] if field["name"] == column_name and "length" in field), 
#                     2000  # Default length
#                 )
#                 field_type = models.CharField(max_length=max_length, null=True, blank=True)

#                 # Handle External ID fields (assuming they are unique identifiers)
#             if is_external_id:
#                 field_type = models.CharField(max_length=255, null=True, blank=True, unique=True)
#             attrs[column_name] = field_type

#         model_class = register_dynamic_model("sf_integration", obj_name, attrs)

#         # Check if table exists
#         existing_tables = connection.introspection.table_names()

#         if table_name in existing_tables:
#             print(f"⚠️ Table '{table_name}' already exists. Checking for missing fields...")

#             # Ensure model is properly registered before fetching
#             apps.clear_cache()
#             model_class = apps.get_model("sf_integration", obj_name)

#             # Get existing database columns
#             with connection.cursor() as cursor:
#                 cursor.execute(f"""
#                     SELECT column_name 
#                     FROM information_schema.columns 
#                     WHERE table_name = '{table_name}';
#                 """)
#                 existing_db_fields = {row[0] for row in cursor.fetchall()}  # Fetch database column names

#             new_fields = set(columns.keys())  # Fields from Salesforce metadata
#             missing_fields = new_fields - existing_db_fields  # Fields missing in database


#             if missing_fields:
#                 with connection.schema_editor() as schema_editor:
#                     for field_name in missing_fields:
#                         field_type = attrs[field_name]  # Get field type dynamically

#                         # Manually alter the database table if schema_editor fails
#                         try:
#                             schema_editor.add_field(model_class, field_type)
#                             print(f"✅ Added missing field '{field_name}' to {obj_name}")
#                         except Exception as e:
#                             print(f"⚠️ Error adding field '{field_name}' to {obj_name}: {e}")
                            
#                             # Direct SQL fallback for adding column
#                             sql_type = "TEXT"  # Default type
#                             if isinstance(field_type, models.FloatField):
#                                 sql_type = "DOUBLE PRECISION"
#                             elif isinstance(field_type, models.IntegerField):
#                                 sql_type = "INTEGER"
#                             elif isinstance(field_type, models.BooleanField):
#                                 sql_type = "BOOLEAN"
#                             elif isinstance(field_type, models.DateTimeField):
#                                 sql_type = "TIMESTAMP"

#                             alter_sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{field_name}" {sql_type};'
#                             with connection.cursor() as cursor:
#                                 cursor.execute(alter_sql)
#                                 print(f"✅ Added missing field '{field_name}' to {obj_name} via SQL")


#             else:
#                 print(f"✅ No missing fields found in {obj_name}")

#         else:
#             print(f"✅ Creating new table '{table_name}'")
#             with connection.schema_editor() as schema_editor:
#                 schema_editor.create_model(model_class)

#         # Sync data (insert only missing records)
#         columns_list = list(columns.keys())

#         if "Id" in columns_list:
#             columns_list.remove("Id")

#         records = sf.query_all(f"SELECT Id, {', '.join(columns_list)} FROM {obj_name}")

#         existing_records = {record.Id: record for record in model_class.objects.all()}  # Fetch existing records
#         sf_record_ids = set()
#         objects_to_create = []
#         objects_to_update = []

#         for record in records["records"]:
#             record_id = record["Id"]
#             sf_record_ids.add(record_id)  # Track Salesforce IDs
#             record_data = {key: record[key] for key in columns.keys() if key in record}

#             if record_id in existing_records:
#                 # ✅ Update existing record
#                 obj = existing_records[record_id]
#                 for key, value in record_data.items():
#                     setattr(obj, key, value)
#                 objects_to_update.append(obj)
#             else:
#                 # ✅ Insert new record
#                 obj = model_class(**record_data)
#                 objects_to_create.append(obj)

#         # Bulk insert new records
#         if objects_to_create:
#             with transaction.atomic():
#                 model_class.objects.bulk_create(objects_to_create, ignore_conflicts=True)
#             print(f"✅ Inserted {len(objects_to_create)} new records for {obj_name}")

#         # Bulk update existing records
#         if objects_to_update:
#             with transaction.atomic():
#                 model_class.objects.bulk_update(objects_to_update, columns.keys())
#             print(f"✅ Updated {len(objects_to_update)} existing records for {obj_name}")

#         # ✅ Handle deletions: Remove records in the database that no longer exist in Salesforce
#         records_to_delete = model_class.objects.exclude(Id__in=sf_record_ids)
#         deleted_count = records_to_delete.count()
#         if deleted_count > 0:
#             with transaction.atomic():
#                 records_to_delete.delete()
#             print(f"🗑️ Deleted {deleted_count} records from {obj_name} that no longer exist in Salesforce")

#     print("✅ Salesforce metadata, schema, and records synced successfully!")





from django.apps import apps
from django.db import models, connection, transaction
from simple_salesforce import Salesforce
import requests

def register_dynamic_model(app_label, model_name, attrs):
    """Registers a dynamically created model in Django's app registry and ensures it is accessible."""
    
    # Check if the model is already registered
    if model_name.lower() in apps.all_models[app_label]:
        return apps.get_model(app_label, model_name)

    # Create a new model class dynamically
    model_class = type(model_name, (models.Model,), attrs)

    # Explicitly register the model
    apps.all_models[app_label][model_name.lower()] = model_class

    # Ensure Django recognizes it
    try:
        apps.get_app_config(app_label).models[model_name.lower()] = model_class
    except KeyError:
        print(f"⚠️ App '{app_label}' not found in Django. Ensure it's in INSTALLED_APPS.")

    # Clear Django’s cache to reflect model registration
    apps.clear_cache()

    return model_class


import requests
from django.conf import settings
from simple_salesforce import Salesforce

def get_salesforce_client():
    """Authenticate with Salesforce using credentials from settings.py."""
    
    username = settings.SALESFORCE_USERNAME
    password = settings.SALESFORCE_PASSWORD
    client_id = settings.SALESFORCE_CLIENT_ID
    client_secret = settings.SALESFORCE_CLIENT_SECRET

    if not all([username, password, client_id, client_secret]):
        raise Exception("One or more Salesforce credentials are missing from settings.")

    payload = {
        "grant_type": "password",
        "client_id": client_id,
        "client_secret": client_secret,
        "username": username,
        "password": password,
    }

    response = requests.post("https://login.salesforce.com/services/oauth2/token", data=payload)

    if response.status_code == 200:
        auth_response = response.json()
        return Salesforce(
            instance_url=auth_response["instance_url"],
            session_id=auth_response["access_token"]
        )
    else:
        raise Exception(f"Salesforce Authentication Failed: {response.json()}")

def fetch_salesforce_metadata():
    """Fetch metadata from Salesforce for both custom and standard objects."""
    sf = get_salesforce_client()
    
    # Fetch all Salesforce objects' metadata
    all_objects = sf.describe()["sobjects"]
    
    # Custom objects (end with '__c')
    custom_objects = [obj["name"] for obj in all_objects if obj["name"].endswith("__c")]

    # Standard objects needed for syncing
    standard_objects = ["Account", "Lead", "Opportunity", "Product2", "Task", "Contact", "Pricebook2"]

    # Combine both lists
    objects_to_sync = standard_objects + custom_objects  

    metadata = {}
    for obj_name in objects_to_sync:
        metadata[obj_name] = sf.__getattr__(obj_name).describe()
    
    return metadata


from django.db import models, connection, transaction
from django.apps import apps

def sync_metadata_and_data(single_object=None):
    """Fetch metadata, register models, update schema, and sync records."""
    metadata = fetch_salesforce_metadata()
    sf = get_salesforce_client()

    objects_to_sync = {single_object: metadata[single_object]} if single_object else metadata

    for obj_name, obj_metadata in objects_to_sync.items():
        table_name = f"sf_integration_{obj_name.lower()}"
        columns = {field["name"]: field["type"] for field in obj_metadata["fields"]}
        
        if not columns:
            continue

        # Register model dynamically
        attrs = {
            "__module__": "sf_integration.models",
            "Meta": type("Meta", (), {"app_label": "sf_integration"}),
        }

        for column_name, column_type in columns.items():
            field_type = models.CharField(max_length=2000, null=True, blank=True)
            # Check for External ID field
            is_external_id = any(field.get("externalId", False) for field in obj_metadata["fields"] if field["name"] == column_name)
            if column_type == "double":
                field_type = models.FloatField(null=True, blank=True)
            elif column_type == "boolean":
                field_type = models.BooleanField(null=True, blank=True)
            elif column_type == "int":
                field_type = models.IntegerField(null=True, blank=True)
            elif column_type == "datetime":
                field_type = models.DateTimeField(null=True, blank=True)
            elif column_type == "string":
                max_length = next(
                    (field["length"] for field in obj_metadata["fields"] if field["name"] == column_name and "length" in field), 
                    2000  # Default length
                )
                field_type = models.CharField(max_length=max_length, null=True, blank=True)

                # Handle External ID fields (assuming they are unique identifiers)
            if is_external_id:
                field_type = models.CharField(max_length=255, null=True, blank=True, unique=True)
            attrs[column_name] = field_type

        model_class = register_dynamic_model("sf_integration", obj_name, attrs)

        # Check if table exists
        existing_tables = connection.introspection.table_names()

        if table_name in existing_tables:
            print(f"⚠️ Table '{table_name}' already exists. Checking for missing fields...")

            # Ensure model is properly registered before fetching
            apps.clear_cache()
            model_class = apps.get_model("sf_integration", obj_name)

            # Get existing database columns
            with connection.cursor() as cursor:
                cursor.execute(f"""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = '{table_name}' AND table_schema = 'public';
                """)
                existing_db_fields = {row[0] for row in cursor.fetchall()}  # Fetch database column names

            new_fields = set(columns.keys())  # Fields from Salesforce metadata
            missing_fields = new_fields - existing_db_fields  # Fields missing in database


            if missing_fields:
                with connection.schema_editor() as schema_editor:
                    for field_name in missing_fields:
                        field_type = attrs[field_name]  # Get field type dynamically

                        # Manually alter the database table if schema_editor fails
                        try:
                            schema_editor.add_field(model_class, field_type)
                            print(f"✅ Added missing field '{field_name}' to {obj_name}")
                        except Exception as e:
                            print(f"⚠️ Error adding field '{field_name}' to {obj_name}: {e}")
                            
                            # Direct SQL fallback for adding column
                            sql_type = "TEXT"  # Default type
                            if isinstance(field_type, models.FloatField):
                                sql_type = "DOUBLE PRECISION"
                            elif isinstance(field_type, models.IntegerField):
                                sql_type = "INTEGER"
                            elif isinstance(field_type, models.BooleanField):
                                sql_type = "BOOLEAN"
                            elif isinstance(field_type, models.DateTimeField):
                                sql_type = "TIMESTAMP"

                            alter_sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{field_name}" {sql_type};'
                            with connection.cursor() as cursor:
                                cursor.execute(alter_sql)
                                print(f"✅ Added missing field '{field_name}' to {obj_name} via SQL")


            else:
                print(f"✅ No missing fields found in {obj_name}")

        else:
            print(f"✅ Creating new table '{table_name}'")
            with connection.schema_editor() as schema_editor:
                schema_editor.create_model(model_class)

        # Sync data (insert only missing records)
        columns_list = list(columns.keys())

        if "Id" in columns_list:
            columns_list.remove("Id")

        records = sf.query_all(f"SELECT Id, {', '.join(columns_list)} FROM {obj_name}")

        existing_records = {record.Id: record for record in model_class.objects.all()}  # Fetch existing records
        sf_record_ids = set()
        objects_to_create = []
        objects_to_update = []

        for record in records["records"]:
            record_id = record["Id"]
            sf_record_ids.add(record_id)  # Track Salesforce IDs
            record_data = {key: record[key] for key in columns.keys() if key in record}

            if record_id in existing_records:
                # ✅ Update existing record
                obj = existing_records[record_id]
                for key, value in record_data.items():
                    setattr(obj, key, value)
                objects_to_update.append(obj)
            else:
                # ✅ Insert new record
                obj = model_class(**record_data)
                objects_to_create.append(obj)

        # Bulk insert new records
        if objects_to_create:
            with transaction.atomic():
                model_class.objects.bulk_create(objects_to_create, ignore_conflicts=True)
            print(f"✅ Inserted {len(objects_to_create)} new records for {obj_name}")

        # Bulk update existing records
        if objects_to_update:
            with transaction.atomic():
                model_class.objects.bulk_update(objects_to_update, columns.keys())
            print(f"✅ Updated {len(objects_to_update)} existing records for {obj_name}")

        # ✅ Handle deletions: Remove records in the database that no longer exist in Salesforce
        records_to_delete = model_class.objects.exclude(Id__in=sf_record_ids)
        deleted_count = records_to_delete.count()
        if deleted_count > 0:
            with transaction.atomic():
                records_to_delete.delete()
            print(f"🗑️ Deleted {deleted_count} records from {obj_name} that no longer exist in Salesforce")

    print("✅ Salesforce metadata, schema, and records synced successfully!")