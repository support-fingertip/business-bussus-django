# import psycopg2
# import json
# import requests
# import os
# import environ
# import django

# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'version2.settings')  # Replace with your actual Django project name
# django.setup()

# from dotenv import load_dotenv
# from sf_integration.salesforce_client import get_salesforce_client

# # Load environment variables
# load_dotenv()

# # Initialize environment variables
# env = environ.Env(DEBUG=(bool, False))  # Default DEBUG=False

# # PostgreSQL Database Connection
# DB_CONFIG = {
#     "dbname": "version2",
#     "user": "djangouser",
#     "password": "Django@1",
#     "host": '88.222.241.78',
#     "port": "5432"
# }

# SALESFORCE_URL = "https://bussus2-dev-ed.develop.my.salesforce.com/services/data/v59.0/sobjects"

# def get_salesforce_headers():
#     """
#     Retrieves a fresh Salesforce access token and constructs the authorization headers.
#     """
#     try:
#         sf_client = get_salesforce_client()
#         return {
#             "Authorization": f"Bearer {sf_client.session_id}",
#             "Content-Type": "application/json"
#         }
#     except Exception as e:
#         print(f"\U0001F6A8 Salesforce Authentication Failed: {e}")
#         return None

# def sync_to_salesforce(data):
#     operation = data.get("operation")
#     table = data.get("table")
#     record = data.get("data")
    
#     if not record:
#         print("❌ No data to sync.")
#         return

#     salesforce_object = table.replace("sf_integration_", "").title()  # Convert table name dynamically
#     salesforce_id = record.pop("Id", None)
#     headers = get_salesforce_headers()
    
#     if not headers:
#         print("❌ Unable to sync: Failed to get Salesforce headers.")
#         return

#     print(f"📤 Attempting {operation} operation on Salesforce Object: {salesforce_object}")
#     print(f"🔄 Payload: {json.dumps(record, indent=2)}")

#     try:
#         response = None
#         if operation == "INSERT":
#             local_db_id = record.get("id")  # Store local database ID before modifying record
#             record.pop("id", None)

#             record = {k: v for k, v in record.items() if v is not None}
            
#             url = f"{SALESFORCE_URL}/{salesforce_object}/"
#             response = requests.post(url, json=record, headers=headers)
            
#             if response.status_code in [200, 201]:
#                 sf_response = response.json()
#                 new_sf_id = sf_response.get("id")
#                 print(f"✅ Record Created in Salesforce with ID: {new_sf_id}")
                
#                 if new_sf_id and local_db_id:
#                     update_query = f"UPDATE {table} SET \"Id\" = '{new_sf_id}' WHERE id = {local_db_id};"
#                     with psycopg2.connect(**DB_CONFIG) as conn:
#                         with conn.cursor() as cur:
#                             cur.execute(update_query)
#                             conn.commit()
#                     print(f"✅ Updated PostgreSQL with Salesforce ID: {new_sf_id}")
#             else:
#                 print(f"❌ Failed to insert: {response.status_code} - {response.text}")

#         elif operation == "UPDATE":
#             if not salesforce_id:
#                 print(f"❌ Missing Salesforce Id for UPDATE: {record}")
#                 return
#             url = f"{SALESFORCE_URL}/{salesforce_object}/{salesforce_id}"
#             record.pop("id", None)
#             record = {k: v for k, v in record.items() if v is not None}
#             response = requests.patch(url, json=record, headers=headers)
#             print(f"📤 Salesforce Response: {response.status_code}, {response.text}")

#         elif operation == "DELETE":
#             if not salesforce_id:
#                 print(f"❌ Missing Salesforce Id for DELETE: {record}")
#                 return
#             url = f"{SALESFORCE_URL}/{salesforce_object}/{salesforce_id}"
#             response = requests.delete(url, headers=headers)
#             print(f"📤 Salesforce Response: {response.status_code}, {response.text}")

#         if response and response.status_code in [200, 201, 204]:
#             print(f"✅ Successfully synced {operation} for object {salesforce_object}")
#         else:
#             print(f"❌ Failed to sync {operation}: {response.text}")

#     except Exception as e:
#         print(f"🚨 Error syncing data: {e}")

# def listen_for_changes():
#     """
#     Listens to PostgreSQL notifications and syncs data with Salesforce.
#     """
#     try:
#         conn = psycopg2.connect(**DB_CONFIG)
#         conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
#         cursor = conn.cursor()

#         cursor.execute("LISTEN salesforce_sync;")
#         print("Listening for database changes...")

#         while True:
#             conn.poll()
#             while conn.notifies:
#                 notify = conn.notifies.pop(0)
#                 data = json.loads(notify.payload)
#                 print(f"Received notification: {data}")
#                 sync_to_salesforce(data)
#     except Exception as e:
#         print(f"Error in listening process: {e}")

# if __name__ == "__main__":
#     listen_for_changes()














































































































#--------------WITH FOREIGN KEYS----------------------


# import psycopg2
# import json
# import requests
# import os
# import environ
# import django

# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'version2.settings')  # Replace with your actual Django project name
# django.setup()

# from dotenv import load_dotenv
# from sf_integration.salesforce_client import get_salesforce_client

# # Load environment variables
# load_dotenv()

# # Initialize environment variables
# env = environ.Env(DEBUG=(bool, False))  # Default DEBUG=False

# # PostgreSQL Database Connection
# DB_CONFIG = {
#     "dbname": "version2",
#     "user": "djangouser",
#     "password": "Django@1",
#     "host": '88.222.241.78',
#     "port": "5432"
# }

# SALESFORCE_URL = "https://bussus2-dev-ed.develop.my.salesforce.com/services/data/v59.0/sobjects"

# def get_salesforce_headers():
#     """
#     Retrieves a fresh Salesforce access token and constructs the authorization headers.
#     """
#     try:
#         sf_client = get_salesforce_client()
#         return {
#             "Authorization": f"Bearer {sf_client.session_id}",
#             "Content-Type": "application/json"
#         }
#     except Exception as e:
#         print(f"\U0001F6A8 Salesforce Authentication Failed: {e}")
#         return None


# def get_foreign_keys():
#     """
#     Fetches all foreign key relationships for sf_integration_ tables.
#     Returns a dictionary mapping child table columns to parent table columns.
#     """
#     query = """
#     SELECT 
#         conrelid::regclass AS child_table,
#         conname AS constraint_name,
#         a.attname AS child_column,
#         confrelid::regclass AS parent_table,
#         af.attname AS parent_column
#     FROM pg_constraint c
#     JOIN pg_attribute a ON a.attnum = ANY(c.conkey) AND a.attrelid = c.conrelid
#     JOIN pg_attribute af ON af.attnum = ANY(c.confkey) AND af.attrelid = c.confrelid
#     WHERE c.contype = 'f' AND c.conrelid::regclass::text LIKE 'sf_integration_%';
#     """

#     foreign_keys = {}
#     with psycopg2.connect(**DB_CONFIG) as conn:
#         with conn.cursor() as cur:
#             cur.execute(query)
#             results = cur.fetchall()
#             for child_table, constraint, child_col, parent_table, parent_col in results:
#                 foreign_keys[(child_table, child_col)] = (parent_table, parent_col)
#     return foreign_keys

# def resolve_parent_id(record, table, foreign_keys):
#     """
#     Replaces local parent ID references with the corresponding Salesforce ID.
#     If a parent Salesforce ID is missing, return None to delay syncing.
#     """
#     for (child_table, child_col), (parent_table, parent_col) in foreign_keys.items():
#         if table == child_table and child_col in record:
#             local_parent_id = record[child_col]

#             # Fetch the corresponding Salesforce ID from the parent table
#             query = f'SELECT "Id" FROM {parent_table} WHERE id = %s;'
#             with psycopg2.connect(**DB_CONFIG) as conn:
#                 with conn.cursor() as cur:
#                     cur.execute(query, (local_parent_id,))
#                     result = cur.fetchone()

#             if result and result[0]:  # If parent Salesforce ID exists
#                 record[child_col] = result[0]
#             else:
#                 print(f"🔄 Parent record ({parent_table}) not synced yet. Delaying child record sync.")
#                 return None  # Delay syncing this record until parent is available

#     return record  # Return updated record with Salesforce parent IDs

# def sync_to_salesforce(data):
#     operation = data.get("operation")
#     table = data.get("table")
#     record = data.get("data")

#     if not record:
#         print("❌ No data to sync.")
#         return

#     foreign_keys = get_foreign_keys()  # Get FK relationships dynamically
#     updated_record = resolve_parent_id(record, table, foreign_keys)

#     if updated_record is None:
#         print(f"🚨 Delaying sync for {table} due to missing parent record.")
#         return  # Skip sync for now, parent not ready

#     salesforce_object = table.replace("sf_integration_", "").title()
#     salesforce_id = updated_record.pop("Id", None)
#     headers = get_salesforce_headers()

#     if not headers:
#         print("❌ Unable to sync: Failed to get Salesforce headers.")
#         return

#     print(f"📤 Syncing {operation} operation on {salesforce_object}")
#     try:
#         response = None
#         if operation == "INSERT":
#             local_db_id = updated_record.get("id")
#             updated_record.pop("id", None)  # Remove local ID before sending to Salesforce
#             updated_record = {k: v for k, v in updated_record.items() if v is not None}

#             url = f"{SALESFORCE_URL}/{salesforce_object}/"
#             response = requests.post(url, json=updated_record, headers=headers)

#             if response.status_code in [200, 201]:
#                 sf_response = response.json()
#                 new_sf_id = sf_response.get("id")
#                 print(f"✅ Record Created in Salesforce with ID: {new_sf_id}")

#                 # Update PostgreSQL with Salesforce ID
#                 if new_sf_id and local_db_id:
#                     update_query = f'UPDATE {table} SET "Id" = %s WHERE id = %s;'
#                     with psycopg2.connect(**DB_CONFIG) as conn:
#                         with conn.cursor() as cur:
#                             cur.execute(update_query, (new_sf_id, local_db_id))
#                             conn.commit()
#                     print(f"✅ Updated PostgreSQL with Salesforce ID: {new_sf_id}")

#             else:
#                 print(f"❌ Failed to insert: {response.status_code} - {response.text}")

#         elif operation == "UPDATE":
#             if not salesforce_id:
#                 print(f"❌ Missing Salesforce Id for UPDATE: {updated_record}")
#                 return
#             url = f"{SALESFORCE_URL}/{salesforce_object}/{salesforce_id}"
#             updated_record.pop("id", None)
#             updated_record = {k: v for k, v in updated_record.items() if v is not None}
#             response = requests.patch(url, json=updated_record, headers=headers)

#         elif operation == "DELETE":
#             if not salesforce_id:
#                 print(f"❌ Missing Salesforce Id for DELETE: {updated_record}")
#                 return
#             url = f"{SALESFORCE_URL}/{salesforce_object}/{salesforce_id}"
#             response = requests.delete(url, headers=headers)

#         if response and response.status_code in [200, 201, 204]:
#             print(f"✅ Successfully synced {operation} for {salesforce_object}")
#         else:
#             print(f"❌ Failed to sync {operation}: {response.text}")

#     except Exception as e:
#         print(f"🚨 Error syncing data: {e}")

# def listen_for_changes():
#     """
#     Listens to PostgreSQL notifications and syncs data with Salesforce.
#     """
#     try:
#         conn = psycopg2.connect(**DB_CONFIG)
#         conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
#         cursor = conn.cursor()

#         cursor.execute("LISTEN salesforce_sync;")
#         print("Listening for database changes...")

#         while True:
#             conn.poll()
#             while conn.notifies:
#                 notify = conn.notifies.pop(0)
#                 data = json.loads(notify.payload)
#                 print(f"Received notification: {data}")
#                 sync_to_salesforce(data)
#     except Exception as e:
#         print(f"Error in listening process: {e}")

# if __name__ == "__main__":
#     listen_for_changes()







#-----------------WITHOUT EID SYNC----------------------


import psycopg2
import json
import requests
import os
import environ
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'version2.settings')  # Replace with your actual Django project name
django.setup()

from dotenv import load_dotenv
from sf_integration.salesforce_client import get_salesforce_client

# Load environment variables
load_dotenv()

# Initialize environment variables
env = environ.Env(DEBUG=(bool, False))  # Default DEBUG=False

# PostgreSQL Database Connection
DB_CONFIG = {
    "dbname": "version2",
    "user": "djangouser",
    "password": "Django@1",
    "host": '88.222.241.78',
    "port": "5432"
}

SALESFORCE_URL = "https://bussus2-dev-ed.develop.my.salesforce.com/services/data/v59.0/sobjects"

def get_salesforce_headers():
    """
    Retrieves a fresh Salesforce access token and constructs the authorization headers.
    """
    try:
        sf_client = get_salesforce_client()
        return {
            "Authorization": f"Bearer {sf_client.session_id}",
            "Content-Type": "application/json"
        }
    except Exception as e:
        print(f"\U0001F6A8 Salesforce Authentication Failed: {e}")
        return None
    
def get_foreign_keys():
    """
    Fetches all foreign key relationships for sf_integration_ tables.
    Returns a dictionary mapping child table columns to parent table columns.
    """
    query = """
    SELECT 
        conrelid::regclass AS child_table,
        conname AS constraint_name,
        a.attname AS child_column,
        confrelid::regclass AS parent_table,
        af.attname AS parent_column
    FROM pg_constraint c
    JOIN pg_attribute a ON a.attnum = ANY(c.conkey) AND a.attrelid = c.conrelid
    JOIN pg_attribute af ON af.attnum = ANY(c.confkey) AND af.attrelid = c.confrelid
    WHERE c.contype = 'f' AND c.conrelid::regclass::text LIKE 'sf_integration_%';
    """

    foreign_keys = {}
    with psycopg2.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            results = cur.fetchall()
            for child_table, constraint, child_col, parent_table, parent_col in results:
                foreign_keys[(child_table, child_col)] = (parent_table, parent_col)
    return foreign_keys

def resolve_parent_id(record, table, foreign_keys):
    """
    Replaces local parent ID references with the corresponding Salesforce ID.
    If a parent Salesforce ID is missing, return None to delay syncing.
    """
    for (child_table, child_col), (parent_table, parent_col) in foreign_keys.items():
        if table == child_table and child_col in record:
            local_parent_id = record[child_col]

            # Fetch the corresponding Salesforce ID from the parent table
            query = f'SELECT "Id" FROM {parent_table} WHERE id = %s;'
            with psycopg2.connect(**DB_CONFIG) as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (local_parent_id,))
                    result = cur.fetchone()

            if result and result[0]:  # If parent Salesforce ID exists
                record[child_col] = result[0]
            else:
                print(f"🔄 Parent record ({parent_table}) not synced yet. Delaying child record sync.")
                return None  # Delay syncing this record until parent is available

    return record  # Return updated record with Salesforce parent IDs

from simple_salesforce import Salesforce

def get_salesforce_metadata(object_name):
    """
    Fetch metadata for a given Salesforce object and determine the External ID field.
    """
    try:
        sf_client = get_salesforce_client()  # Use the existing function to authenticate
        metadata = sf_client.__getattr__(object_name).describe()
        
        external_id_field = None
        for field in metadata['fields']:
            if field.get("externalId"):  # Check if it's an External ID field
                external_id_field = field["name"]
                break  # Take the first External ID field found

        return external_id_field  # Returns the field name or None if not found
    except Exception as e:
        print(f"❌ Error fetching metadata for {object_name}: {e}")
        return None


def sync_to_salesforce(data):
    operation = data.get("operation")
    table = data.get("table")
    record = data.get("data")

    if not record:
        print("❌ No data to sync.")
        return

    foreign_keys = get_foreign_keys()  # Get FK relationships dynamically
    updated_record = resolve_parent_id(record, table, foreign_keys)

    if updated_record is None:
        print(f"🚨 Delaying sync for {table} due to missing parent record.")
        return  # Skip sync for now, parent not ready

    salesforce_object = table.replace("sf_integration_", "").title()
    local_db_id = updated_record.get("id")  # Get the local database ID
    
    # Fetch the correct External ID field name(Create EID in salesforce with the name A_EID)
    external_id_field = get_salesforce_metadata(salesforce_object)

    if external_id_field:
        updated_record[external_id_field] = f"EID{local_db_id}"  # Set the correct External ID field dynamically

    salesforce_id = updated_record.pop("Id", None)  # Remove Salesforce Id from the request payload
    headers = get_salesforce_headers()

    if not headers:
        print("❌ Unable to sync: Failed to get Salesforce headers.")
        return

    print(f"📤 Syncing {operation} operation on {salesforce_object}")
    try:
        response = None
        if operation == "INSERT":
            updated_record.pop("id", None)  # Remove local ID before sending to Salesforce
            updated_record = {k: v for k, v in updated_record.items() if v is not None}

            url = f"{SALESFORCE_URL}/{salesforce_object}/"
            response = requests.post(url, json=updated_record, headers=headers)

            if response.status_code in [200, 201]:
                sf_response = response.json()
                new_sf_id = sf_response.get("id")
                external_id_value = updated_record.get(external_id_field) if external_id_field else None

                print(f"✅ Record Created in Salesforce with ID: {new_sf_id}")

                # Update PostgreSQL with Salesforce ID and External ID
                if new_sf_id and local_db_id:
                    update_query = f'UPDATE {table} SET "Id" = %s'
                    params = [new_sf_id]

                    if external_id_value:
                        update_query += f', "{external_id_field}" = %s'
                        params.append(external_id_value)

                    update_query += " WHERE id = %s;"
                    params.append(local_db_id)

                    with psycopg2.connect(**DB_CONFIG) as conn:
                        with conn.cursor() as cur:
                            cur.execute(update_query, tuple(params))
                            conn.commit()
                    print(f"✅ Updated PostgreSQL with Salesforce ID: {new_sf_id} and External ID: {external_id_value}")

            else:
                print(f"❌ Failed to insert: {response.status_code} - {response.text}")

        elif operation == "UPDATE":
            if not salesforce_id:
                print(f"❌ Missing Salesforce Id for UPDATE: {updated_record}")
                return
            url = f"{SALESFORCE_URL}/{salesforce_object}/{salesforce_id}"
            updated_record.pop("id", None)
            updated_record = {k: v for k, v in updated_record.items() if v is not None}
            response = requests.patch(url, json=updated_record, headers=headers)

        elif operation == "DELETE":
            if not salesforce_id:
                print(f"❌ Missing Salesforce Id for DELETE: {updated_record}")
                return
            url = f"{SALESFORCE_URL}/{salesforce_object}/{salesforce_id}"
            response = requests.delete(url, headers=headers)

        if response and response.status_code in [200, 201, 204]:
            print(f"✅ Successfully synced {operation} for {salesforce_object}")
        else:
            print(f"❌ Failed to sync {operation}: {response.text}")

    except Exception as e:
        print(f"🚨 Error syncing data: {e}")


def listen_for_changes():
    """
    Listens to PostgreSQL notifications and syncs data with Salesforce.
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        cursor = conn.cursor()

        cursor.execute("LISTEN salesforce_sync;")
        print("Listening for database changes...")

        while True:
            conn.poll()
            while conn.notifies:
                notify = conn.notifies.pop(0)
                data = json.loads(notify.payload)
                print(f"Received notification: {data}")
                sync_to_salesforce(data)
    except Exception as e:
        print(f"Error in listening process: {e}")

if __name__ == "__main__":
    listen_for_changes()


    