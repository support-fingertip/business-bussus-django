# # utils.py or service layer

# from simple_salesforce import Salesforce
# from sf_integration.salesforce_client import get_salesforce_client
# from .models import SalesforceMetadata, SalesforceSync
# from django.utils.timezone import now

# def populate_salesforce_metadata_and_sync():
#     sf = get_salesforce_client()
    
#     # Get object list
#     describe_global = sf.describe()
#     sobjects = describe_global['sobjects']

#     for sobject in sobjects:
#         name = sobject['name']
#         label = sobject['label']
#         if name.endswith('__Share') or name.endswith('__History'):
#             continue  # Skip metadata-only or system-managed tables

#         # Describe object to get fields
#         try:
#             obj_meta = sf.__getattr__(name).describe()
#         except Exception as e:
#             print(f"Skipping {name} due to error: {str(e)}")
#             continue

#         # Extract field details
#         fields = [
#             {
#                 "name": f["name"],
#                 "label": f["label"],
#                 "type": f["type"],
#                 "picklistValues": f.get("picklistValues", []),
#                 "updateable": f.get("updateable"),
#                 "createable": f.get("createable")
#             }
#             for f in obj_meta.get("fields", [])
#         ]

#         # Upsert into SalesforceMetadata
#         SalesforceMetadata.objects.update_or_create(
#             object_name=name,
#             defaults={"fields": fields, "updated_at": now()}
#         )

#         # Add default sync settings if not already present
#         SalesforceSync.objects.get_or_create(
#             object_name=name,
#             defaults={
#                 "label": label,
#                 "syncing_frequency": 60,
#                 "salesforce_pull": False,
#                 "salesforce_push": False,
#                 "is_enabled": True,
#                 "last_synced_at": None,
#             }
#         )



from simple_salesforce import Salesforce
from sf_integration.salesforce_client import get_salesforce_client
from django.utils.timezone import now
from django.db import connection
import json

from sf_integration.salesforce_client import get_salesforce_client
from django.utils.timezone import now
from django.db import connection
import json

from sf_integration.salesforce_client import get_salesforce_client
from django.utils.timezone import now
from django.db import connection
import json

from sf_integration.salesforce_client import get_salesforce_client
from django.utils.timezone import now
from django.db import connection
import json

def populate_salesforce_metadata_and_sync():
    sf = get_salesforce_client()

    describe_global = sf.describe()
    all_sobjects = describe_global['sobjects']
    current_time = now()

    # List of allowed standard object names (case-insensitive)
    allowed_standard_objects = {
        'account', 'contact', 'opportunity', 'lead', 'campaign', 'product', 'invoice',
        'target', 'quote', 'opportunity_lineitem', 'quote_line_item', 'invoice_item',
        'target_item', 'target_logic', 'product_category', 'case'
    }

    with connection.cursor() as cursor:
        for sobject in all_sobjects:
            name = sobject['name']
            label = sobject['label']
            is_custom = sobject.get('custom', False)

            if name.endswith('__Share') or name.endswith('__History'):
                continue  # Skip system objects

            name_lower = name.lower()

            # Sync if:
            # - It's a custom object (ends with '__c')
            # - OR it's one of the allowed standard objects
            if is_custom or name_lower in allowed_standard_objects:
                try:
                    obj_meta = sf.__getattr__(name).describe()
                except Exception as e:
                    print(f"Skipping {name} due to error: {str(e)}")
                    continue

                fields = [
                    {
                        "name": f["name"],
                        "label": f["label"],
                        "type": f["type"],
                        "picklistValues": f.get("picklistValues", []),
                        "updateable": f.get("updateable"),
                        "createable": f.get("createable")
                    }
                    for f in obj_meta.get("fields", [])
                ]

                fields_json = json.dumps(fields)

                # Upsert into salesforce_metadata
                cursor.execute("""
                    INSERT INTO salesforce_metadata (object_name, fields, created_at, updated_at)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (object_name)
                    DO UPDATE SET fields = EXCLUDED.fields, updated_at = EXCLUDED.updated_at;
                """, [name, fields_json, current_time, current_time])

                # Insert into salesforce_sync if not already present
                cursor.execute("""
                    INSERT INTO salesforce_sync (
                        object_name, label, syncing_frequency,
                        salesforce_pull, salesforce_push, is_enabled, last_synced_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (object_name) DO NOTHING;
                """, [name, label, 60, False, False, True, None])
