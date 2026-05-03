# import requests
# from .outlook_auth import get_access_token

# def send_email_using_outlook(sender_email, to_email, subject, html_content):
#     access_token = get_access_token()

#     url = f"https://graph.microsoft.com/v1.0/users/{sender_email}/sendMail"
#     headers = {
#         "Authorization": f"Bearer {access_token}",
#         "Content-Type": "application/json"
#     }

#     email_msg = {
#         "message": {
#             "subject": subject,
#             "body": {
#                 "contentType": "HTML",
#                 "content": html_content
#             },
#             "toRecipients": [
#                 {"emailAddress": {"address": to_email}}
#             ]
#         },
#         "saveToSentItems": "true"
#     }

#     response = requests.post(url, headers=headers, json=email_msg)
#     return response.status_code, response.text



import os
import json
import re
import requests
from django.utils.timezone import now
from typing import Dict, Any, Optional, Literal
from api.BL.utils import JWTHandler
from .gmail_auth import get_user_gmail_credentials

OUTLOOK_TOKEN_PATH = "api/emailsend/outlook_token.json"
from urllib.parse import urlencode
import time
from api.security.schema_authority import get_validated_schema
 

CLIENT_ID = os.getenv("OUTLOOK_CLIENT_ID")
CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET")
TENANT_ID = os.getenv("OUTLOOK_TENANT_ID")
REDIRECT_URI = "http://localhost:8080/v2/api/outlook/oauth/callback/"
# SCOPES = "https://graph.microsoft.com/.default"
TOKEN_FILE = "api/emailsend/outlook_token.json"

AUTHORITY = "https://login.microsoftonline.com/common"
AUTHORIZE_URL = f"{AUTHORITY}/oauth2/v2.0/authorize"
TOKEN_URL = f"{AUTHORITY}/oauth2/v2.0/token"

SCOPES = [
    "offline_access",
    "openid",
    "email",
    "https://graph.microsoft.com/Mail.Send",
]
SCOPES_STR = " ".join(SCOPES)

# def refresh_outlook_token(token_data):
#     token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
#     # token_url = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
#     data = {
#         "client_id": CLIENT_ID,
#         "scope": SCOPES,
#         "refresh_token": token_data.get("refresh_token"),
#         "grant_type": "refresh_token",
#         "client_secret": CLIENT_SECRET,
#     }
#     response = requests.post(token_url, data=data)
#     if response.status_code != 200:
#         print(response.text)
#         raise Exception(f"Failed to refresh token: {response.text}")
    

    
#     print(response.text)
#     new_token_data = response.json()
#     # Optional: Track token expiry time
#     new_token_data['expires_at'] = int(time.time()) + new_token_data['expires_in']
#     with open(OUTLOOK_TOKEN_PATH, "w") as f:
#         json.dump(new_token_data, f)
#     return new_token_data

def refresh_outlook_token(token_data: dict) -> dict:
    try:
        if "refresh_token" not in token_data:
            raise Exception("No refresh_token available for Outlook.")
        data = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "grant_type": "refresh_token",
            "refresh_token": token_data["refresh_token"],
            "scope": SCOPES_STR,
        }
        resp = requests.post(TOKEN_URL, data=data)
        if resp.status_code != 200:
            try:
                err_body = resp.json()
            except Exception:
                err_body = {"raw": resp.text}
            print("Outlook refresh error:", err_body)

            # If invalid_grant, this connection is dead. Force user to reconnect.
            if err_body.get("error") == "invalid_grant":
                # TODO: delete token from DB for this user
                raise Exception("Outlook token invalid/expired. User must reconnect.")

            raise Exception(f"Failed to refresh token: {err_body}")

        new_token_data = resp.json()
        new_token_data["expires_at"] = int(time.time()) + new_token_data["expires_in"]
        return new_token_data
    except Exception as er:
        return None

def get_valid_outlook_token(token_data):
    expires_at = token_data.get("expires_at", 0)
    if time.time() > expires_at - 60:  # Refresh 1 min before expiry
        print("🔄 Refreshing expired Outlook token...")
        token_data = refresh_outlook_token(token_data)
    return token_data


def is_html_template(template):
    return bool(re.search(r'</?(html|head|body|p|div|span|br|h\d|strong|em|table|tr|td|a)[^>]*>', template, re.IGNORECASE))

def create_outlook_message(to_email, subject, body, cc: Optional[str] = None):
    """Build payload for Outlook sendMail; supports optional CC."""
    to_list = [addr.strip() for addr in to_email.split(',') if addr.strip()]
    cc_list = []
    if cc:
        cc_list = [addr.strip() for addr in cc.split(',') if addr.strip()]
    payload = {
        "message": {
            "subject": subject,
            "body": {
                "contentType": "HTML" if is_html_template(body) else "Text",
                "content": body
            },
            "toRecipients": [{"emailAddress": {"address": addr}} for addr in to_list]
        }
    }
    if cc_list:
        payload["message"]["ccRecipients"] = [{"emailAddress": {"address": addr}} for addr in cc_list]
    return payload


def send_email_using_outlook_api(to_email, subject, body, user_id, cc: Optional[str] = None, **kwargs):
    try:
        schema = (get_validated_schema(kwargs) or 'public')
        credentials,_ = get_user_gmail_credentials(user_id=user_id,provider="outlook",schema=schema)
        if not credentials:
            jwthandler = JWTHandler()
            data = {"user_id": user_id,"provider": "gmail","schema": (get_validated_schema(kwargs) or 'public'), "exp": now().timestamp() + 300}
            token = jwthandler.encrypt(data,expires_in_hours=0.0833)
            authurl = get_outlook_auth_url(token)
            return {"authurl" : authurl,"verify":True}
        credentials = json.loads(credentials)
        token_data = get_valid_outlook_token(credentials)
        access_token = token_data.get("access_token")
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        message_payload = create_outlook_message(to_email, subject, body, cc=cc)
        response = requests.post("https://graph.microsoft.com/v1.0/me/sendMail", headers=headers, json=message_payload)
        if response.status_code != 202:
            raise Exception(response.text)
        return "Email sent successfully."
    except Exception as er:
        print(er)
        raise er

def get_outlook_auth_url(state: str) -> str:
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "response_mode": "query",
        "scope": SCOPES_STR,
        "state": state,  # CSRF protection, store+verify
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


# from api.emailsend.utils.outlook_auth import get_valid_user_outlook_token

# def send_email_using_outlook_api(user_id, to_email, subject, body):
#     access_token = get_valid_user_outlook_token(user_id)
#     print("🔐 Access token type:", type(access_token))
#     headers = {
#         "Authorization": f"Bearer {access_token}",
#         "Content-Type": "application/json"
#     }
#     message_payload = create_outlook_message(to_email, subject, body)
#     response = requests.post("https://graph.microsoft.com/v1.0/me/sendMail", headers=headers, json=message_payload)
    
#     if response.status_code != 202:
#         raise Exception(response.text)
    
#     return "Email sent successfully."