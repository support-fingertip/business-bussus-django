import hashlib
import hmac
import logging
import os
from typing import Any, Dict, Optional

import requests
from django.conf import settings
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com"
DEFAULT_GRAPH_VERSION = "v20.0"
REQUEST_TIMEOUT = 8  # seconds


def _get_fb_creds() -> Dict[str, str]:
    app_id = os.getenv("FB_APP_ID") or getattr(settings, "FB_APP_ID", None)
    app_secret = os.getenv("FB_APP_SECRET") or getattr(settings, "FB_APP_SECRET", None)
    if not app_id or not app_secret:
        logger.error("Facebook credentials are not configured")
        raise RuntimeError("Facebook credentials are not configured")
    return {"app_id": app_id, "app_secret": app_secret}


def _appsecret_proof(token: str, app_secret: str) -> str:
    return hmac.new(app_secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def _validate_endpoint(endpoint: str) -> str:
    # Guard against path traversal or protocol injection in dynamic endpoints
    if ".." in endpoint or "//" in endpoint or endpoint.startswith(":" ):
        raise ValueError("Invalid Facebook endpoint")
    return endpoint


def _validate_token_with_app(token: str, creds: Dict[str, str]) -> Dict[str, Any]:
    """Call debug_token to verify token validity and app ownership."""
    debug = _graph_get(
        "debug_token",
        params={"input_token": token, "access_token": f"{creds['app_id']}|{creds['app_secret']}"},
        version="v20.0",
    )
    data = debug.get("data", {})
    if not data.get("is_valid"):
        raise RuntimeError("Invalid Facebook access token")
    if data.get("app_id") and data["app_id"] != creds["app_id"]:
        raise RuntimeError("Access token does not belong to this app")
    return data


def _graph_get(
    endpoint: str,
    params: Dict[str, Any],
    access_token: Optional[str] = None,
    app_secret: Optional[str] = None,
    version: str = DEFAULT_GRAPH_VERSION,
) -> Dict[str, Any]:
    endpoint = _validate_endpoint(endpoint)
    url = f"{GRAPH_BASE}/{version}/{endpoint.lstrip('/')}"
    query = dict(params)
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
        logger.exception("Failed to parse Facebook Graph API response as JSON")
        raise RuntimeError("Facebook API response was not valid JSON")

    if resp.status_code != 200:
        fb_error = data.get("error", {})
        message = fb_error.get("message") or "Facebook API call failed"
        code = fb_error.get("code")
        subcode = fb_error.get("error_subcode")
        logger.warning("Facebook API error: status=%s code=%s subcode=%s message=%s", resp.status_code, code, subcode, message)
        raise RuntimeError(message)

    return data


@api_view(["POST"])
def facebook_login(request):
    token = request.data.get("access_token")
    if not token:
        return Response({"error": "No access token provided"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        creds = _get_fb_creds()
        app_token = f"{creds['app_id']}|{creds['app_secret']}"

        # 1) Verify the access token
        _validate_token_with_app(token, creds)

        # 2) Get user info
        user_info = _graph_get(
            "me",
            params={"fields": "id,name,email,picture"},
            access_token=token,
            app_secret=creds["app_secret"],
            version=DEFAULT_GRAPH_VERSION,
        )

        # 3) Get user's Facebook pages
        pages = _graph_get(
            "me/accounts",
            params={},
            access_token=token,
            app_secret=creds["app_secret"],
            version=DEFAULT_GRAPH_VERSION,
        )
        return Response({"user": user_info, "pages": pages.get("data", [])}, status=status.HTTP_200_OK)

    except RuntimeError as e:
        return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception:
        logger.exception("Unexpected error during facebook_login")
        return Response({"error": "An unexpected error occurred"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FetchLeadForms(APIView):
    def post(self, request, *args, **kwargs):
        page_id = request.data.get("page_id")
        page_access_token = request.data.get("access_token")

        if not page_id or not page_access_token:
            return Response({"error": "Page ID and Access Token are required."}, status=status.HTTP_400_BAD_REQUEST)

        # Basic page_id validation to avoid malformed endpoints
        if not str(page_id).isdigit():
            return Response({"error": "Invalid page ID."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            creds = _get_fb_creds()
            # Validate the provided access token belongs to this app
            _validate_token_with_app(page_access_token, creds)
            data = _graph_get(
                f"{page_id}/leadgen_forms",
                params={},
                access_token=page_access_token,
                app_secret=creds["app_secret"],
                version=DEFAULT_GRAPH_VERSION,
            )
            return Response(data, status=status.HTTP_200_OK)
        except RuntimeError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Unexpected error during FetchLeadForms")
            return Response({"error": "An unexpected error occurred"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GetPageAccessToken(APIView):
    def post(self, request, *args, **kwargs):
        user_access_token = request.data.get("user_access_token")

        if not user_access_token:
            return Response({"error": "User Access Token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            creds = _get_fb_creds()
            _validate_token_with_app(user_access_token, creds)
            data = _graph_get(
                "me/accounts",
                params={},
                access_token=user_access_token,
                app_secret=creds["app_secret"],
                version=DEFAULT_GRAPH_VERSION,
            )
            return Response(data, status=status.HTTP_200_OK)
        except RuntimeError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Unexpected error during GetPageAccessToken")
            return Response({"error": "An unexpected error occurred"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)