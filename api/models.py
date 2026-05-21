import uuid
from django.db import models


from django.contrib.auth.models import  PermissionsMixin, UserManager, AbstractBaseUser
from django.utils import timezone
from django.utils.timezone import now
import os

# Phase 3 — encrypted-at-rest field types for secret columns
# (SessionLog.access_token / refresh_token below; future tables follow
# the same pattern). See docs/security/launch_readiness_plan.md Phase 3.
from api.security.encrypted_fields import EncryptedCharField

# Re-export tenant-scoped models so Django picks them up under the `api`
# app. See `api/tenant_models/__init__.py` for the per-tenant model
# definitions; they are all managed=False (Django doesn't own their schema).
from api.tenant_models import (  # noqa: F401  (re-exported for app discovery)
    # Wave 2 — object metadata + authorization
    PlatformObject,
    Field,
    Profile,
    UserGroup,
    UserGroupUser,
    UserGroupProfile,
    UserGroupPublicGroup,
    ObjectPermission,
    FieldPermission,
    TabPermission,
    AppPermission,
    SharingRecord,
    # Wave 3 — UI / layout
    App,
    PageLayout,
    SearchLayout,
    Listview,
    PageBuilder,
    PageComponent,
    PageBuilderAssignment,
    LayoutAssignment,
    HomepageAssignment,
    FieldMapping,
    # Wave 4 — reporting
    Report,
    ReportFolder,
    ReportFolderSharing,
    Dashboard,
    DashboardComponent,
    DashboardFolder,
    DashboardFolderSharing,
    DashboardAssignment,
    # Wave 5 — workflow
    Workflow,
    WorkflowNode,
    WorkflowEdge,
    PathBuilder,
    EmailTemplate,
    # Phase 3.B — integration / telephony / email
    TelephonyConfig,
    LandingNumber,
    TelephonyUser,
    CallActivity,
    EmailProviderSetup,
    UserGmailToken,
    UserOutlookToken,
    # Phase 3.B — audit / history
    AuditTrailTrack,
    FieldHistoryLog,
    FieldTrackingConfig,
    # Phase 3.B — misc
    Task,
    Notification,
    SharedRecord,
    # Phase 4.A — misc + shared
    OrgCompany,
    LeadCapture,
)

def organization_logo_path(instance, filename):
    return f"uploads/{instance.name}/{filename}"

class Organization(models.Model):
    """Model representing an organization/tenant in the system."""
    id = models.CharField(max_length=64, primary_key=True, editable=False)
    name = models.CharField(max_length=255, unique=True)
    database_schema = models.CharField(max_length=63, unique=True)
    is_active = models.BooleanField(default=True)
    created_date = models.DateTimeField(default=timezone.now)
    logo = models.ImageField(upload_to=organization_logo_path, null=True, blank=True)
    
    class Meta:
        db_table = 'organizations'
        verbose_name = 'Organization'
        verbose_name_plural = 'Organizations'
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.id:
            self.id = f"org_{uuid.uuid4().hex[:10]}"
        else:
            try:
                old_org = Organization.objects.get(pk=self.id)
                if old_org.logo and self.logo and old_org.logo != self.logo:
                    old_org.logo.delete(save=False)
            except Organization.DoesNotExist:
                pass
        super().save(*args, **kwargs)


class CustomUserManager(UserManager):
    def _create_user(self, email, password, **extra_fields):
        if not email:
            ValueError("Email not provided")
        if 'id' not in extra_fields or not extra_fields['id']:
            extra_fields['id'] = str(uuid.uuid4().hex[:10])
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        
        return user
    
    def create_user(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)
    
    def create_superuser(self, email=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self._create_user(email, password, **extra_fields)
    

class User(AbstractBaseUser, PermissionsMixin):
    id = models.CharField(max_length=64, primary_key=True, editable=False)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, db_column='organization_id')
    email = models.EmailField(default='', blank=True, unique=True)
    name = models.CharField(default='', max_length=255, blank=True)
    username = models.CharField(default='', max_length=255, blank=True)
    phone = models.CharField(default='', max_length=255, blank=True, null=True)
    first_name = models.CharField(max_length=255, blank=True, null=True)
    last_name = models.CharField(max_length=255, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_superuser = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    alias = models.CharField(max_length=255, blank=True, null=True)
    profile_id = models.CharField(max_length=255, blank=True, null=True)
    role_id = models.CharField(max_length=255, blank=True, null=True)
    manager_id = models.CharField(max_length=64, blank=True, null=True)
    time_zone_sid_key = models.CharField(max_length=100, blank=True, null=True)
    timezone = models.CharField(max_length=100, blank=True, null=True)
    locale = models.CharField(max_length=100, blank=True, null=True)
    locale_sid_key = models.CharField(max_length=100, blank=True, null=True)
    email_encoding_key = models.CharField(max_length=100, blank=True, null=True)
    language_locale_key = models.CharField(max_length=100, blank=True, null=True)
    user_type = models.CharField(max_length=100, blank=True, null=True)
    email_preferences_auto_bcc = models.BooleanField(default=False, blank=True, null=True)
    email_preferences_auto_bcc_stay_in_touch = models.BooleanField(default=False, blank=True, null=True)
    
    created_date = models.DateTimeField(auto_now_add=True)
    last_modified_date = models.DateTimeField(auto_now=True)
    last_login = models.DateTimeField(null=True, blank=True)
    
    company = models.CharField(max_length=255, blank=True, null=True)
    # Phase 3: SMTP app password encrypted at rest. max_length bumped
    # 128 → 512 to fit Fernet ciphertext overhead. Migration handles
    # the ALTER COLUMN.
    app_password = EncryptedCharField(max_length=512, blank=True, null=True)
    
    is_email_verified = models.BooleanField(default=False)

    objects = CustomUserManager()
    
    USERNAME_FIELD = 'email'
    EMAIL_FIELD = 'email'
    REQUIRED_FIELDS = []
    
    class Meta:
        db_table = 'users'
        verbose_name = 'User'
        verbose_name_plural = 'Users'
    def get_full_name(self):
        return self.name
    
    def get_short_name(self):
        return self.name or self.email.split('@')[0]        


class SessionLog(models.Model):
    id = models.CharField(max_length=64, primary_key=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sessions")
    # Phase 4 part 2: organization_id is the predicate Row-Level
    # Security uses to decide which rows a given tenant role can see.
    # Nullable initially so the migration can run before the backfill;
    # the backfill command + a follow-up NOT NULL migration close the loop.
    # Indexed because the RLS policy filters on it on every query.
    organization_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    profile_id = models.CharField(max_length=20, null=False)
    company_name = models.CharField(max_length=255)
    login_time = models.DateTimeField(default=now)
    logout_time = models.DateTimeField(null=True, blank=True)
    # Phase 3: encrypted at rest via api.security.token_encryption (ENC1: prefix).
    # max_length bumped from 500 → 1024 to fit Fernet's ~140-char overhead on
    # top of the original token. Legacy (pre-encryption) plaintext rows keep
    # decoding via decrypt_token's passthrough — see encrypt_legacy_session_tokens
    # management command for the backfill.
    access_token = EncryptedCharField(max_length=1024)
    refresh_token = EncryptedCharField(max_length=1024)
    expiry_time = models.DateTimeField(null=True, blank=True)  # Optional: expiry of the session
    ip_address = models.GenericIPAddressField(null=True, blank=True)  # For IPv4 and IPv6
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)  # Latitude
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    
    class Meta:
        db_table = 'session_log'
        verbose_name = 'Session Log'
        verbose_name_plural = 'Session Logs'
  
    def save(self, *args, **kwargs):
        if not self.id:  # Generate a UUID-based ID
            random_id = uuid.uuid4().hex[:10]  # Take the first 9 characters of a UUID
            self.id = f"087ulin{random_id}hs"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Session for {self.user.username} (Profile ID: {self.profile_id}) at {self.login_time} access_token: {self.access_token[-4:]}"
    
    
    
class UserLoginHistory(models.Model):
    id = models.CharField(max_length=64, primary_key=True, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    # Phase 4 part 2: organization_id for RLS scoping. Nullable on the
    # initial migration so backfill can run; tightened to NOT NULL in
    # a follow-up migration after backfill completes. See
    # ``backfill_organization_id`` management command.
    organization_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    login_time = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    login_type = models.CharField(max_length=50, choices=[('success', 'Success'), ('failed', 'Failed')], default='success')
    status = models.CharField(max_length=50, default='Success')  # Success, Failed, Locked, etc.
    browser = models.CharField(max_length=255, null=True, blank=True)
    location = models.CharField(max_length=50, default='Unknown')  
    platform = models.CharField(max_length=255, null=True, blank=True)
    application = models.CharField(max_length=255, default='Web')  # Default to 'Web' (or can be dynamic)
    client_version = models.CharField(max_length=255, null=True, blank=True)
    api_type = models.CharField(max_length=50, null=True, blank=True)
    api_version = models.CharField(max_length=50, null=True, blank=True)
    login_url = models.URLField(max_length=512, null=True, blank=True)

    def __str__(self):
        return f"{self.user.username if self.user else 'Unknown'} logged in at {self.login_time}"

    class Meta:
        ordering = ['-login_time']
        db_table = 'user_login_history'
        verbose_name = 'Login History'
        verbose_name_plural = 'Login History'
  
    def save(self, *args, **kwargs):
        if not self.id:  # Generate a UUID-based ID
            random_id = uuid.uuid4().hex[:10]  # Take the first 9 characters of a UUID
            self.id = f"087ulin{random_id}hs"
        super().save(*args, **kwargs)

        
    
    
    
class UserMFA(models.Model):
    """Phase C9 — per-user multi-factor-auth state.

    A separate model (OneToOne to User) rather than columns on User,
    so the auth-sensitive fields are isolated and the User model
    stays focused.

    ``secret`` is the TOTP secret — as sensitive as a password, so
    it's stored with EncryptedCharField (encrypted at rest).
    ``recovery_codes`` holds the HASHED one-time recovery codes
    (never plaintext). ``enabled`` is False during enrollment and
    flips True only after the user confirms a code.
    """

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="mfa",
        db_column="user_id",
    )
    # TOTP secret — encrypted at rest. max_length 512 covers the
    # base32 secret plus Fernet overhead.
    secret = EncryptedCharField(max_length=512)
    # False until the user verifies a code during enrollment.
    enabled = models.BooleanField(default=False)
    # JSON list of HASHED recovery codes (one-time backup codes).
    recovery_codes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "user_mfa"
        verbose_name = "User MFA"
        verbose_name_plural = "User MFA"

    def __str__(self):
        state = "enabled" if self.enabled else "pending"
        return f"MFA for {self.user_id} ({state})"


# class FacebookLeadWebhooks(models.Model):
#     id = models.CharField(primary_key=True, editable=False, max_length=64)
#     webhook = models.URLField(max_length=1024),
#     lead_id = models.CharField(max_length=32)
#     page_id = models.CharField(max_length=32)
#     ad_id = models.CharField(max_length=32)
#     created_by = models.ForeignKey(User, related_name='fbh_created_by', on_delete=models.CASCADE)
#     created_date = models.DateField(auto_now_add=True)
    
#     def save(self, *args, **kwargs):
#         if not self.id:  # Generate a UUID-based ID
#             random_id = uuid.uuid4().hex[:10]  # Take the first 9 characters of a UUID
#             self.id = f"0044flws{random_id}as"
#         super().save(*args, **kwargs)

#     class Meta:
#         db_table = 'facebookleadwebhooks'
#         verbose_name = 'App'
#         verbose_name_plural = 'Apps'

