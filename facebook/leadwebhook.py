import hashlib
import hmac
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import requests
from django.conf import settings
from django.db import connection, transaction
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from psycopg2 import sql

from facebook.pageAccessToken import get_long_lived_page_token

logger = logging.getLogger(__name__)

GRAPH_API_URL = "https://graph.facebook.com"
GRAPH_VERSION = "v20.0"
REQUEST_TIMEOUT = 8  # seconds
VERIFY_TOKEN = os.getenv("FB_VERIFY_TOKEN") or getattr(settings, "FB_VERIFY_TOKEN", "verify")
SAFE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _get_fb_creds() -> Dict[str, str]:
    app_id = os.getenv("FB_APP_ID") or getattr(settings, "FB_APP_ID", None)
    app_secret = os.getenv("FB_APP_SECRET") or getattr(settings, "FB_APP_SECRET", None)
    if not app_id or not app_secret:
        logger.error("Facebook credentials are not configured")
        raise RuntimeError("Facebook credentials are not configured")
    return {"app_id": app_id, "app_secret": app_secret}


def _appsecret_proof(token: str, app_secret: str) -> str:
    return hmac.new(app_secret.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).hexdigest()


def _assert_safe_identifier(value: str, label: str) -> str:
    """Ensure identifier parts are alphanumeric/underscore to block SQL injection."""
    if not value or not SAFE_IDENT.match(value):
        raise RuntimeError(f"Invalid {label} provided")
    return value


def _graph_get(
    endpoint: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    access_token: Optional[str] = None,
    app_secret: Optional[str] = None,
) -> Dict[str, Any]:
    url = f"{GRAPH_API_URL}/{GRAPH_VERSION}/{endpoint.lstrip('/')}"
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


def fetch_lead_details(leadgen_id: str, page_access_token: str) -> Dict[str, Any]:
    creds = _get_fb_creds()
    return _graph_get(
        leadgen_id,
        params={},
        access_token=page_access_token,
        app_secret=creds["app_secret"],
    )


def map_field_data(data: Dict[str, Any], mapping: Dict[str, str]) -> Dict[str, Any]:
    mapped_values: Dict[str, Any] = {}
    field_data: List[Dict[str, Any]] = data.get("field_data", [])
    for key, mapped_key in mapping.items():
        for field in field_data:
            if field.get("name") == key:
                vals = field.get("values") or []
                if vals:
                    mapped_values[mapped_key] = vals[0]
    return mapped_values


@method_decorator(csrf_exempt, name="dispatch")
class FacebookWebhookView(APIView):
    # Phase 2.A4 — explicit authentication_classes=[] + AllowAny so this
    # view doesn't depend on global DRF defaults. Facebook calls this
    # without a JWT (Facebook IS the caller, not a logged-in user).
    # SECURITY: the X-Hub-Signature-256 HMAC verification is what
    # authenticates an inbound webhook. Confirm verify_signature is
    # called in the post() handler BEFORE any DB write.
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if mode == "subscribe" and token == VERIFY_TOKEN:
            return HttpResponse(challenge, status=200)
        return HttpResponse("Unauthorized", status=403)

    def post(self, request, *args, **kwargs):
        payload = request.data
        try:
            if not payload or "entry" not in payload:
                return Response({"error": "Invalid payload"}, status=status.HTTP_400_BAD_REQUEST)
            with transaction.atomic():
                with connection.cursor() as cursor:
                    for entry in payload.get("entry", []):
                        page_id = entry.get("id")
                        for change in entry.get("changes", []):
                            if change.get("field") != "leadgen":
                                continue
                            value = change.get("value", {}) or {}
                            lead_id = value.get("leadgen_id")
                            form_id = value.get("form_id")
                            if not lead_id or not form_id:
                                logger.warning("Missing leadgen_id or form_id in change payload")
                                continue
                            # Insert raw lead event (idempotent on lead_id)
                            cursor.execute(
                                """
                                INSERT INTO facebook_lead (lead_id, page_id, form_id, raw_data, created_time)
                                VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                                ON CONFLICT (lead_id) DO NOTHING
                                """,
                                [lead_id, page_id, form_id, json.dumps(value)],
                            )
                            # Fetch lead capture configuration
                            cursor.execute(
                                """
                                SELECT page_access_token, field_mapping, created_by_id
                                FROM lead_capture
                                WHERE lead_form_id = %s
                                LIMIT 1
                                """,
                                [form_id],
                            )
                            row = cursor.fetchone()
                            if not row:
                                raise RuntimeError(f"Lead Capture Task not found for form_id: {form_id}")

                            page_access_token, field_mapping_raw, created_by = row
                            try:
                                field_mapping = json.loads(field_mapping_raw) if field_mapping_raw else {}
                            except json.JSONDecodeError:
                                raise RuntimeError("Invalid field_mapping JSON")

                            # Fetch lead details from Facebook
                            lead_data = fetch_lead_details(lead_id, page_access_token)

                            # Map fields
                            mapped_lead_data = map_field_data(lead_data, field_mapping)
                            # Normalize expected fields
                            if "phone" in mapped_lead_data and isinstance(mapped_lead_data["phone"], str):
                                mapped_lead_data["phone"] = mapped_lead_data["phone"][:16]
                            mapped_lead_data["lead_source"] = "Facebook"

                            # Prepare insert into tenant schema
                            columns = list(mapped_lead_data.keys())
                            values = [mapped_lead_data[col] for col in columns]
                            values.extend([created_by, created_by, created_by])
                            cursor.execute(
                                """
                                SELECT o.database_schema
                                FROM organizations o
                                JOIN users u ON o.id = u.organization_id
                                WHERE u.id = %s
                                """,
                                [created_by],
                            )
                            org_row = cursor.fetchone()
                            if not org_row:
                                raise RuntimeError("Organization schema not found for user")
                            schema = _assert_safe_identifier(org_row[0], "schema")

                            # Validate column identifiers to prevent SQL injection via field mapping
                            safe_columns: List[str] = []
                            safe_values: List[Any] = []
                            for col in columns:
                                safe_columns.append(_assert_safe_identifier(col, "column name"))
                                safe_values.append(mapped_lead_data[col])

                            # Audit/user columns and values
                            safe_columns.extend([
                                "created_by_id",
                                "last_modified_by_id",
                                "owner_id",
                                "created_date",
                                "last_modified_date",
                            ])
                            safe_values.extend([created_by, created_by, created_by])
                            column_identifiers = [sql.Identifier(col) for col in safe_columns]
                            value_parts = [sql.Placeholder()] * len(safe_values)
                            value_parts.extend([sql.SQL("CURRENT_TIMESTAMP"), sql.SQL("CURRENT_TIMESTAMP")])
                            insert_sql = sql.SQL("""
                                INSERT INTO {}.{} ({})
                                VALUES ({})
                            """).format(
                                sql.Identifier(schema),
                                sql.Identifier("leads"),
                                sql.SQL(", ").join(column_identifiers),
                                sql.SQL(", ").join(value_parts),
                            )
                            cursor.execute(insert_sql, safe_values)
            return Response({"status": "received"}, status=status.HTTP_200_OK)
        except RuntimeError as e:
            logger.warning("Webhook handling error: %s", e)
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Unexpected error handling webhook")
            return Response({"error": "An unexpected error occurred"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)