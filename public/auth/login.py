import uuid
from django.contrib.auth import authenticate
from django.http import JsonResponse
from django.views import View
import requests
from rest_framework.status import HTTP_200_OK, HTTP_401_UNAUTHORIZED
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django_ratelimit.decorators import ratelimit
import json
from django.utils.timezone import now
from django.db import connection
from api.ORM.AuditLogs.audit_trail_logs import log_audit_sql
from utils.custom_refresh_token import CustomRefreshToken
from .session import get_client_ip
from user_agents import parse
from django.contrib.auth.hashers import check_password
from api.notifications.notify import trigger_notication
from channels.layers import get_channel_layer
from datetime import datetime
from ..utils.exists import error_record
# Phase C9 — MFA login challenge (two-step "Pattern A" login). These
# helpers stay dormant until a user enrolls in MFA: for a user who
# never enrolled, user_has_mfa_enabled() returns False and the login
# below is byte-for-byte unchanged.
from api.security.mfa_login import (
    issue_mfa_ticket,
    user_has_mfa_enabled,
    verify_login_mfa,
    verify_mfa_ticket,
)
import logging

logger = logging.getLogger(__name__)

class CustomUser:
    def __init__(self, id, username, email, profile_id, company_name, organization_id):
        self.id = id
        self.username = username
        self.email = email
        self.profile_id = profile_id
        self.company_name = company_name
        self.organization_id = organization_id


def _build_login_response(request, user_tuple, data):
    """Issue the JWT and build the authenticated login response.

    Shared by the normal login path (LoginView, for a user without
    MFA) and the MFA second step (CompleteMfaLoginView). ``user_tuple``
    is a row from the users-join-organizations SELECT used by both
    views — the column order unpacked below must match that query.
    """
    (user_id, username, email, hashed_password, profile_id, company_name,
     organization_id, name, is_staff, is_superuser, timezone, is_active,
     locale, schema, org_name, domain) = user_tuple

    try:
        custom_user = CustomUser(
            id=user_id,
            username=username,
            email=email,
            profile_id=profile_id,
            company_name=company_name,
            organization_id=organization_id,
        )
        # Generate tokens using the CustomRefreshToken class
        refresh = CustomRefreshToken.for_user(custom_user)
        access_token = refresh.access_token
    except Exception as e:
        logger.error(f"Error generating tokens: {str(e)}")
        return JsonResponse({'error': 'Token generation failed'}, status=HTTP_401_UNAUTHORIZED)

    cursor = connection.cursor()
    cursor.execute(f"SELECT EXISTS(SELECT 1 FROM {schema}.profile WHERE id = %s AND profile_type in ('admin', 'superadmin', 'manager'))", [profile_id])
    setup = cursor.fetchone()[0]

    ip = get_client_ip(request)
    location = get_location_from_ip(ip)
    user_agent = request.META.get('HTTP_USER_AGENT')
    platform, browser = get_platform_and_browser(user_agent)
    login_url = request.build_absolute_uri()

    response = JsonResponse({
        'access': str(access_token),
        'refresh': str(refresh),
        'user': {
            'id': user_id,
            'username': username,
            'email': email,
            'profile_id': profile_id,
            'company': domain,
            'name': name,
            'timezone': timezone,
            'locale': locale,
            'setup': setup,
            'domain': domain
        }
    }, status=HTTP_200_OK)

    # Set the cookie to work across subdomains
    response.set_cookie(
        key="authToken",
        value=str(access_token),
        domain=f"{domain}.bussus.com",  # Works for all subdomains
        secure=True,
        httponly=True,
        samesite="None",  # Required for cross-site cookies
        max_age=86400  # 1 day expiration
    )

    # Phase C2 — session/login logging.
    #
    # Routing through the log_user_login_async Celery task (a
    # TenantRequiredTask that uses the ORM) keeps tenant isolation
    # intact: the ORM path encrypts the access / refresh tokens, sets
    # organization_id from the injected TenantContext (required by
    # FORCE ROW LEVEL SECURITY), and runs inside a with_tenant_schema()
    # block. Best-effort — a logging failure must never fail the login.
    try:
        from adminuser.tasks import log_user_login_async
        from api.celery_tasks.base import serialize_ctx
        from api.security.schema_authority import TenantContext

        _tenant_ctx = TenantContext(
            org_id=str(organization_id),
            schema=schema,
            profile_id=str(profile_id) if profile_id else None,
        )
        log_user_login_async.apply_async(kwargs={
            "_tenant_ctx": serialize_ctx(_tenant_ctx),
            "user_id": user_id,
            "profile_id": profile_id,
            "company_name": company_name,
            "ip": ip,
            "location": location,
            "browser": browser,
            "platform": platform,
            "client_version": data.get("client_version"),
            "api_type": data.get("api_type"),
            "api_version": data.get("api_version", "1.0"),
            "login_url": login_url,
            "access_token": str(access_token),
            "refresh_token": str(refresh),
        })
    except Exception as e:
        # Logging is best-effort — never fail the login over it.
        logger.error(f"Failed to queue login logging task: {str(e)}")

    # Trigger notification for the org admin.
    if not is_staff and not is_superuser:
        notify_kwargs = {
            "message": f"{username} is logged in at {datetime.now().strftime('%H:%M %p')}"
        }
        org_admin = get_admin_user(organization_id)
        trigger_notication(
            owner_id=org_admin,
            channel_layer=get_channel_layer(),
            title="Login alert",
            notification_type='alert',
            user_id=user_id,
            channel='push',
            request=request,
            **notify_kwargs,
        )

    return response


@method_decorator(csrf_exempt, name='dispatch')
# Phase 8.A7 — rate limit fixes:
#   * block=True so the decorator returns 429 itself (the previous
#     form without block=True silently set request.limited and the
#     view never checked, making the decorator a no-op).
#   * Stacked ip + post:username keys. IP-only is bypassed by
#     residential-proxy rotation; per-username catches credential
#     stuffing against a single account from rotating sources.
#   * 5/m → 20/h per IP feels generous, but combined with the
#     per-username 5/h limit + progressive lockout it bounds the
#     attacker.
@method_decorator(
    ratelimit(key='ip', rate='20/h', method='POST', block=True),
    name='dispatch',
)
@method_decorator(
    ratelimit(key='post:username', rate='5/h', method='POST', block=True),
    name='dispatch',
)
class LoginView(View):
    def post(self, request, *args, **kwargs):
        try:
            # Parse the request body
            request.referer = "login"
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')

            # Validate required fields
            if not username or not password:
                return JsonResponse({'error': 'Username and password are required.'}, status=400)

            # Phase 8.A7 — progressive lockout. Even if the per-IP +
            # per-username rate limits are bypassed, an account that
            # has hit the failed-attempt threshold within the rolling
            # window is locked for AUTH_LOCKOUT_MINUTES. Message is
            # intentionally vague (no enumeration leak).
            from public.auth.lockout import is_locked_out, lockout_response_payload
            if is_locked_out(username):
                return JsonResponse(
                    lockout_response_payload(username),
                    status=429,
                )

            cursor = connection.cursor()
            cursor.execute("SELECT u.id, u.username, u.email, u.password, u.profile_id, u.company, u.organization_id, u.name, u.is_staff, u.is_superuser, u.timezone, u.is_active, u.locale, o.database_schema, o.name,o.domain FROM users u JOIN organizations o ON u.organization_id = o.id WHERE u.username = %s", [username])
            user = cursor.fetchone()
            if user:
                user_id, username, email, hashed_password, profile_id, company_name, organization_id, name, is_staff, is_superuser, timezone, is_active, locale, schema, org_name, domain = user
                if not is_active:
                    return JsonResponse({'error': 'Account is inactive'}, status=HTTP_401_UNAUTHORIZED)
                # Step 2: Verify the password
                if check_password(password, hashed_password):
                    # Phase C9 — MFA login challenge (Pattern A). The
                    # password is correct; if this user enrolled in MFA
                    # we do NOT issue the JWT yet. Instead we return a
                    # short-lived signed mfa_ticket and the client
                    # finishes login at POST /v2/login/mfa with the
                    # ticket + a 6-digit code. For a user who never
                    # enrolled, user_has_mfa_enabled() is False and the
                    # login proceeds exactly as before.
                    if user_has_mfa_enabled(user_id):
                        return JsonResponse({
                            'mfa_required': True,
                            'mfa_ticket': issue_mfa_ticket(user_id),
                        }, status=HTTP_200_OK)
                    return _build_login_response(request, user, data)
                else:
                    return JsonResponse({'error': 'Invalid password for the email'}, status=HTTP_401_UNAUTHORIZED)
            else:
                return JsonResponse({'error': 'Username does not exist.'}, status=HTTP_401_UNAUTHORIZED)
        except json.JSONDecodeError as e:
            error_record(er=e)
            return JsonResponse({'error': 'Invalid JSON format'}, status=400)
        except Exception as er:
            error_record(er=er)
            return JsonResponse({'error': 'An error occurred processing your request.'}, status=500)


@method_decorator(csrf_exempt, name='dispatch')
# Phase C9 — the MFA second step uses the same per-IP rate limit as
# LoginView (20/h, block=True). The 6-digit code is the only
# brute-force surface here; 20/h per IP combined with the 5-minute
# mfa_ticket lifetime makes guessing a code infeasible.
@method_decorator(
    ratelimit(key='ip', rate='20/h', method='POST', block=True),
    name='dispatch',
)
class CompleteMfaLoginView(View):
    """Phase C9 — step 2 of the two-step MFA login ("Pattern A").

    POST /v2/login/mfa  {"mfa_ticket": "...", "code": "123456"}

    Step 1 (LoginView) verified the password and returned a
    short-lived signed mfa_ticket. This view verifies that ticket
    plus a 6-digit TOTP code (or a one-time recovery code) and only
    then issues the JWT. The ticket alone is NOT a session — without
    a valid code this endpoint issues nothing.
    """

    def post(self, request, *args, **kwargs):
        try:
            request.referer = "login"
            data = json.loads(request.body)
            ticket = data.get('mfa_ticket')
            code = data.get('code')

            if not ticket or not code:
                return JsonResponse({'error': 'mfa_ticket and code are required.'}, status=400)

            # The ticket proves the password check passed < 5 min ago.
            user_id = verify_mfa_ticket(ticket)
            if not user_id:
                return JsonResponse(
                    {'error': 'MFA session expired. Please log in again.'},
                    status=HTTP_401_UNAUTHORIZED,
                )

            # Verify the TOTP code, or consume a one-time recovery code.
            if not verify_login_mfa(user_id, code):
                return JsonResponse({'error': 'Invalid MFA code.'}, status=HTTP_401_UNAUTHORIZED)

            # Re-load the user — the account may have been changed or
            # deactivated in the window between step 1 and step 2.
            cursor = connection.cursor()
            cursor.execute("SELECT u.id, u.username, u.email, u.password, u.profile_id, u.company, u.organization_id, u.name, u.is_staff, u.is_superuser, u.timezone, u.is_active, u.locale, o.database_schema, o.name,o.domain FROM users u JOIN organizations o ON u.organization_id = o.id WHERE u.id = %s", [user_id])
            user = cursor.fetchone()
            if not user:
                return JsonResponse({'error': 'Account not found.'}, status=HTTP_401_UNAUTHORIZED)
            if not user[11]:  # is_active
                return JsonResponse({'error': 'Account is inactive'}, status=HTTP_401_UNAUTHORIZED)

            return _build_login_response(request, user, data)
        except json.JSONDecodeError as e:
            error_record(er=e)
            return JsonResponse({'error': 'Invalid JSON format'}, status=400)
        except Exception as er:
            error_record(er=er)
            return JsonResponse({'error': 'An error occurred processing your request.'}, status=500)


def get_platform_and_browser(user_agent):
    if user_agent:
        ua = parse(user_agent)
        platform = ua.os.family
        browser = ua.browser.family
        return platform, browser
    return 'Unknown', 'Unknown'

def get_location_from_ip(ip_address):
    try:
        response = requests.get(f'https://ipinfo.io/{ip_address}/json')
        data = response.json()
        return data.get('city', 'Unknown')
    except Exception:
        return 'Unknown'

# Phase C2 — `log_user_login` (raw-SQL threading helper) was removed.
# It wrote session_log / user_login_history rows via direct INSERT,
# which (a) bypassed EncryptedCharField and stored access/refresh
# tokens in plaintext, (b) omitted organization_id on session_log,
# and (c) ran with no tenant context. Login logging now goes through
# adminuser.tasks.log_user_login_async (a TenantRequiredTask using
# the ORM) — see the apply_async call in _build_login_response above.


def get_admin_user(org_id):
    try:
        cursor = connection.cursor()
        cursor.execute("""
                SELECT id
                FROM users
                WHERE organization_id = %s AND is_staff=true
            """, [org_id])
        user_details = cursor.fetchone()
        if user_details:
            adminid = user_details[0]
            return adminid
        raise Exception("Admin not found")
    except Exception as er:
        logger.error(f"Error getting admin user: {str(er)}")
        return None
