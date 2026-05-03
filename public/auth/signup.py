import uuid

from django.contrib.auth.hashers import make_password
from django.core.exceptions import ValidationError
from django.db import connection, transaction, IntegrityError
from django_ratelimit.decorators import ratelimit
from psycopg2 import sql
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from public.utils.organisation import create_new_tenant
from public.utils.error_log import log_tenant_error
from utils.schema_validator import validate_schema_name

MAX_LEN_EMAIL = 254
MAX_LEN_NAME = 150
MAX_LEN_PHONE = 32


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _redact_payload(payload: dict) -> dict:
    redacted = dict(payload)
    if "password" in redacted:
        redacted["password"] = "***"
    return redacted


@api_view(["POST"])
@permission_classes([AllowAny])
@ratelimit(key="ip", rate="30/h", method="POST")  # adjust as needed
def signup_with_proof(request):
    if request.content_type != "application/json":
        return Response(
            {"ok": False, "error": "Content-Type must be application/json"},
            status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        )

    body = request.data if isinstance(request.data, dict) else {}
    # Server-generated IDs (never trust client IDs)
    user_id = body.get('user_id', f"uSr_{uuid.uuid4().hex[:12]}")
    organization_id = body.get("organization_id", f"org_{uuid.uuid4().hex[:12]}")

    email = _normalize_email(body.get("email"))
    password = body.get("password") or ""
    username = (body.get("username") or email).strip()
    phone = (body.get("phone") or "").strip()[:MAX_LEN_PHONE]
    first_name = (body.get("first_name") or "").strip()[:MAX_LEN_NAME]
    last_name = (body.get("last_name") or "").strip()[:MAX_LEN_NAME]
    organisation_name = (body.get("organization_name") or "").strip()[:MAX_LEN_NAME]
    schema_name = (body.get("schema_name") or "").strip()

    # Validate required fields
    if not email or "@" not in email or len(email) > MAX_LEN_EMAIL:
        return Response({"ok": False, "error": "Valid email is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not password or len(password) < 8:
        return Response({"ok": False, "error": "Password must be at least 8 characters."}, status=status.HTTP_400_BAD_REQUEST)
    if not organisation_name:
        return Response({"ok": False, "error": "Organization name is required."}, status=status.HTTP_400_BAD_REQUEST)
    if not schema_name:
        return Response({"ok": False, "error": "Schema name is required."}, status=status.HTTP_400_BAD_REQUEST)

    # Validate schema name
    try:
        validate_schema_name(schema_name)
    except ValidationError as e:
        return Response({"ok": False, "error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    pwd_hash = make_password(password, hasher="pbkdf2_sha256")
    safe_payload = _redact_payload(body)

    try:
        with transaction.atomic():
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.users (
                        id, email, password, name, phone, first_name, last_name,
                        username, company, is_active, created_date, is_staff, organization_id
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, NOW(), TRUE, %s)
                    RETURNING id
                    """,
                    [
                        user_id,
                        email,
                        pwd_hash,
                        f"{first_name} {last_name}".strip(),
                        phone,
                        first_name,
                        last_name,
                        username,
                        organisation_name,
                        organization_id,
                    ],
                )
        payload = {
            'id': user_id,
            **body
        }
        profile_id, organization_id_ = create_new_tenant(
            organisation_name,
            username,
            password,
            schema_name,
            payload,
            organization_id=organization_id
        )
        return Response({"ok": True}, status=status.HTTP_201_CREATED)
    except IntegrityError as e:
        print(e)
        # Map likely unique constraint names to friendly messages
        constraint = getattr(getattr(e, "diag", None), "constraint_name", "") or ""
        if "users_username_key" in constraint:
            msg = "Username already exists."
        elif "users_email_key" in constraint:
            msg = "Email already exists."
        elif "organizations_database_schema_key" in constraint:
            msg = "Schema name already in use."
        elif "organizations_name_key" in constraint:
            msg = "Organization name already in use."
        else:
            msg = "Duplicate value."
        log_tenant_error(
            user_id=user_id,
            email=email,
            organization_name=organisation_name,
            schema_name=schema_name,
            step="signup_with_proof",
            error=e,
            payload=safe_payload,
        )
        return Response({"ok": False, "error": msg}, status=status.HTTP_409_CONFLICT)

    except Exception as e:
        print(e)
        # Comprehensive logging without secrets
        log_tenant_error(
            user_id=user_id,
            email=email,
            organization_name=organisation_name,
            schema_name=schema_name,
            step="signup_with_proof",
            error=e,
            payload=safe_payload,
        )
        # Best-effort cleanup if a partial tenant/schema was created
        try:
            with connection.cursor() as cur:
                cur.execute("DELETE FROM users WHERE id = %s", [user_id])
                cur.execute("DELETE FROM organizations WHERE database_schema = %s", [schema_name])
                cur.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(schema_name)
                    )
                )
        except Exception:
            pass
        return Response({"ok": False, "error": "Signup failed"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)