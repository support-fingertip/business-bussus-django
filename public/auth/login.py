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
            
            channel = get_channel_layer()
            cursor = connection.cursor()
            cursor.execute("SELECT u.id, u.username, u.email, u.password, u.profile_id, u.company, u.organization_id, u.name, u.is_staff, u.is_superuser, u.timezone, u.is_active, u.locale, o.database_schema, o.name,o.domain FROM users u JOIN organizations o ON u.organization_id = o.id WHERE u.username = %s", [username])
            user = cursor.fetchone() 
            if user:
                user_id, username, email, hashed_password, profile_id, company_name, organization_id, name, is_staff, is_superuser, timezone, is_active, locale, schema, org_name, domain = user                
                if not is_active:
                    return JsonResponse({'error': 'Account is inactive'}, status=HTTP_401_UNAUTHORIZED)
                # Step 2: Verify the password
                if check_password(password, hashed_password):
                    try:                                 
                        custom_user = CustomUser(
                                            id=user_id,
                                            username=username,
                                            email=email,
                                            profile_id=profile_id,
                                            company_name=company_name,
                                            organization_id=organization_id
                                        )                        # Generate tokens using the CustomRefreshToken class       
                        refresh = CustomRefreshToken.for_user(custom_user)
                        access_token = refresh.access_token
                    except Exception as e:
                        logger.error(f"Error generating tokens: {str(e)}")
                        return JsonResponse({'error': 'Token generation failed'}, status=HTTP_401_UNAUTHORIZED)
                    
                    setup = False
                    cursor.execute(f"SELECT EXISTS(SELECT 1 FROM {schema}.profile WHERE id = %s AND profile_type in ('admin', 'superadmin', 'manager'))", [profile_id])
                    setup = cursor.fetchone()[0]

                    ip = get_client_ip(request)               
                    location = None
                    if not location:
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
                    # The old code spawned a raw threading.Thread that ran
                    # INSERT statements directly. That had THREE problems:
                    #   1. No tenant context — the thread skips the request
                    #      middleware, so search_path / role / app.current_org_id
                    #      were never pinned.
                    #   2. The session_log INSERT omitted organization_id, so
                    #      under FORCE ROW LEVEL SECURITY the WITH CHECK clause
                    #      rejects the row.
                    #   3. Raw SQL bypasses EncryptedCharField — the access /
                    #      refresh tokens were written to the DB in plaintext.
                    #
                    # Routing through the log_user_login_async Celery task
                    # (a TenantRequiredTask that uses the ORM) fixes all three:
                    # the ORM path encrypts the tokens, sets organization_id
                    # from the injected TenantContext, and runs inside a
                    # with_tenant_schema() block.
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
                    #Trigger notification for org admin
                    if not is_staff and not is_superuser:
                        kwargs["message"] = f"{username} is logged in at {datetime.now().strftime('%H:%M %p')}"
                        org_admin = get_admin_user(organization_id)
                        trigger_notication(
                        owner_id=org_admin,
                        channel_layer=channel,
                        title="Login alert",
                        notification_type='alert',
                        user_id=user_id,
                        channel='push',
                        request=request,
                        **kwargs
                        )
                    return response
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
# the ORM) — see the apply_async call in LoginView.post above.


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