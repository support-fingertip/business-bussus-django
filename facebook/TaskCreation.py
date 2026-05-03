import hashlib
import hmac
import logging
import os
from typing import Any, Dict, Optional

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


def _appsecret_proof(token: str, app_secret: str) -> str:
    return hmac.new(app_secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def register_facebook_webhook(page_id: str, webhook_url: str, page_access_token: str) -> Dict[str, Any]:
    if not page_id or not webhook_url or not page_access_token:
        raise ValueError("page_id, webhook_url, and page_access_token are required")
    creds = _get_fb_creds()
    url = f"{GRAPH_API_URL}/{GRAPH_VERSION}/{page_id}/subscribed_apps"
    data = {
        "object": "page",
        "subscribed_fields": "leadgen",
        "callback_url": webhook_url,
        "verify_token": os.getenv("FB_VERIFY_TOKEN") or "verify",
        "access_token": page_access_token,
        "appsecret_proof": _appsecret_proof(page_access_token, creds["app_secret"]),
    }
    try:
        resp = requests.post(url, data=data, timeout=REQUEST_TIMEOUT)
        payload = resp.json()
    except requests.RequestException as e:
        logger.exception("Network error registering webhook")
        raise RuntimeError(f"Failed to register webhook: {e}") from e
    except ValueError:
        logger.exception("Invalid JSON from webhook registration")
        raise RuntimeError("Webhook registration response was not valid JSON")

    if resp.status_code != 200:
        msg = payload.get("error", {}).get("message") or "Webhook registration failed"
        logger.warning("Webhook registration error: status=%s message=%s", resp.status_code, msg)
        raise RuntimeError(msg)

    logger.info("Webhook registered successfully for page %s", page_id)
    return payload