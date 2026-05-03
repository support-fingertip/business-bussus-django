import hashlib
import hmac
import logging
import os
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

GRAPH_API_URL = "https://graph.facebook.com"
GRAPH_VERSION = "v20.0"
REQUEST_TIMEOUT = 8  # seconds


def _get_fb_creds() -> Dict[str, str]:
    app_id = os.getenv("FB_APP_ID")
    app_secret = os.getenv("FB_APP_SECRET")
    if not app_id or not app_secret:
        logger.error("Facebook credentials are not configured (FB_APP_ID/FB_APP_SECRET)")
        raise RuntimeError("Facebook credentials are not configured")
    return {"app_id": app_id, "app_secret": app_secret}


def get_long_lived_page_token(page_access_token: str) -> Optional[str]:
    creds = _get_fb_creds()
    url = (
        f"{GRAPH_API_URL}/{GRAPH_VERSION}/oauth/access_token"
        f"?grant_type=fb_exchange_token"
        f"&client_id={creds['app_id']}"
        f"&client_secret={creds['app_secret']}"
        f"&fb_exchange_token={page_access_token}"
    )

    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT)
        data = resp.json()
    except requests.RequestException as e:
        logger.exception("Network error exchanging page token")
        raise RuntimeError(f"Facebook token exchange failed: {e}") from e
    except ValueError:
        logger.exception("Invalid JSON exchanging page token")
        raise RuntimeError("Facebook token exchange response was not valid JSON")

    if resp.status_code != 200:
        msg = data.get("error", {}).get("message") or "Token exchange failed"
        logger.warning("Token exchange error: status=%s message=%s", resp.status_code, msg)
        raise RuntimeError(msg)

    token = data.get("access_token")
    if not token:
        raise RuntimeError("Access token not found in token exchange response")
    return token