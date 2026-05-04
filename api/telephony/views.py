# from django.http import JsonResponse
# from django.views.decorators.csrf import csrf_exempt
# import json

# # A helper function to run raw SQL queries and return result as dicts
# def run_query(query, params=None):
#     from django.db import connection
#     with connection.cursor() as cursor:
#         cursor.execute(query, params or [])
#         columns = [col[0] for col in cursor.description]
#         rows = cursor.fetchall()
#         return [dict(zip(columns, row)) for row in rows]

# # Simple in-memory store for round robin pointer (use Redis in prod)
# round_robin_pointers = {}

# @csrf_exempt
# def telephony_route(request, telephony_id):
#     print("📞 telephony_route HIT")
#     try:
#         print("Request method:", request.method)
#         if request.method != 'POST':
#             return JsonResponse({'error': 'Method not allowed'}, status=405)

#         print("Request body:", request.body)
#         data = json.loads(request.body)

#         landing_number = data.get('landing_number') or data.get('calledNumber')
#         print("Landing Number:", landing_number)

#         if not landing_number:
#             return JsonResponse({'error': 'landing_number is required'}, status=400)

#         # Step 1: Find landing number config
#         landing_query = """
#             SELECT group_id, routing_logic 
#             FROM landing_numbers 
#             WHERE telephony_id=%s AND landing_number=%s
#         """
#         landing_result = run_query(landing_query, [telephony_id, landing_number])
#         print("Landing Query Result:", landing_result)

#         if not landing_result:
#             return JsonResponse({'error': 'Landing number not configured'}, status=404)

#         group_id = landing_result[0]['group_id']
#         routing_logic = landing_result[0]['routing_logic']
#         print("Group:", group_id, "Routing Logic:", routing_logic)

#         # Step 2: Find all users in the group
#         users_query = """
#             SELECT u.id, u.phone
#             FROM users u
#             JOIN user_group_users ugu ON u.id = ugu.user_id
#             WHERE ugu.user_group_id = %s
#             ORDER BY u.id
#         """
#         users = run_query(users_query, [group_id])

#         print("Users in group:", users)

#         if not users:
#             return JsonResponse({'error': 'No users in the group'}, status=404)

#         # Step 3: Routing logic
#         selected_user = None

#         if routing_logic == 'round_robin':
#             pointer = round_robin_pointers.get(group_id, 0)
#             selected_user = users[pointer % len(users)]
#             round_robin_pointers[group_id] = (pointer + 1) % len(users)

#         elif routing_logic == 'next_available':
#             selected_user = users[0]

#         elif routing_logic == 'no_routing':
#             return JsonResponse({'agent_assigned': False})

#         else:
#             return JsonResponse({'error': 'Unknown routing logic'}, status=400)

#         # Final response
#         return JsonResponse({
#             'action': 'connect',
#             'number': selected_user['phone']
#         })

#     except Exception as e:
#         print("🔥 ERROR:", str(e))
#         return JsonResponse({'success': False, 'error': str(e)}, status=500)



import logging
import os

from django.http import JsonResponse,HttpResponse
from django.views.decorators.csrf import csrf_exempt
import json
from django.utils.dateparse import parse_datetime
from asgiref.sync import async_to_sync
from twilio.rest import Client
from django.conf import settings

from api.security.webhook_verification import verify_hmac_signature

logger = logging.getLogger(__name__)


def _verify_voxbay_signature(request) -> bool:
    """Reject Voxbay webhook requests that don't carry a valid HMAC.

    Operator: set ``VOXBAY_WEBHOOK_SECRET`` and configure Voxbay to send
    ``X-Voxbay-Signature: sha256=<hex>`` over the raw body.

    During the rollout window you can set ``VOXBAY_WEBHOOK_ENFORCE=0`` to
    log-only-mode (still records every rejection in logs) so the provider
    has time to add signing without dropping live calls. Default behaviour
    is **enforce**.
    """
    raw_body = request.body
    sig = request.headers.get("X-Voxbay-Signature") or request.META.get("HTTP_X_VOXBAY_SIGNATURE")
    ok = verify_hmac_signature(raw_body, sig, "VOXBAY_WEBHOOK_SECRET")
    if ok:
        return True
    if os.getenv("VOXBAY_WEBHOOK_ENFORCE", "1") == "0":
        logger.warning(
            "Voxbay webhook signature failed (log-only mode); accepting %s",
            request.path,
        )
        return True
    return False
from twilio.twiml.voice_response import VoiceResponse
from twilio.jwt.client import ClientCapabilityToken
from channels.layers import get_channel_layer

def run_query(query, params=None, schema=None):
    """Execute a parameterized query safely; optionally set schema after validating it."""
    from django.db import connection
    from api.ORM.sqlFunctions.utils.helpers import validate_identifier
    with connection.cursor() as cursor:
        if schema:
            # Strict identifier validation: rejects anything that isn't a
            # valid SQL identifier (letters, digits, underscores, must
            # start with a letter or underscore, max 63 chars). Stops
            # injection attempts via crafted schema names.
            validate_identifier(schema, "schema")
            cursor.execute("SET search_path TO %s", [schema])
        cursor.execute(query, params or [])
        result = []

        if cursor.description:
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
            result = [dict(zip(columns, row)) for row in rows]

        connection.commit()  # ✅ Always commit after execution
        return result


# @csrf_exempt
# def telephony_connecting(request, telephony_id):
#     if request.method != 'POST':
#         return JsonResponse({'error': 'Method not allowed'}, status=405)

#     try:
#         data = json.loads(request.body)
#         from_number = data.get('from_number')
#         start_time_str = data.get('start_time')
#         call_id = data.get('call_id')
#         call_type = data.get('call_type')
#         to_number = data.get('to_number')

#         # Validate essential parameters
#         if not from_number or not call_id:
#             return JsonResponse({'error': 'Missing required params: from_number or call_id'}, status=400)

#         # Parse start_time to datetime object (if provided)
#         start_time = parse_datetime(start_time_str) if start_time_str else None

#         # Step 1: Get telephony config for this telephony_id
#         config_query = """
#             SELECT target_object, target_field, display_fields,disposition_values
#             FROM telephony_config WHERE id = %s
#         """
#         config_result = run_query(config_query, [telephony_id])
#         if not config_result:
#             return JsonResponse({'error': 'Telephony config not found'}, status=404)
#         config = config_result[0]

#         target_object = config['target_object']      # e.g. 'lead'
#         target_field = config['target_field']        # e.g. 'phone'
#         display_fields_raw = config.get('display_fields') or []
#         disposition_values_raw = config.get('disposition_values') or []

#         if isinstance(display_fields_raw, str):
#             display_fields = [f.strip() for f in display_fields_raw.split(',')]
#         elif isinstance(display_fields_raw, list):
#             display_fields = display_fields_raw

#         if isinstance(disposition_values_raw, str):
#             disposition_values = [d.strip() for d in disposition_values_raw.split(',')]
#         else:
#             disposition_values = disposition_values_raw
#         # else:
#         #     display_fields = []


#         # Step 2: Try to find matching record by phone number
#         search_query = f"SELECT id, {', '.join(display_fields)} FROM {target_object} WHERE {target_field} = %s LIMIT 1"
#         matched = run_query(search_query, [from_number])

#         if matched:
#             matched_record = matched[0]
#             matched_record_id = matched_record['id']
#         else:
#             # Create a new record with phone number only
#             import uuid
#             new_id = str(uuid.uuid4())
#             insert_query = f"INSERT INTO {target_object} (id, {target_field}) VALUES (%s, %s) RETURNING id"
#             inserted = run_query(insert_query, [new_id, from_number])

#             matched_record_id = inserted[0]['id']
#             # Prepare a default empty matched_record dict for display
#             matched_record = {field: None for field in display_fields}
#             matched_record['id'] = matched_record_id

#         # Step 3: Insert call log entry
#         insert_call_log = """
#             INSERT INTO call (telephony_id, from_number, to_number, start_time, call_type, call_id, matched_record_id, matched_object)
#             VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
#         """
#         run_query(insert_call_log, [telephony_id, from_number, to_number, start_time, call_type, call_id, matched_record_id, target_object])

#         # Step 4: Emit popup event via Channels (WebSocket)
#         channel_layer = get_channel_layer()
#         async_to_sync(channel_layer.group_send)(
#             "telephony_popup_group",  # Customize if needed per user/session
#             {
#                 "type": "show_popup",
#                 "data": {
#                     "telephony_id": telephony_id,
#                     "call_id": call_id,
#                     "matched_record": matched_record,
#                     "display_fields": display_fields,
#                     "from_number": from_number,
#                     "call_type": call_type,
#                     "to_number": to_number,
#                     "disposition_values": disposition_values
#                 }
#             }
#         )
        

#         return JsonResponse({'status': 'popup triggered'})

#     except Exception as e:
#         print("🔥 ERROR in telephony_connecting:", str(e))
#         return JsonResponse({'error': str(e)}, status=500)



# @csrf_exempt
# def telephony_hangup(request, telephony_id):
#     if request.method != 'POST':
#         return JsonResponse({'error': 'Method not allowed'}, status=405)

#     data = json.loads(request.body)
#     call_id = data.get('call_id')
#     end_time = parse_datetime(data.get('end_time'))
#     duration = data.get('duration')
#     recording_file = data.get('recording_file')
#     disposition = data.get('disposition')
#     description = data.get('description')
#     call_status = data.get('call_status')

#     if not call_id or not end_time:
#         return JsonResponse({'error': 'Missing required parameters'}, status=400)

#     update_query = """
#         UPDATE call SET
#             end_time=%s,
#             duration=%s,
#             recording_file=%s,
#             disposition=%s,
#             description=%s,
#             call_status=%s
#         WHERE call_id=%s AND telephony_id=%s
#     """
#     run_query(update_query, [end_time, duration, recording_file, disposition, description, call_status, call_id, telephony_id])

#     return JsonResponse({'status': 'call log updated'})







# @csrf_exempt
# def telephony_outgoing(request, telephony_id):
#     if request.method != 'POST':
#         return JsonResponse({'error': 'Method not allowed'}, status=405)

#     import requests
#     import json

#     data = json.loads(request.body)
#     customer_number = data.get('customer_number')

#     # Replace with your actual UID, PIN, and extension
#     uid = "b8go8318rz"
#     pin = "niyxxfhiun"
#     ext_number = "101"
    
#     # Correct API endpoint
#     voxbay_api_url = (
#         f"https://pbx.voxbaysolutions.com/api/call.php?"
#         f"uid={uid}&pin={pin}&ext={ext_number}&destination={customer_number}"
#     )

#     response = requests.get(voxbay_api_url)

#     return JsonResponse({
#         "status_code": response.status_code,
#         "text": response.text
#     })




from urllib.parse import urlencode


import requests
import json

@csrf_exempt
def telephony_outgoing(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    if not _verify_voxbay_signature(request):
        return JsonResponse({"error": "Invalid signature"}, status=401)

    # Credentials sourced from environment. The previously hardcoded values
    # have been rotated and must now be supplied by the operator. If any are
    # missing we fail fast rather than placing a real call with stale creds.
    UID = os.getenv("VOXBAY_UID")
    PIN = os.getenv("VOXBAY_PIN")
    EXT = os.getenv("VOXBAY_EXT", "108")
    CALLER_ID = os.getenv("VOXBAY_CALLER_ID")
    DESTINATIONNUMBER = os.getenv("VOXBAY_DESTINATION_NUMBER")
    if not (UID and PIN and CALLER_ID and DESTINATIONNUMBER):
        logger.error("telephony_outgoing missing Voxbay env vars")
        return JsonResponse(
            {"error": "Telephony not configured."}, status=503
        )

    # Use requests params= so values are URL-encoded; never f-string into a URL.
    params = {
        "id_dept": 0,
        "uid": UID,
        "upin": PIN,
        "user_no": EXT,
        "destination": DESTINATIONNUMBER,
    }
    try:
        response = requests.get(
            "https://x.voxbay.com/api/click_to_call",
            params=params,
            timeout=10,
        )
        logger.info("telephony_outgoing voxbay_status=%s", response.status_code)
    except requests.RequestException as exc:
        logger.error("telephony_outgoing voxbay request failed: %s", exc)
        return JsonResponse({"error": "Upstream telephony failure."}, status=502)
    return JsonResponse(data={}, status=200)






def accept_call(request):
    # Voxbay creds come from environment. Failing fast beats placing a call
    # with stale, leaked-into-source credentials.
    UID = os.getenv("VOXBAY_UID")
    PIN = os.getenv("VOXBAY_PIN")
    EXT = os.getenv("VOXBAY_EXT", "108")
    CALLER_ID = os.getenv("VOXBAY_CALLER_ID")
    if not (UID and PIN and CALLER_ID):
        logger.error("accept_call missing Voxbay env vars")
        return JsonResponse({"status": "error", "message": "Telephony not configured."}, status=503)

    source = request.GET.get('agent_number')
    destination = request.GET.get('customer_number')
    if not (source and destination):
        return JsonResponse(
            {"status": "error", "message": "agent_number and customer_number are required."},
            status=400,
        )

    params = {
        "uid": UID,
        "pin": PIN,
        "source": source,
        "destination": destination,
        "ext": EXT,
        "callerid": CALLER_ID,
    }

    try:
        response = requests.get(
            "https://pbx.voxbaysolutions.com/api/clicktocall.php",
            params=params,
            timeout=10,
        )
        response_data = response.json()
        if response.status_code == 200 and response_data.get("status") == "success":
            return JsonResponse({"status": "success", "message": "Call accepted successfully"})
        return JsonResponse(
            {"status": "error", "message": "Failed to accept call", "error": response_data},
            status=400,
        )
    except requests.exceptions.RequestException as e:
        logger.error("accept_call voxbay request failed: %s", e)
        return JsonResponse({"status": "error", "message": "Upstream telephony failure."}, status=502)

#---------------------------------------------------------------
from django.http import JsonResponse,HttpRequest
from django.views.decorators.csrf import csrf_exempt
import json

# Dummy round-robin pointer (replace with Redis in production)
round_robin_pointers = {}


def _landing_number_lookup_raw(telephony_id, landing_number):
    """Legacy raw-SQL path — byte-identical shape (list of dicts)."""
    query = (
        "SELECT group_id, routing_logic FROM landing_numbers "
        "WHERE telephony_id=%s AND landing_number=%s"
    )
    return run_query(query, [telephony_id, landing_number])


def _landing_number_lookup_orm(telephony_id, landing_number):
    """ORM path against the Phase 3.B LandingNumber model.

    Returns the same shape as the raw path so the caller can keep
    indexing ``result[0]['group_id']`` / ``['routing_logic']``.
    """
    from api.tenant_models import LandingNumber
    row = (
        LandingNumber.objects
        .filter(telephony_id=telephony_id, landing_number=landing_number)
        .values("group_id", "routing_logic")
        .first()
    )
    return [row] if row else []


@csrf_exempt
def telephony_route(request, telephony_id):
    from api.permissions._orm_dispatch import dispatch as _dispatch_path

    if not _verify_voxbay_signature(request):
        return JsonResponse({"error": "Invalid signature"}, status=401)
    logger.info("telephony_route HIT")

    try:
        data = json.loads(request.body)
        print("Payload:", data)

        landing_number = data.get("calledNumber")
        if not landing_number:
            return JsonResponse({'error': 'calledNumber missing'}, status=400)

        # Step 1: Get group info — Phase 3.C wave 2 dual-path (USE_ORM_FOR_BL).
        result = _dispatch_path(
            "telephony.landing_number_lookup",
            raw_impl=lambda: _landing_number_lookup_raw(telephony_id, landing_number),
            orm_impl=lambda: _landing_number_lookup_orm(telephony_id, landing_number),
            flag="USE_ORM_FOR_BL",
        )
        if not result:
            return JsonResponse({'error': 'Landing number not configured'}, status=404)

        group_id = result[0]['group_id']
        routing_logic = result[0]['routing_logic']

        # Step 2: Fetch users in group
        user_query = """SELECT u.id, u.phone FROM users u
                        JOIN user_group_users g ON u.id = g.user_id
                        WHERE g.user_group_id = %s ORDER BY u.id"""
        users = run_query(user_query, [group_id])
        if not users:
            return JsonResponse({'error': 'No users in group'}, status=404)

        # Step 3: Routing logic
        selected_user = None
        if routing_logic == 'round_robin':
            pointer = round_robin_pointers.get(group_id, 0)
            selected_user = users[pointer % len(users)]
            round_robin_pointers[group_id] = (pointer + 1) % len(users)
        else:
            selected_user = users[0]

        return JsonResponse({
            'action': 'connect',
            'number': selected_user['phone']
        })

    except Exception as e:
        print("🔥 Error in telephony_route:", e)
        return JsonResponse({'error': str(e)}, status=500)



def exists_schema(schema_name)->bool:
    try:
        query = """SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name = %s"""
        schema_data = run_query(query,[schema_name])
        if schema_data:
            return True
        return False
    except Exception as er:
        print(er)
        return False

def get_user_by_ext(ext,schema)->dict:
    from psycopg2 import sql
    from api.ORM.sqlFunctions.utils.helpers import validate_identifier
    try:
        validate_identifier(schema, "schema")
        users = sql.SQL(
            "SELECT user_id FROM {}.telephony_user "
            "WHERE (details->>'ext_no')::int=%s"
        ).format(sql.Identifier(schema))
        data = run_query(users,[ext])
        if data:
            user_id = data[0].get("user_id")
            users = """SELECT organization_id,profile_id FROM public.users WHERE id=%s"""
            data = run_query(users,[user_id])
            if data:
                organization_id = data[0].get("organization_id")
                query = """SELECT database_schema FROM public.organizations WHERE id=%s"""
                organizationname = run_query(query,[organization_id])
                if organizationname:
                    return {
                            "schema":organizationname[0].get("database_schema",""),
                            "status":"ok",
                            "error":False,
                            "user_id":user_id,
                            "org_id":organization_id,
                            "ext":ext,
                            "profile_id":data[0].get("profile_id")
                    }
                else:
                    raise Exception("Organization not found")
            else:
                raise Exception("User ID not found")
        else:
            raise Exception("Extension user not found")
    except Exception as er:
        return {"error":True,"data":"","message":str(er)}


def get_object(profile_id,schema,objects=False):
    from psycopg2 import sql
    from api.ORM.sqlFunctions.utils.helpers import validate_identifier
    returndata = {}
    try:
        validate_identifier(schema, "schema")
        schema_id = sql.Identifier(schema)
        query = sql.SQL(
            "SELECT telephony_id FROM {}.landing_numbers WHERE profile_id=%s"
        ).format(schema_id)
        data = run_query(query,[profile_id])
        if data and len(data) == 1:
            telephone = data[0].get("telephony_id")
            telephony_query = sql.SQL(
                "SELECT target_object, disposition_values "
                "FROM {}.telephony_config WHERE id=%s"
            ).format(schema_id)
            config = run_query(telephony_query,[telephone])
            if config and len(config) == 1:
                target_object = config[0].get("target_object")
                if objects:
                    objectQuery = sql.SQL(
                        "SELECT * FROM {}.object WHERE id=%s"
                    ).format(schema_id)
                    objDetails = run_query(objectQuery,[target_object])
                    returndata["objectdetails"] = objDetails
                returndata["error"] = False
                returndata["profile_id"]= profile_id
                returndata["target_object"]=target_object
                returndata["disposition_values"] = config[0].get("disposition_values")
                return returndata
        raise Exception("Excepted one object but got more than one or None!")
    except Exception as er:
        returndata["error"] = True
        returndata["message"] = str(er)
        return returndata
    

def get_object_data(object_name,schema,dataid):
    return



from django.utils.dateparse import parse_datetime
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

@csrf_exempt
def telephony_connecting(request):
    if not _verify_voxbay_signature(request):
        return JsonResponse({"error": "Invalid signature"}, status=401)
    logger.info("telephony_connecting HIT")
    try:
        data = json.loads(request.body)
        print("Payload:", data)
        org = request.headers.get("SCHEMA")
        is_schema = exists_schema(org)
        ext_no = data.get("agent_ext")
        if is_schema:
            user = get_user_by_ext(ext_no,org)
            if not user["error"]:
                user_id = user["user_id"]
                async_to_sync(get_channel_layer().group_send)(
                     f"telephony_group_{user_id}",
                    {
                        "type": "call_accepted",
                        "data": {
                            "telephony_id": "Soming"
                            }
                    }
                )

        # from_number = data.get("callerNumber")
        # call_id = data.get("CallUUID")
        # to_number = data.get("AgentNumber")
        # start_time = parse_datetime(data.get("callStartTime")) if data.get("callStartTime") else None

        # if not from_number or not call_id:
        #     return JsonResponse({'error': 'callerNumber or CallUUID missing'}, status=400)

        # config = run_query("""SELECT target_object, target_field, display_fields, disposition_values 
        #                       FROM telephony_config WHERE id = %s""", [telephony_id])[0]

        # target_object = config['target_object']
        # target_field = config['target_field']
        # display_fields_raw = config.get('display_fields', [])
        # disposition_values_raw = config.get('disposition_values', [])

        # # If it's a comma-separated string, split it
        # if isinstance(display_fields_raw, str):
        #     display_fields = [f.strip() for f in display_fields_raw.split(',')]
        # else:
        #     display_fields = display_fields_raw

        # if isinstance(disposition_values_raw, str):
        #     disposition_values = [d.strip() for d in disposition_values_raw.split(',')]
        # else:
        #     disposition_values = disposition_values_raw

        # match_query = f"""SELECT id, {','.join(display_fields)} 
        #                   FROM {target_object} WHERE {target_field} = %s LIMIT 1"""
        # matched = run_query(match_query, [from_number])

        # if matched:
        #     matched_record = matched[0]
        # else:
        #     import uuid
        #     new_id = str(uuid.uuid4())
        #     insert = f"""INSERT INTO {target_object} (id, {target_field}) VALUES (%s, %s) RETURNING id"""
        #     run_query(insert, [new_id, from_number])
        #     matched_record = {'id': new_id, **{f: None for f in display_fields}}

        # # Insert call log
        # run_query("""INSERT INTO call 
        #              (telephony_id, from_number, to_number, start_time, call_type, call_id, matched_record_id, matched_object)
        #              VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
        #           [telephony_id, from_number, to_number, start_time, 'incoming', call_id, matched_record['id'], target_object])

        # # Emit popup via WebSocket
        


        return JsonResponse({"status": "popup triggered"})

    except Exception as e:
        print("🔥 Error in telephony_connecting:", e)
        return JsonResponse({'error': str(e)}, status=500)



from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse
import json
@csrf_exempt
def telephony_hangup(request:HttpRequest):
    if not _verify_voxbay_signature(request):
        return JsonResponse({"error": "Invalid signature"}, status=401)
    try:
        data = json.loads(request.body)
        agent_ext = data.get("agent_ext")
        org = request.headers["SCHEMA"]
        is_exists = exists_schema(org)
        if is_exists:
            user = get_user_by_ext(agent_ext,org)
            if not user["error"]:
                user_id = user["user_id"]
                async_to_sync(get_channel_layer().group_send)(
                    f"telephony_group_{user_id}",
                    {
                        "type": "hang_up",
                        "data": {
                            "telephony_id": "",
                        }
                    }
                )
        return JsonResponse({"status": "call log updated"})

    except Exception as e:
        print("🔥 Error in telephony_hangup:", e)
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
def telephony_cdr(request:HttpRequest):
    if not _verify_voxbay_signature(request):
        return JsonResponse({"error": "Invalid signature"}, status=401)
    try:
        data = json.loads(request.body)
        logger.info("CDR received")

        call_id = data.get("CallUUID")
        if not call_id:
            return JsonResponse({"error": "Missing CallUUID"}, status=400)
        end_time = parse_datetime(data.get("callEndTime"))
        duration = data.get("conversationDuration") or data.get("Total Call Duration") or 0
        recording_url = data.get("recording_URL") or data.get("Call Recording URL") or ""
        call_status = data.get("callStatus") or data.get("Call Status") or ""
        disposition = data.get("disposition") or data.get("param1") or ""
        description = data.get("description", "")
        call_log_id = data.get("telephony")
        callStartTime = data.get("callStartTime")
        source_number = data.get("source_number")
        destination_number = data.get("destination_number")
        ext_no = data.get("extension_number")
        org = request.headers.get("SCHEMA")
        is_schema = exists_schema(org)
        if is_schema:
            get_user = get_user_by_ext(ext_no,org)
            if call_log_id:
                from psycopg2 import sql as _sql
                from api.ORM.sqlFunctions.utils.helpers import (
                    validate_identifier as _vi,
                )
                _vi(org, "schema")
                exists = run_query(
                    _sql.SQL("SELECT id FROM {}.call WHERE id=%s").format(
                        _sql.Identifier(org)
                    ),
                    [call_log_id],
                )
                if not exists:
                    pass
                update_query = _sql.SQL(
                    "UPDATE {}.call SET "
                    "start_time = %s, end_time = %s, duration = %s, "
                    "recording_link = %s, call_status = %s WHERE id = %s"
                ).format(_sql.Identifier(org))
                run_query(update_query, [
                    callStartTime,
                    end_time, 
                    duration,
                    recording_url, 
                    call_status,
                    call_log_id
                ])
            else:
                # Fallback insert
                obj=get_object(get_user["profile_id"],get_user['schema'])
                if obj['error']:
                    raise Exception(obj["message"])
                object_id=obj["target_object"]
                from psycopg2 import sql as _sql
                from api.ORM.sqlFunctions.utils.helpers import (
                    validate_identifier as _vi,
                )
                _vi(org, "schema")
                query = _sql.SQL(
                    "UPDATE {}.call SET "
                    "landing_number = %s, customer_number = %s, "
                    "recording_link = %s, start_time = %s, end_time = %s, "
                    "call_status = %s, object_id = %s, duration = %s "
                    "WHERE calluuid = %s"
                ).format(_sql.Identifier(org))
            run_query(
                query,
                [
                    destination_number,
                    source_number,
                    recording_url,
                    callStartTime,
                    end_time,
                    call_status,
                    object_id,
                    duration,
                    call_id,  
                ],
            )
            return JsonResponse({"status": "call log updated from CDR"})
        else:
            async_to_sync(get_channel_layer().group_send)(
            "telephony_popup_group",
            {
                "type": "error_responses",
                "data": {
                    "message":"Schema not found"
                }
            }
        )
    except Exception as e:
        print("What is the exception",e)
        async_to_sync(get_channel_layer().group_send)(
            "telephony_popup_group",
            {
                "type": "error_responses",
                "data": {
                    "message":str(e)
                }
            }
        )
    


@csrf_exempt
def make_call(request:HttpRequest):
    if request.method == "POST":
        data = json.loads(request.body)
        ext = data.get("agent_ext","")
        org = request.headers.get("SCHEMA")
        is_org = exists_schema(org)
        if is_org:
            try:
                user = get_user_by_ext(ext,org) 
                if not user["error"]:
                    user_id = user["user_id"]
                    async_to_sync(get_channel_layer().group_send)(
                        f"telephony_group_{user_id}",
                        {
                            "type": "show_popup",
                            "data": {
                                "telephony_id": "Soming",
                                "sourceNumber":data["sourcenumber"],
                                "logId":data["telephony"],
                                "action":"accept"
                            }
                        }
                    )
            except Exception as er:
                print(er)
    return JsonResponse({"s_id":"cal.sid"})

@csrf_exempt
def incoming_call(request):
    if not _verify_voxbay_signature(request):
        return JsonResponse({"error": "Invalid signature"}, status=401)
    logger.info("incoming_call HIT")
    if request.method == "POST":
        data = json.loads(request.body)
        ext = data.get("agent_ext","")
        org = request.headers.get("SCHEMA")
        destination_number = data.get("destination")
        source_number = data.get("sourceNumber")
        callStartTime = data.get("callStartTime")
        calluuid = data.get("calluuid")
        is_org = exists_schema(org)
        if is_org:
            try:
                user = get_user_by_ext(ext,org) 
                if not user["error"]:
                    user_id = user["user_id"]
                    obj = get_object(user['profile_id'],user['schema'],objects=True)
                    object_id=obj["target_object"]
                    from psycopg2 import sql
                    from api.ORM.sqlFunctions.utils.helpers import validate_identifier
                    validate_identifier(org, "schema")
                    query = sql.SQL(
                        "UPDATE {}.call "
                        "SET object_id = %s, agent_id = %s "
                        "WHERE calluuid = %s "
                        "RETURNING id"
                    ).format(sql.Identifier(org))
                    logid = run_query(
                        query,
                        [object_id,user_id, calluuid]
                    )
                    print(f"telephony_group_{user_id}")
                    async_to_sync(get_channel_layer().group_send)(
                        f"telephony_group_{user_id}",
                        {
                            "type": "incoming",
                            "data": {
                                "sourcenumber":source_number,
                                "action":"incoming",
                                "logid":logid[0].get("id"),
                                "dispostionvalues":obj['disposition_values'],
                                "object":object_id,
                                "connected":"accepted"
                            }
                        }
                    )

                else:
                    from psycopg2 import sql as _sql
                    from api.ORM.sqlFunctions.utils.helpers import (
                        validate_identifier as _vi,
                    )
                    _vi(org, "schema")
                    query = _sql.SQL(
                        "INSERT INTO {}.call("
                        "call_type, landing_number, customer_number, "
                        "start_time, calluuid) "
                        "VALUES('Inbound', %s, %s, %s, %s) RETURNING id"
                    ).format(_sql.Identifier(org))
                    logid =  run_query(query,[destination_number,source_number,callStartTime,calluuid])
                    
            except Exception as er:
                print(er)
    return JsonResponse({"s_id":"cal.sid"})


def connect_agent(request):
    response = VoiceResponse()
    response.say("Connecting to your voice agent, please wait.")
    agent_dial = os.getenv("VOXBAY_AGENT_DIAL_NUMBER")
    if not agent_dial:
        logger.error("connect_agent: VOXBAY_AGENT_DIAL_NUMBER unset")
        return HttpResponse(status=503)
    response.dial(agent_dial)
    return HttpResponse()

@csrf_exempt
def get_Call_status(request):
    data = json.loads(request.body)
    sid = data.get("sid")
    client =  Client(settings.TWILIO_ACCOUNT_SID,settings.TWILIO_AUTH_TOKEN)
    calldata = client.calls(sid).fetch()
    print(dir(calldata))
    print(calldata.status)
    return JsonResponse(data={})
    
def generate_twilo_token(request):
    capability = ClientCapabilityToken(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    capability.allow_client_incoming("agent")
    token = capability.to_jwt()
    return JsonResponse({"token": token})

import json

from cryptography.fernet import Fernet
key = Fernet.generate_key()

@csrf_exempt
def execute_test_api(request):
    # query = """
    #     select 
    #     *  

    #     from 
    #     organization_balajitraders.telephony_config
    #     where id=%s
    #     """
    # params = ['GEN_50af460a7']
    # data = run_query(query,params)[0]
    # target_field = data.get("target_field")
    # target_field = json.loads(target_field)
    # target_field = json.loads(target_field)
    # select_fields = []
    # joins = []
    # previous_table = target_field[0]['column'].replace('_id', '')
    # dataneed = previous_table 
    # print(target_field)
    try:
        # for item in target_field:
        #     if item['datatype'] == 'lookup_relationship' and item['column'].endswith('_id'):
        #         table_name = item['column'].replace('_id', '') 
        #         select_fields.append(f"{table_name}.name AS {table_name}_name")
        #         joins.append(f"LEFT JOIN organization_balajitraders.{table_name} AS {table_name} ON {previous_table}.{item['column']} = {table_name}.id")
        #         previous_table = table_name
        #     elif item["datatype"] == "phone":
        #         column = item['column']
        #         select_fields.clear()
        #         select_fields.append(f"{previous_table}.{column}")
        # query = f"""
        # SELECT
        #     {',\n    '.join(select_fields)}
        # FROM
        #    organization_balajitraders.{dataneed}
        #     {'\n    '.join(joins)};
        # """
        # print(query)
        # response = run_query(query)
        # print(response)
        fernet = Fernet(key)
        value  = "GEN_50af460a7".encode()
        encrypted = fernet.encrypt(value).decode()
        print(encrypted)
        return JsonResponse(data={"res":""},status=200)
    except Exception as er:
        print(er)
    return JsonResponse(data={},status=200)


def on_connected(request:HttpRequest):
    data = json.loads(request.body)
    agent_ext = data.get("agent_ext")
    org = request.headers["SCHEMA"]   
    is_org = exists_schema(org)
    if is_org: 
        user = get_user_by_ext(agent_ext,org)
        if not user['error']:
            user_id = user["user_id"]
            async_to_sync(get_channel_layer().group_send)(
                f"telephony_group_{user_id}",
                    {
                    "type": "call_accepted",
                    "data": {
                        "telephony_id": "Soming"
                            }
                }
            )
    return




def user_can_make_call(request:HttpRequest):
    from psycopg2 import sql as _sql
    from api.ORM.sqlFunctions.utils.helpers import (
        validate_identifier as _vi,
    )
    user_id = request.POST.get("id")
    profile = request.POST.get("profile_id")
    schema = request.POST.get("schema","pubic")
    telephony_grp = request.POST.get("telephony_grp")

    _vi(schema, "schema")
    schema_id = _sql.Identifier(schema)
    telephone_group = _sql.SQL(
        "SELECT * FROM {}.user_group WHERE id=%s"
    ).format(schema_id)
    profile_query = _sql.SQL(
        "SELECT * FROM {}.user_group_profiles WHERE profile_id = %s"
    ).format(schema_id)
    user_query = _sql.SQL(
        "SELECT * FROM {}.user_group_users WHERE user_group_id = %s"
    ).format(schema_id)
    telegrp = run_query(telephone_group,[telephony_grp],fetch_one=True)
    if not telegrp:
        return False
    
    profile_row = run_query(profile_query,[telegrp['id']])

    user_row = run_query(user_query,[telegrp[0]])

    if profile_row:
        user_group = """SELECT * FROM user_group WHERE id=%s"""
    if user_row:
        profile_grp = """SELECT * FROM """
    return