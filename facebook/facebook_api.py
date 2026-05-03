import hashlib
import hmac
import logging
import os
from typing import Any, Dict, Optional

import requests

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com"
GRAPH_VERSION = "v20.0"
REQUEST_TIMEOUT = 8  # seconds


def _get_fb_creds() -> Dict[str, str]:
    app_id = os.getenv("FB_APP_ID")
    app_secret = os.getenv("FB_APP_SECRET")
    if not app_id or not app_secret:
        logger.error("Facebook credentials are not configured (FB_APP_ID/FB_APP_SECRET)")
        raise RuntimeError("Facebook credentials are not configured")
    return {"app_id": app_id, "app_secret": app_secret}


def _appsecret_proof(token: str, app_secret: str) -> str:
    return hmac.new(app_secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def _graph_get(
    endpoint: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    access_token: Optional[str] = None,
    app_secret: Optional[str] = None,
    version: str = GRAPH_VERSION,
) -> Dict[str, Any]:
    url = f"{GRAPH_BASE}/{version}/{endpoint.lstrip('/')}"
    query = dict(params or {})
    if access_token:
        query["access_token"] = access_token
        if app_secret:
            query["appsecret_proof"] = _appsecret_proof(access_token, app_secret)

    try:
        resp = requests.get(url, params=query, timeout=REQUEST_TIMEOUT)
        data = resp.json()
    except requests.RequestException as e:
        logger.exception("Network error calling Facebook Graph API")
        raise RuntimeError(f"Facebook API request failed: {e}") from e
    except ValueError:
        logger.exception("Invalid JSON from Facebook Graph API")
        raise RuntimeError("Facebook API response was not valid JSON")

    if resp.status_code != 200:
        fb_error = data.get("error", {})
        message = fb_error.get("message") or "Facebook API call failed"
        code = fb_error.get("code")
        subcode = fb_error.get("error_subcode")
        logger.warning(
            "Facebook API error: status=%s code=%s subcode=%s message=%s",
            resp.status_code,
            code,
            subcode,
            message,
        )
        raise RuntimeError(message)

    return data


def get_facebook_user_data(access_token: str) -> Dict[str, Any]:
    creds = _get_fb_creds()
    return _graph_get(
        "me",
        params={"fields": "id,name,email,picture"},
        access_token=access_token,
        app_secret=creds["app_secret"],
    )


def get_facebook_pages(access_token: str) -> Dict[str, Any]:
    creds = _get_fb_creds()
    return _graph_get(
        "me/accounts",
        params={"fields": "id,name"},
        access_token=access_token,
        app_secret=creds["app_secret"],
    )


def get_facebook_lead_forms(page_id: str, access_token: str) -> Dict[str, Any]:
    creds = _get_fb_creds()
    return _graph_get(
        f"{page_id}/leadgen_forms",
        params={"fields": "id,name"},
        access_token=access_token,
        app_secret=creds["app_secret"],
    )