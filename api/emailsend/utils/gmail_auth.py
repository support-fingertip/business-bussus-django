import os
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow,Flow
from api.telephony.views import run_query
from typing import Literal
from api.BL.utils import JWTHandler
from api.security.token_encryption import (
    decrypt_token,
    encrypt_token,
    is_encrypted,
)

CREDENTIALS_PATH = "api/emailsend/credentials.json"
TOKEN_PATH = "api/emailsend/token.json"
SCOPES = [
    "https://www.googleapis.com/auth/gmail.send"
]

request:Request

def authenticate(user_id,**kwargs):
    creds = None
    schema = kwargs.get("schema","public")
    creds,userInfo = get_user_gmail_credentials(user_id=user_id,provider="gmail",schema=schema)
    # If credentials are not valid, re-authenticate
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            try:
                jwt_handler = JWTHandler()
                data = {"user_id": user_id,"provider": "gmail","schema": kwargs.get("schema","public"), "exp": now().timestamp() + 300}
                token = jwt_handler.encrypt(data,expires_in_hours=0.0833)
                redirect_uri = os.getenv("REDIRECT_URL","")
                print(f"Generated JWT for authentication flow: {token}")
                print(f"Using redirect URI: {redirect_uri}")
                flow = Flow.from_client_secrets_file(
                "api/emailsend/credentials.json",
                scopes=SCOPES,
                redirect_uri=redirect_uri
                    )
                auth_url, _ = flow.authorization_url(
                    access_type='offline',
                    include_granted_scopes='true',
                    prompt='consent',
                    state=str(token) 
                )
                return {"authurl":auth_url,"verify":True}
            except Exception as e:
                print("Error during authentication flow:", e)   
                raise
            # print(os.environ.get('DJANGO_ENV', 'production'))
            # if os.environ.get('DJANGO_ENV', 'production') == 'production':
            #     # In production, use the redirect URI-based authentication flow
            #     # print("🌐 Using production authentication flow...")
            #     # flow = InstalledAppFlow.from_client_secrets_file(
            #     #     CREDENTIALS_PATH, SCOPES)                
            #     # # Production should use your server's URL
            #       # Change this to your production URI
            #     # creds = flow.run_local_server(
            #     #     port=8080,  # Port should be available on the server
            #     #     authorization_prompt_message="",
            #     #     success_message="Authentication complete. You may close this window.",
            #     #     open_browser=True,  # This will still open a browser for manual consent
            #     #     redirect_uri=redirect_uri  # This is key for production
            #     # )
                
            # else:
            #     flow = InstalledAppFlow.from_client_secrets_file(
            #         CREDENTIALS_PATH, SCOPES)
            #     creds = flow.run_local_server(
            #         port=8080,
            #         authorization_prompt_message="",
            #         success_message="Authentication complete. You may close this window.",
            #         open_browser=True,
            #         access_type='offline',
            #         prompt='consent'
            #         )
            # save_token(user_id=user_id,provider="gmail",creds=creds.to_json())
            # print("✅ Authentication successful!")
    return creds

def save_token(user_id,provider:Literal["gmail","outlook","send_grid"],creds,schema=None):
    try:
        # Always store the cred blob encrypted at rest. `creds` is normally a
        # JSON string for OAuth providers; cast to str defensively in case a
        # caller passes a dict.
        if not isinstance(creds, str):
            creds = json.dumps(creds)
        encrypted_creds = encrypt_token(creds)
        query = "INSERT INTO email_provider_setup (user_id, provider, cred) VALUES (%s, %s, %s)"
        run_query(query, [user_id, provider, encrypted_creds], schema=schema)
    except Exception as er:
        # Never log the cred itself.
        raise Exception(f"Database error: {str(er)}")
    return

import requests


def save_user_email(email,user_id,schema=None):
    row = run_query("SELECT email FROM users WHERE id = %s", [user_id], schema=schema)
    existing_email = row[0]["email"]
    if existing_email != email:
        run_query(
            "UPDATE users SET email = %s WHERE id = %s",
            [email, user_id],
            schema=schema
        )
        print("Updated email found")
    return



# import os
# import json
# from django.db import connection
# from google.auth.transport.requests import Request
# from google.oauth2.credentials import Credentials
# from google_auth_oauthlib.flow import InstalledAppFlow

# CREDENTIALS_PATH = "api/emailsend/credentials.json"
# SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

# def authenticate(user_email):
#     creds = None
#     print(f"🔑 Starting Gmail authentication for {user_email}")

#     # STEP 1: Load token data from DB using raw SQL
#     with connection.cursor() as cursor:
#         cursor.execute("SELECT token_data FROM gmail_token WHERE user_email = %s", [user_email])
#         row = cursor.fetchone()

#     if row:
#         print("📦 Found token in database.")
#         token_data = row[0]
#         try:
#             creds = Credentials.from_authorized_user_info(token_data, SCOPES)
#         except Exception as e:
#             print("⚠️ Error loading credentials:", e)
#             creds = None
#     else:
#         print("⚠️ No token found for this user.")
#         creds = None

#     # STEP 2: Validate and refresh token if expired
#     if not creds or not creds.valid:
#         if creds and creds.expired and creds.refresh_token:
#             print("♻️ Token expired. Refreshing...")
#             try:
#                 creds.refresh(Request())
#                 print("✅ Token refreshed successfully.")
#                 _save_token(user_email, creds)
#             except Exception as e:
#                 print("❌ Failed to refresh token:", e)
#                 creds = None
#         else:
#             print("🌐 Re-authenticating user...")
#             flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)

#             redirect_uri = (
#                 "https://dev0.bussus.com/api/oauth2callback"
#                 if os.environ.get("DJANGO_ENV", "production") == "production"
#                 else "http://localhost:8080"
#             )

#             creds = flow.run_local_server(
#                 port=8080,
#                 authorization_prompt_message="",
#                 success_message="✅ Authentication complete. You may close this window.",
#                 open_browser=True,
#             )

#             _save_token(user_email, creds)


            # ON CONFLICT (user_email)
            # DO UPDATE SET token_data = EXCLUDED.token_data, updated_at = NOW();

#     return creds






 # Step 3: Get authorization code from user


#----New per user-------------------

#gmail_auth.py


from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from django.utils.timezone import now


def get_user_gmail_credentials(user_id, provider, schema):
    if provider != "gmail":
        row = run_query(
            "SELECT cred FROM email_provider_setup WHERE user_id = %s AND provider = %s",
            [user_id, provider],
            schema=schema,
        )
        if not row:
            return (None, None)
        # Decrypt transparently; legacy plaintext rows pass through unchanged.
        return (decrypt_token(row[0]["cred"]), None)

    try:
        rows = run_query(
            "SELECT cred FROM email_provider_setup WHERE user_id = %s AND provider = %s",
            [user_id, provider],
            schema=schema,
        )
        if not rows:
            return None, None

        stored_raw = decrypt_token(rows[0]["cred"])
        stored = json.loads(stored_raw)
        user_info = stored
        creds = Credentials(
            token=stored.get("token"),
            refresh_token=stored.get("refresh_token"),
            token_uri=stored.get("token_uri"),
            client_id=os.getenv("GOOGLE_CLIENT_ID"),
            client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
            scopes=stored.get("scopes"),
        )

        if not creds.valid:
            creds.refresh(Request())
            refreshed_payload = {
                "token": creds.token,
                "refresh_token": creds.refresh_token,
                "token_uri": creds.token_uri,
                "client_id": creds.client_id,
                "client_secret": creds.client_secret,
                "scopes": list(creds.scopes) if creds.scopes else [],
                "universe_domain": creds.universe_domain,
                "account": stored.get("account", ""),
                "expiry": creds.expiry,
            }
            # Persist only when values change to avoid extra writes.
            if (
                stored.get("token") != creds.token
                or stored.get("refresh_token") != creds.refresh_token
            ):
                run_query(
                    """
                        UPDATE email_provider_setup
                        SET cred = %s, updated_at = NOW()
                        WHERE user_id = %s AND provider = %s
                    """,
                    [
                        encrypt_token(json.dumps(refreshed_payload, default=str)),
                        user_id,
                        provider,
                    ],
                    schema=schema,
                )

        return creds, user_info
    except Exception as exc:
        # Surface errors to caller so they can decide how to handle.
        raise exc