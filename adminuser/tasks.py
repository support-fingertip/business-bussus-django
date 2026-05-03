"""
Celery tasks for adminuser app.
"""
from celery import shared_task
from django.db import transaction
from django.utils.timezone import now
from api.models import SessionLog, UserLoginHistory, User
import logging

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def log_user_login_async(self, user_id, profile_id, company_name, ip, location, 
                        browser, platform, client_version, api_type, api_version, 
                        login_url, access_token, refresh_token):
    """
    Asynchronous task to log user login to session_log and user_login_history tables.
    
    This task replaces the threading approach with a proper background task queue.
    
    Args:
        user_id: The ID of the user logging in
        profile_id: User's profile ID
        company_name: Name of the company
        ip: IP address of the login
        location: Geographic location of the login
        browser: Browser used for login
        platform: Platform/OS used for login
        client_version: Version of the client
        api_type: Type of API used
        api_version: Version of the API
        login_url: URL where login occurred
        access_token: Generated access token
        refresh_token: Generated refresh token
    """
    try:
        with transaction.atomic():
            # Get user object
            try:
                user = User.objects.get(id=user_id)
            except User.DoesNotExist:
                logger.error(f"User {user_id} not found for login logging")
                return {"status": "failed", "error": "User not found"}
            
            # Create session log entry using ORM
            SessionLog.objects.create(
                user=user,
                profile_id=profile_id,
                company_name=company_name,
                login_time=now(),
                access_token=str(access_token),
                refresh_token=str(refresh_token),
                ip_address=ip
            )
            
            # Create login history entry using ORM
            UserLoginHistory.objects.create(
                user=user,
                ip_address=ip,
                location=location,
                login_type='success',
                status='Success',
                browser=browser,
                platform=platform,
                application='Web',
                client_version=client_version or 'Unknown',
                api_type=api_type or 'Unknown',
                api_version=api_version or '1.0',
                login_url=login_url
            )
        
        logger.info(f"Successfully logged login for user {user_id}")
        return {"status": "success", "user_id": user_id}
        
    except Exception as e:
        logger.error(f"Error logging user login for {user_id}: {str(e)}")
        # Retry the task if it fails
        try:
            self.retry(countdown=60, exc=e)
        except self.MaxRetriesExceededError:
            logger.error(f"Max retries exceeded for logging user {user_id} login")
            return {"status": "failed", "error": str(e)}
