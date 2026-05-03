
import requests
from rest_framework.views import APIView
from rest_framework.response import Response
from api.emailsend.utils.find_provider import check_domain_authenticated, get_email_provider_from_mx
from api.telephony.views import run_query
from .utils.gmail_service import send_email_using_gmail_api,save_token
from .utils.outlook_service import TENANT_ID, send_email_using_outlook_api
from .utils.mergefields import get_record_from_sql, replace_merge_fields,get_object_details
from .utils.sendgrid_service import send_bulk_email_using_sendgrid, send_email_using_sendgrid
from django.utils import timezone

class SendTestEmailAPIView(APIView):
    def post(self, request):
        data = request.data
        object_name = data.get('selected_object')
        record_id = data.get('record_id')
        template_body = data.get('template_body')
        template_subject = data.get('template_subject', 'Test Email')
        provider = data.get('provider', 'gmail').lower()
        record_data = get_record_from_sql(object_name.lower(), record_id)
        recipient_email = record_data.get('email')
        merged_template = replace_merge_fields(template_body, object_name, record_data)
        if provider == 'gmail':
            message_id = send_email_using_gmail_api(recipient_email, template_subject, merged_template)
            return Response({"message": f"Gmail sent", "message_id": message_id})
        elif provider == 'outlook':
            send_email_using_outlook_api(recipient_email, template_subject, merged_template)
            return Response({"message": f"Outlook email sent"})
        else:
            return Response({"error": "Unknown provider"}, status=400)
        

import os
import requests
import re
import hashlib
from .utils.gmail_service import send_email_using_gmail_api
from .utils.outlook_service import send_email_using_outlook_api
from .utils.mergefields import get_record_from_sql, replace_merge_fields
import datetime

def send_test_email(request, data, **kwargs):
    try:
        from api.permissions.permissions import post_permission
        subject_template = data.get("template_subject", "")
        body_template = data.get("template_body", "")
        object_name = (data.get("selected_object") or "").strip()
        record_ids = list(dict.fromkeys(data.get("record_ids", [])))
        cc_raw = data.get("cc", [])
        cc = [str(e).strip() for e in cc_raw if e]
        schema = get_validated_schema(kwargs)
        user_ctx = kwargs.get("user_", {}) or {}
        sender_email = user_ctx.get("email")
        user_id = user_ctx.get("id")
        if not sender_email or not user_id:
            return Response({"error": "Sender email not found"}, status=400)
        provider = get_sender_provider(user_id)
        object_key = object_name.lower()
        responses = []
        timestamp = timezone.now()
        safe_kwargs = {k: v for k, v in kwargs.items() if k != "create_data"}

        if provider in ["gmail", "outlook", "outlook.com", "gmail.com", "google.com"]:
            object_details = get_object_details(object_key, schema)
            for record_id in record_ids:
                record_data = get_record_from_sql(object_key, record_id, schema)
                recipient_email = next(
                    (v.get("value") for v in record_data.values() if isinstance(v, dict) and v.get("datatype") == "email" and v.get("value")),
                    None,
                )
                if not recipient_email:
                    raise Exception("Please provide recepient email")

                subject = replace_merge_fields(subject_template, object_name, record_data)
                body = replace_merge_fields(body_template, object_name, record_data)

                if provider in ['gmail', 'gmail.com', 'google.com']:
                    msg_id = send_email_using_gmail_api(recipient_email, subject, body, user_id, cc=cc, **kwargs)
                    if isinstance(msg_id, dict) and "authurl" in msg_id:
                        return msg_id
                else:
                    data = send_email_using_outlook_api(recipient_email, subject, body, user_id, cc=cc, **kwargs)
                    if isinstance(data, dict) and "authurl" in data:
                        return data
                responses.append({
                    "from_email": sender_email,
                    "to_email": recipient_email,
                    "matched_record_id": record_id,
                    "object_id": object_details.get("id"),
                    "created_by_id": user_id,
                    "owner_id": user_id,
                    "sent_time": timestamp,
                    "body": body,
                    "subject": subject,
                    "cc_email": ", ".join(cc),
                })

        elif provider in ["sendgrid", "webmail"]:
            if not check_domain_authenticated(request):
                return {"error": "You need to authenticate your domain first. Ask your administrator."}

            object_details = get_object_details(object_key, schema)
            personalizations = []

            for record_id in record_ids:
                record_data = get_record_from_sql(object_key, record_id, schema)
                email = record_data.get("email", {}).get("value")

                dynamic_data = {}
                import decimal
                import datetime
                for k, v in record_data.items():
                    if isinstance(v, (datetime.datetime, datetime.date)):
                        dynamic_data[k] = v.isoformat()
                    elif isinstance(v, decimal.Decimal):
                        dynamic_data[k] = float(v)
                    else:
                        dynamic_data[k] = v
                personalizations.append({
                    "to": [{"email": email}],
                    "dynamic_template_data": dynamic_data,
                })

            handlebars_subject = convert_merge_fields_to_handlebars(subject_template, object_name)
            handlebars_body = convert_merge_fields_to_handlebars(body_template, object_name)
            template_id = create_sendgrid_dynamic_template(handlebars_subject, handlebars_body)
            status = send_bulk_email_using_sendgrid(personalizations, sender_email, template_id)

            for record_id, p in zip(record_ids, personalizations):
                email = p["to"][0]["email"]
                responses.append({
                    "to_email": email,
                    "object": object_name,
                    "matched_record_id": record_id,
                    "object_id": object_details.get("id"),
                    "body": handlebars_body,
                    "subject": handlebars_subject,
                    "cc_email": ", ".join(cc),
                    "sendgrid_status": status,
                })
        for payload in responses:
           dalevta = post_permission(request, 'email', create_data=payload, **safe_kwargs)

        # Store campaign record after successful email send
        campaign_name = data.get("campaign_name")
        campaign_type = data.get("campaign_type", "Email")
        campaign_status = data.get("campaign_status", "Completed")
        template_id = data.get("template_id")
        campaign_members = data.get("campaign_members", [])
        if campaign_name:
            try:
                campaign_data = {
                    "name": campaign_name,
                    "type": campaign_type,
                    "status": campaign_status,
                    "module": object_name,
                    "template": template_id,
                    "send_time": timestamp.isoformat(),
                    "number_sent": len(responses),
                    "created_by_id": user_id,
                    "owner_id": user_id,
                    "child_tables": [
                        {
                            "table": "campaign_member",
                            "records": campaign_members,
                        }
                    ],
                }
                post_permission(request, 'campaign', create_data=campaign_data, **safe_kwargs)
            except Exception as e:
                print(f"Campaign creation failed: {e}")

        return responses
    except Exception as er:
        print(er)
        raise er

#-------------------------------sendgrid------------------------------------------------------

def convert_merge_fields_to_handlebars(template, object_name):
    pattern = r"{!\s*" + re.escape(object_name) + r"\.(\w+)(?:,\s*([^}]+))?\s*}"
    def replacer(match):
        field, default = match.groups()
        if default:
            return f'{{{{{field} | default("{default}")}}}}'
        return f'{{{{{field}}}}}'
    return re.sub(pattern, replacer, template)


#--------------------------------


def create_sendgrid_dynamic_template(subject, body):
    template_hash = generate_template_hash(subject, body)

    # ✅ Check if already uploaded
    existing_id = get_sendgrid_template_id_from_db(template_hash)
    if existing_id:
        return existing_id

    # ❌ Not found — create new
    api_key = os.getenv("SENDGRID_API_KEY")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    template_name = f"AppTemplate_{int(os.times()[4])}"
    response = requests.post(
        "https://api.sendgrid.com/v3/templates",
        headers=headers,
        json={"name": template_name, "generation": "dynamic"}
    )
    print(response)
    if response.status_code != 201:
        raise Exception(f"Failed to create template: {response.text}")

    template_id = response.json()["id"]

    version_data = {
        "template_id": template_id,
        "active": 1,
        "name": f"v1_{template_name}",
        "html_content": body,
        "subject": subject,
        "plain_content": body
    }

    version_response = requests.post(
        f"https://api.sendgrid.com/v3/templates/{template_id}/versions",
        headers=headers,
        json=version_data
    )
    if version_response.status_code != 201:
        raise Exception(f"Failed to create version: {version_response.text}")

    # ✅ Save for reuse
    save_sendgrid_template_id_to_db(template_hash, template_id)

    return template_id



def generate_template_hash(subject, body):
    raw = subject + body
    return hashlib.md5(raw.encode()).hexdigest()


def get_sendgrid_template_id_from_db(template_hash):
    query = "SELECT sendgrid_template_id FROM email_templates WHERE sendgrid_template_hash = %s"
    result = run_query(query, [template_hash])
    return result[0]['sendgrid_template_id'] if result else None

def save_sendgrid_template_id_to_db(template_hash, template_id):
    query = """
        UPDATE email_templates
        SET sendgrid_template_id = %s, sendgrid_template_hash = %s
        WHERE id = (
            SELECT id FROM email_templates
            WHERE sendgrid_template_hash IS NULL OR sendgrid_template_hash = %s
            ORDER BY id
            LIMIT 1
        )
    """
    run_query(query, [template_id, template_hash, template_hash])



def get_user_email_provider(user_id):

    query = """
        SELECT provider FROM email_provider_setup
        WHERE user_id = %s
        LIMIT 1
    """
    result = run_query(query, [user_id])
    if result:
        return result[0]["provider"]
    raise Exception("Email provider not configured for user.")



def get_sender_provider(user_id):
    query = """SELECT split_part(email, '@', 2) AS domain_name FROM users WHERE id=%s"""
    result = run_query(query,[user_id])
    if result:
        return get_email_provider_from_mx(result[0]['domain_name'])
    return Exception('User email domain not found')









#--------------------------GMAIL------------------------------------------------------
#--Per User Gmail OAuth Integration--

# api/emailsend/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from google_auth_oauthlib.flow import Flow
from django.utils.timezone import now, timedelta
from rest_framework.permissions import AllowAny 
import traceback
from django.template.loader import render_to_string
import json
from api.BL.utils import JWTHandler

class GmailOAuthCallbackView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    def get(self, request):
        code = request.GET.get("code")
        states = request.GET.get("state")        
        if not code or not states:
            return Response({"error": "Missing code or state (user_id)"}, status=400)
        try:
            if not code or not states:
                html = render_to_string("mail_linked_failed.html",{"domain": "Gmail"})
                return HttpResponse(html)            
            flow = Flow.from_client_secrets_file(
            "api/emailsend/credentials.json",
            scopes=["https://www.googleapis.com/auth/gmail.send"],
            redirect_uri=os.getenv("REDIRECT_URL")
            )
            flow.fetch_token(code=code)
            credentials = flow.credentials
            token_data = credentials.to_json()
            if "token" not in token_data:
                template = render_to_string("mail_linked_failed.html",{"domain": "Gmail"})
                return HttpResponse(template)
            try:
                jwt_handler = JWTHandler()
                user_id,schema = None,None
                data = jwt_handler.decrypt(states)
                if not data:
                    raise Exception("Invalid state token")
                user_id = data.get("user_id")
                schema = data.get("schema","public")
            except Exception as er:
                print("Error decoding JWT state token:", er)
                error_html = render_to_string("mail_linked_failed.html",{"domain": "Gmail"})
                return HttpResponse(error_html)  
            save_token(user_id, provider="gmail", creds=token_data,schema=schema)
            success_html = render_to_string("mail_linked.html",{"domain": "Gmail"})
            return HttpResponse(success_html)
        except Exception as er:
            print("Error in Gmail OAuth callback:", er)
            html = render_to_string("mail_linked_failed.html",{"domain": "Gmail"})
            return HttpResponse(html)


        

#-------------------------OUTLOOK------------------------------------------------------

#outlook per user auth

# api/emailsend/views.py
import urllib.parse
import os
from api.security.schema_authority import get_validated_schema


CLIENT_ID = os.getenv("OUTLOOK_CLIENT_ID")
CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET")
TENANT_ID = os.getenv("OUTLOOK_TENANT_ID")
REDIRECT_URI = "http://localhost:8000/msauth/"
# SCOPES = "https://graph.microsoft.com/.default"
TOKEN_FILE = "api/emailsend/outlook_token.json"
AUTHORITY = "https://login.microsoftonline.com/common"
AUTHORIZE_URL = f"{AUTHORITY}/oauth2/v2.0/authorize"
TOKEN_URL = f"{AUTHORITY}/oauth2/v2.0/token"


class OutlookAuthURLView(APIView):
    def get(self, request):
        user_id = request.user.id
        redirect_uri = "http://localhost:8000/v2/api/outlook/oauth/callback/"
        params = {
            "client_id": os.getenv("OUTLOOK_CLIENT_ID"),
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": "https://graph.microsoft.com/.default offline_access openid email",
            "state": str(user_id)
        }
        auth_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/authorize?{urllib.parse.urlencode(params)}"
        return Response({"auth_url": auth_url})


from django.http import HttpResponse

class OutlookOAuthCallbackView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    def get(self, request):
        code = request.GET.get("code")
        state = request.GET.get("state") 
        try:
            if not code or not state:
                html = render_to_string("mail_linked_failed.html",{"domain": "Outlook"})
                return HttpResponse(html)
            token_url = TOKEN_URL
            data = {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "redirect_uri": "http://localhost:8080/v2/api/outlook/oauth/callback/",
                "grant_type": "authorization_code",
                "scope": "https://graph.microsoft.com/.default offline_access openid email",
            }
            response = requests.post(token_url, data=data)
            token_data = response.json()
            access_token = token_data["access_token"]
            try:
                jwt_handler = JWTHandler()
                user_id = None
                data = jwt_handler.decrypt(state)
                if not data:
                    raise Exception("Invalid state token")
                user_id = data.get("user_id")
            except Exception as er:
                error_html = render_to_string("mail_linked_failed.html",{"domain": "Outlook"})
                return HttpResponse(error_html)
            if "access_token" not in token_data:
                error_html = render_to_string("mail_linked_failed.html",{"domain": "Outlook"})
                return HttpResponse(error_html)
            save_token(user_id,provider="outlook",creds=response.text,schema=data.get("schema","public"))
            success_html = render_to_string("mail_linked.html",{"domain": "Outlook"})
            return HttpResponse(success_html)
        except Exception as er:
            html =render_to_string("mail_linked_failed.html",{"domain": "Outlook"})
            return HttpResponse(html)