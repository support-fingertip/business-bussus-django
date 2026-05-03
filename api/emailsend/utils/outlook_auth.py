# from msal import ConfidentialClientApplication
# import os

# CLIENT_ID = os.getenv("OUTLOOK_CLIENT_ID")
# CLIENT_SECRET = os.getenv("OUTLOOK_CLIENT_SECRET")
# TENANT_ID = os.getenv("OUTLOOK_TENANT_ID")

# AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
# SCOPES = ["https://graph.microsoft.com/.default"]

# def get_access_token():
#     app = ConfidentialClientApplication(
#         client_id=CLIENT_ID,
#         client_credential=CLIENT_SECRET,
#         authority=AUTHORITY
#     )
#     result = app.acquire_token_for_client(scopes=SCOPES)
#     if "access_token" in result:
#         return result['access_token']
#     else:
#         raise Exception(f"Failed to get access token: {result.get('error_description')}")


#outlook_auth.py
import os
import json
import requests
import webbrowser

from dotenv import load_dotenv

from api.emailsend.utils.outlook_service import refresh_outlook_token

load_dotenv()

# Load these securely from your environment variables or .env file
# CLIENT_ID = '012a13a8-cc01-4bcf-892a-9beb92b216eb'
# CLIENT_SECRET = '0922640d-35c9-471c-809a-d4e1777b00a4'
# TENANT_ID = 'd8b80013-e71c-4652-9be5-bed934953898'
# REDIRECT_URI = "http://localhost:8000/msauth/"
# SCOPES = "https://graph.microsoft.com/.default offline_access openid email"
# TOKEN_FILE = "api/emailsend/outlook_token.json"

CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TENANT_ID = os.getenv("TENANT_ID")
REDIRECT_URI = "http://localhost:8000/msauth/"
SCOPES = "https://graph.microsoft.com/.default"
TOKEN_FILE = "api/emailsend/outlook_token.json"

def authenticate():
    # ✅ Step 1: Try to load existing token
    # if os.path.exists(TOKEN_FILE):
    #     with open(TOKEN_FILE, "r") as f:
    #         token_data = json.load(f)
    #         if "access_token" in token_data:
    #             return token_data

    # 🌐 Step 2: Build authorization URL
    auth_url = (
        f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/authorize"
        f"?client_id={CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_mode=query"
        f"&scope={SCOPES}"
    )

    # 👀 Ask user to authorize
    print("🌐 Open the following URL in your browser and log in to authorize:")
    print(auth_url)
    webbrowser.open(auth_url)

    # 🧠 Ask for the returned authorization code
    code = input("\n🔐 Paste the authorization code from the URL here: ").strip()

    # 🔁 Step 3: Exchange code for token
    token_url = f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token"
    data = {
        "client_id": CLIENT_ID,
        "scope": SCOPES,
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "client_secret": CLIENT_SECRET,
    }

    response = requests.post(token_url, data=data)
    if response.status_code != 200:
        raise Exception(f"❌ Token request failed: {response.text}")

    token_data = response.json()

    # 💾 Save token for future use
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f)

    print("✅ Access token saved successfully!")
    return token_data


if __name__ == "__main__":
    print("🔄 Starting Outlook auth flow...")  # Add this line
    try:
        authenticate()
    except Exception as e:
        print("❌ Error:", e)







#---------------------------Per User Outlook Auth--------------------------------





import os
import time
from datetime import timedelta
from django.utils.timezone import now
import requests
from api.telephony.views import run_query


def get_valid_user_outlook_token(user_id):
    row = run_query("SELECT * FROM user_outlook_tokens WHERE user_id = %s", [user_id])
    if not row:
        raise Exception("Outlook account not connected.")

    token_data = row[0]
    expiry = token_data["expiry_time"].timestamp()
    if time.time() > expiry - 60:
        # refresh
        refreshed = refresh_outlook_token(token_data["refresh_token"])
        # Update DB
        run_query("""
            UPDATE user_outlook_tokens
            SET access_token = %s,
                expires_in = %s,
                expiry_time = %s,
                updated_at = NOW()
            WHERE user_id = %s
        """, [
            refreshed["access_token"],
            refreshed["expires_in"],
            now() + timedelta(seconds=refreshed["expires_in"]),
            user_id
        ])
        return refreshed["access_token"]

    return token_data["access_token"]







