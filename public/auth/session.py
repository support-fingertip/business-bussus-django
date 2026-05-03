from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist
from django.db import connection
from django.http import JsonResponse
import psycopg2
from django.conf import settings
from django.http import HttpRequest
from CacheService.cache import CacheService, DjangoCacheBackend
from utils.custom_refresh_token import get_jwt_payload
import logging

logger = logging.getLogger(__name__)


def get_access_token(request):
    """
    Retrieve the access token from the Authorization header.
    """
    auth_header = request.headers.get('Authorization')
    if auth_header and auth_header.startswith('Bearer '):
        return auth_header.split(' ')[1]  # Extract the token part
    return None

def get_client_ip(request):
    """
    Retrieve the client's IP address from the request.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # If multiple IPs are in the header, get the first one
        ip = x_forwarded_for.split(',')[0]
    else:
        ip = request.META.get('REMOTE_ADDR')
    # Strip port if present
    if ip and ':' in ip:
        ip = ip.split(':')[0]
    return ip

def get_user_details(request, **kwargs):
    """
    Retrieve user details based on the access token.
    """
    sessions = apps.get_model('api', 'SessionLog')
    access_token = get_access_token(request)
    try:
        details = sessions.objects.get(access_token=access_token)
        profile = details.profile_id
        company = details.company_name

        return {
            "profile": profile,
            "company": company,
            "name": details.user.name,
            "user_id": details.user.id,
        }

    except ObjectDoesNotExist:
        return None

    except Exception as e:
        raise Exception(f"Error retrieving user details: {str(e)}")
                


def get_connection_and_user_details(request):
    """
    Retrieve user details, organization details, and establish a connection to the schema based on the organization database schema.
    """
    # access_token = get_access_token(request)
    user_id = {}
    user_id["user_id"] = request.user.__dict__.get('id')
    referer = get_request_came_from(request)
    db_config = settings.DATABASES.get('default')
    if not db_config:
        raise ValueError(f"No DB config found for alias default.")    
    cursor = connection.cursor()
    user_details = None
    cache = CacheService()
    try:    
        result = cache.get(user_id["user_id"], "users_org")
    except Exception as er:
        logger.warning(f"Cache retrieval error: {str(er)}")
        result = None
    if result:
        return result.get('user_data'), result.get('org_data'), None, result.get('profile_id'), result.get('schema_name'),referer
    logger.debug("Fetching user details from DB...")
    try:
        # First, get the user details and organization schema information
        try:
            cursor.execute("""
            SELECT u.id AS id, 
                   u.name AS name, 
                   u.profile_id, 
                   u.organization_id, 
                   u.email,
                   org.name AS org_name, 
                   org.database_schema AS schema, 
                   org.db_user AS db_user, 
                   org.db_password AS db_password,
                   u.is_active      
            FROM public.users AS u
            JOIN public.organizations AS org ON u.organization_id = org.id
            WHERE u.id = %s
        """, [user_id["user_id"]])
            user_details = cursor.fetchone()
            if user_details is None:
                JsonResponse({"error": "No organisation found for the user."}, status=300)
        except psycopg2.Error as e:
            raise Exception(f"Database error: {str(e)}")        

        if user_details:
            # Extract the user and organization details
            user_id = user_details[0]
            name = user_details[1]
            profile_id = user_details[2]
            organization_id = user_details[3]
            email = user_details[4]
            org_name = user_details[5]
            schema_name = user_details[6]
            db_user = user_details[7]
            db_password = user_details[8]
            is_active = user_details[9]
            user_data = {
                "id": user_id,
                "name": name,
                "profile_id": profile_id,
                "email": email,
                "is_active": is_active
            }
            org_data = {
                "id": organization_id,
                "name": org_name,
                "schema": schema_name,
                "db_user": db_user,
                "db_password": db_password
            }

            if not profile_id:
                raise ValueError("No profile is assigned to the user. Please contact your administrator.")
            if not schema_name:
                raise ValueError("No schema is assigned to the organization. Please contact your administrator.")
            # Return user details, organization details, and the database connection
            cache.set(user_id, {'user_data': user_data, 'org_data': org_data, 'profile_id': profile_id, 'schema_name': schema_name}, "users_org", ttl=6000)  # Cache indefinitely until logout
            return user_data, org_data, None, profile_id, schema_name, referer
            
        else:
            return None, None, None  # If no user details found, return None for all
    except Exception as e:
        # Handle unexpected exceptions and raise with a proper message
        logger.error(f"Error retrieving user details: {str(e)}")
        raise Exception(f"Error retrieving user details: {str(e)}")

    finally:
        cursor.close()  # Ensure the cursor is closed to avoid connection leakage
        # The DB connection and cursor will be handled externally, so no need to close them here.


def get_request_came_from(request:HttpRequest):
    try:
        referer = request.headers.get("X-Frontend-URL","")
        return referer or ''
    except Exception as er:
        return ''