from django.db import connection
from django.http import JsonResponse
from sf_integration.utils import populate_salesforce_metadata_and_sync
from django.shortcuts import render, redirect
from .forms import SalesforceSettingsForm
from .salesforce_client import sync_metadata_and_data
from .models import SalesforceSettings
from rest_framework.response import Response
from rest_framework.decorators import api_view



# def salesforce_settings(request):
#     settings = SalesforceSettings.objects.first()
    
#     if request.method == "POST":
#         form = SalesforceSettingsForm(request.POST, instance=settings)
#         if form.is_valid():
#             form.save()
#             sync_metadata_and_data()  # Trigger sync
#             return redirect('salesforce_settings')
#     else:
#         form = SalesforceSettingsForm(instance=settings)

#     return render(request, 'salesforce_settings.html', {'form': form})


@api_view(['GET'])
def get_salesforce_sync(request):
    with connection.cursor() as cursor:
        cursor.execute("SELECT * FROM salesforce_sync;")
        records = cursor.fetchall()
        columns = [col[0] for col in cursor.description]
        
        # Convert each record tuple into a dict with column names as keys
        data = [dict(zip(columns, row)) for row in records]

    return JsonResponse(data, safe=False, status=200)


from django.http import JsonResponse
from rest_framework.decorators import api_view
from django.db import connection

# @api_view(['PATCH'])
# def update_salesforce_sync(request):
#     request_data = request.data
#     object_name = request_data.get("object_name")

#     if not object_name:
#         return JsonResponse({"error": "object_name is required"}, status=400)

#     with connection.cursor() as cursor:
#         # Step 1: Check if record exists (case-insensitive)
#         cursor.execute("SELECT * FROM salesforce_sync WHERE LOWER(object_name) = LOWER(%s) LIMIT 1;", [object_name])
#         record = cursor.fetchone()

#         if not record:
#             return JsonResponse({"error": f"Record not found for {object_name}"}, status=404)

#         # Step 2: Prepare update fields
#         update_fields = {k: v for k, v in request_data.items() if k != "object_name"}

#         if not update_fields:
#             return JsonResponse({"error": "No fields to update"}, status=400)

#         set_clause = ", ".join(f"{k} = %s" for k in update_fields.keys())
#         values = list(update_fields.values()) + [object_name]

#         # Step 3: Execute update
#         sql = f"""
#             UPDATE salesforce_sync
#             SET {set_clause}
#             WHERE LOWER(object_name) = LOWER(%s)
#             RETURNING *;
#         """
#         cursor.execute(sql, values)
#         updated_record = cursor.fetchone()

#         columns = [desc[0] for desc in cursor.description]
#         data = dict(zip(columns, updated_record))

#     return JsonResponse(data, status=200)


from rest_framework.decorators import api_view
from django.http import JsonResponse
from django.db import connection

@api_view(['PATCH'])
def update_salesforce_sync(request):
    request_data = request.data

    if not isinstance(request_data, list) or not request_data:
        return JsonResponse({"error": "Request body must be a non-empty list"}, status=400)

    updated_records = []

    with connection.cursor() as cursor:
        for item in request_data:
            object_name = item.get("object_name")
            if not object_name:
                continue  # Skip invalid records

            # Check if record exists
            cursor.execute("SELECT * FROM salesforce_sync WHERE LOWER(object_name) = LOWER(%s) LIMIT 1;", [object_name])
            record = cursor.fetchone()
            if not record:
                continue  # Skip non-existing records

            # Prepare update fields
            update_fields = {k: v for k, v in item.items() if k != "object_name"}
            if not update_fields:
                continue

            set_clause = ", ".join(f"{k} = %s" for k in update_fields)
            values = list(update_fields.values()) + [object_name]

            sql = f"""
                UPDATE salesforce_sync
                SET {set_clause}
                WHERE LOWER(object_name) = LOWER(%s)
                RETURNING *;
            """
            cursor.execute(sql, values)
            updated = cursor.fetchone()
            if updated:
                columns = [desc[0] for desc in cursor.description]
                updated_records.append(dict(zip(columns, updated)))

    return JsonResponse(updated_records, safe=False, status=200)



@api_view(["POST"])
def sync_salesforce_metadata(request):
    try:
        populate_salesforce_metadata_and_sync()
        return Response({"status": "success", "message": "Metadata synced"})
    except Exception as e:
        return Response({"status": "error", "message": str(e)}, status=500)
