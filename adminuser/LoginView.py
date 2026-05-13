import uuid
from django.contrib.auth import authenticate
from django.http import JsonResponse
from django.views import View
import requests
from rest_framework.status import HTTP_200_OK, HTTP_401_UNAUTHORIZED
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
import json
from django.utils.timezone import now
from django.db import connection
from public.auth.session import get_client_ip
from utils.custom_refresh_token import CustomRefreshToken
from django.db import transaction
from user_agents import parse
from django.core.cache import cache  # For caching IP locations
from django.contrib.auth.hashers import check_password
from adminuser.tasks import log_user_login_async
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
class LoginView(View):
    def post(self, request, *args, **kwargs):
        try:
            # Parse the request body
            data = json.loads(request.body)
            username = data.get('username')
            password = data.get('password')

            with connection.cursor() as cursor:
                cursor.execute("SELECT id, username, email, password, profile_id, company, organization_id, name, timezone, is_active, is_superuser, is_staff FROM public.users WHERE username = %s and is_superuser", [username])
                user = cursor.fetchone()
                
            if user:
                user_id, username, email, hashed_password, profile_id, company_name, organization_id, name, timezone, is_active, is_superuser, is_staff = user
                
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
                        print(f"Error generating tokens: {e}")
                        return JsonResponse({'error': 'Token generation failed'}, status=HTTP_401_UNAUTHORIZED)

                    # Get profile_id and company_name
                    profile_id = profile_id
                    company_name = company_name
                    organization_id = organization_id
                    ip = get_client_ip(request)                    
                    # Attempt to fetch location from cache, if not available, get it from IP
                    location = cache.get(ip)
                    if not location:
                        location = get_location_from_ip(ip)
                        cache.set(ip, location, timeout=3600)  # Cache for 1 hour

                    user_agent = request.META.get('HTTP_USER_AGENT')
                    platform, browser = get_platform_and_browser(user_agent)
                    
                    login_url = request.build_absolute_uri()

                    # ✅ Send response back immediately
                    response_data = {
                        'access': str(access_token),
                        'refresh': str(refresh),
                        'user': {
                            'id': user_id,
                            'username': username,
                            'email': email,
                            'profile_id': profile_id,
                            'company': company_name,
                            'name': name,
                            'timezone': timezone,
                        }
                    }
                    response = JsonResponse(response_data, status=HTTP_200_OK)

                    # Phase 6 adoption: log_user_login_async is now a
                    # TenantRequiredTask. The login flow runs BEFORE the
                    # tenant middleware (the JWT doesn't exist yet at
                    # login start), so we build a TenantContext explicitly
                    # from the row we just looked up.
                    #
                    # The org_id from the DB lookup is authoritative — it
                    # came from the JOIN on the user row, not from a
                    # JWT claim. So it's safe to pass directly.
                    try:
                        from api.celery_tasks.base import serialize_ctx
                        from api.security.schema_authority import TenantContext
                        from django.db import connection as _conn

                        # Phase 6 adoption: TenantRequiredTask needs a
                        # TenantContext, which needs the org's schema name.
                        # The user-lookup query above doesn't JOIN
                        # organizations; one extra round-trip to fetch it.
                        # On hot login paths this is acceptable (login is
                        # already a multi-statement flow).
                        with _conn.cursor() as _c:
                            _c.execute(
                                "SELECT database_schema FROM public.organizations WHERE id = %s",
                                [organization_id],
                            )
                            _row = _c.fetchone()
                            schema_for_ctx = _row[0] if _row else None

                        if not schema_for_ctx:
                            logger.error(
                                "Cannot queue log_user_login_async: "
                                "no schema for org %s",
                                organization_id,
                            )
                            raise RuntimeError("no schema for org")

                        tenant_ctx = TenantContext(
                            org_id=str(organization_id),
                            schema=schema_for_ctx,
                            profile_id=str(profile_id) if profile_id else None,
                        )
                        log_user_login_async.apply_async(
                            kwargs={
                                "_tenant_ctx": serialize_ctx(tenant_ctx),
                                "user_id": user_id,
                                "profile_id": profile_id,
                                "company_name": company_name,
                                "ip": ip,
                                "location": location,
                                "browser": browser,
                                "platform": platform,
                                "client_version": data.get('client_version'),
                                "api_type": data.get('api_type'),
                                "api_version": data.get('api_version', '1.0'),
                                "login_url": login_url,
                                "access_token": str(access_token),
                                "refresh_token": str(refresh),
                            },
                        )
                    except Exception as e:
                        # Log error but don't fail the login
                        logger.error(f"Failed to queue login logging task: {str(e)}")
                    
                    return response
                else:
                    return JsonResponse({'error': 'Invalid password for the username'}, status=HTTP_401_UNAUTHORIZED)
            else:
                return JsonResponse({'error': 'Admin username does not exist.'}, status=HTTP_401_UNAUTHORIZED)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON format'}, status=HTTP_401_UNAUTHORIZED)

def get_platform_and_browser(user_agent):
    if user_agent:
        ua = parse(user_agent)
        platform = ua.os.family
        browser = ua.browser.family
        return platform, browser
    return 'Unknown', 'Unknown'

def get_location_from_ip(ip_address):
    """
    Get location information from IP address using ipinfo.io API.
    
    Args:
        ip_address: The IP address to look up
        
    Returns:
        str: City name or 'Unknown' if lookup fails
    """
    try:
        # Add timeout to prevent hanging
        response = requests.get(
            f'https://ipinfo.io/{ip_address}/json',
            timeout=5
        )
        response.raise_for_status()
        data = response.json()
        location = data.get('city', 'Unknown')
        logger.info(f"Location lookup for {ip_address}: {location}")
        return location
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout looking up location for IP: {ip_address}")
        return 'Unknown'
    except requests.exceptions.RequestException as e:
        logger.warning(f"Error looking up location for IP {ip_address}: {str(e)}")
        return 'Unknown'

def log_user_login(user, profile_id, company_name, ip, location, browser, platform, data, login_url, refresh, access_token, organization_id):
    """
    Perform background operations (logging session and history)
    """
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                random_id = uuid.uuid4().hex[:10]
                cursor.execute(""" 
                    INSERT INTO session_log (
                        id, user_id, profile_id, company_name, login_time, 
                        access_token, refresh_token, ip_address
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    f"087ulin{random_id}hs", user.id, profile_id, company_name, now(),
                    str(access_token), str(refresh), ip
                ))

                cursor.execute("""
                    INSERT INTO user_login_history (
                        id, users_id, ip_address, location, login_type, status,
                        browser, platform, application, client_version, 
                        api_type, api_version, login_url, login_time, organization_id
                    )
                    VALUES (%s, %s, %s, %s, 'success', 'Success', %s, %s, 'Web', %s, %s, %s, %s, %s, %s)
                """, (
                    f"087ulin{random_id}hs", user.id, ip, location, browser, platform,
                    data.get('client_version', 'Unknown'),
                    data.get('api_type', 'Unknown'),
                    data.get('api_version', '1.0'),
                    login_url,
                    now(),
                    organization_id
                ))
    except Exception as e:
        print(f"Error logging user login: {e}")
