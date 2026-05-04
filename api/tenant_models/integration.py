"""Phase 3 Wave 6 (Phase 3.B) — integration / telephony / email models.

Tables modeled here:
  telephony_config       — TelephonyConfig
  landing_numbers        — LandingNumber
  telephony_user         — TelephonyUser
  callactivity           — CallActivity
  email_provider_setup   — EmailProviderSetup
                           (Phase 0.8 encrypts cred at rest; this model
                            exposes cred as TextField — callers must
                            decrypt via api.security.token_encryption)
  user_gmail_tokens      — UserGmailToken (legacy; superseded by
                           email_provider_setup but still created)
  user_outlook_tokens    — UserOutlookToken (legacy; same)

All models managed=False; FKs db_constraint=False. See ADR-0003.
"""

from __future__ import annotations

from django.contrib.postgres.fields import ArrayField
from django.db import models

from api.tenant_models._base import TenantModel


class TelephonyConfig(TenantModel):
    """``telephony_config`` — per-tenant telephony provider configuration."""

    id = models.CharField(max_length=64, primary_key=True)
    provider = models.CharField(max_length=50, null=True, blank=True)
    target_object = models.CharField(max_length=100, null=True, blank=True)
    target_field = models.CharField(max_length=100, null=True, blank=True)

    # ``TEXT[]`` arrays — Django's ArrayField wraps the Postgres type.
    display_fields = ArrayField(
        models.TextField(), null=True, blank=True, default=list,
    )
    disposition_values = ArrayField(
        models.TextField(), null=True, blank=True, default=list,
    )

    status = models.BooleanField(default=True)
    authtoken = models.CharField(max_length=512, null=True, blank=True)
    sid = models.CharField(max_length=512, null=True, blank=True)

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    deleted_by_id = models.CharField(max_length=64, null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)
    deleted_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "telephony_config"
        verbose_name = "Telephony Config"
        verbose_name_plural = "Telephony Configs"


class LandingNumber(TenantModel):
    """``landing_numbers`` — phone numbers routed by telephony_config."""

    id = models.CharField(max_length=64, primary_key=True)
    telephony_id = models.CharField(max_length=100, null=True, blank=True)
    landing_number = models.CharField(max_length=20, null=True, blank=True)
    group_name = models.CharField(max_length=100, null=True, blank=True)
    routing_logic = models.CharField(max_length=20, null=True, blank=True)
    status = models.BooleanField(default=True)
    group_id = models.TextField(null=True, blank=True)

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    deleted_by_id = models.CharField(max_length=64, null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)
    deleted_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "landing_numbers"
        verbose_name = "Landing Number"
        verbose_name_plural = "Landing Numbers"


class TelephonyUser(TenantModel):
    """``telephony_user`` — per-(user, config) telephony details/extension."""

    id = models.CharField(max_length=64, primary_key=True)
    config_name = models.CharField(max_length=50, null=True, blank=True)
    user_id = models.CharField(max_length=64)
    details = models.JSONField(null=True, blank=True)
    status = models.BooleanField(default=True)

    created_date = models.DateTimeField(null=True, blank=True)
    updated_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "telephony_user"
        verbose_name = "Telephony User"
        verbose_name_plural = "Telephony Users"


class CallActivity(TenantModel):
    """``callactivity`` — log of telephony calls (data is provider-specific)."""

    id = models.CharField(max_length=64, primary_key=True)
    data = models.JSONField(null=True, blank=True)
    user_id = models.CharField(max_length=64, null=True, blank=True)

    created_date = models.DateTimeField(null=True, blank=True)
    updated_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "callactivity"
        verbose_name = "Call Activity"
        verbose_name_plural = "Call Activities"


class EmailProviderSetup(TenantModel):
    """``email_provider_setup`` — per-user OAuth credentials store.

    SECURITY: ``cred`` is encrypted at rest (Phase 0.8). Callers MUST
    decrypt via ``api.security.token_encryption.decrypt_token()`` before
    use; never read the raw column in new code.
    """

    id = models.CharField(max_length=64, primary_key=True)
    user_id = models.CharField(max_length=64, unique=True)
    PROVIDER_CHOICES = [
        ("gmail", "Gmail"),
        ("outlook", "Outlook"),
        ("sendgrid", "SendGrid"),
    ]
    provider = models.CharField(max_length=50, choices=PROVIDER_CHOICES)
    # Encrypted ciphertext; treat as opaque string.
    cred = models.JSONField(null=True, blank=True)

    created_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "email_provider_setup"
        verbose_name = "Email Provider Setup"
        verbose_name_plural = "Email Provider Setups"


class _UserOAuthTokenBase(TenantModel):
    """Shared columns for the legacy per-provider token tables.

    These predate ``email_provider_setup`` (which consolidates all
    providers into one table). Kept for compatibility with code that
    still reads them; new code should write through
    ``email_provider_setup``.
    """

    id = models.CharField(max_length=64, primary_key=True)
    user_id = models.CharField(max_length=64, unique=True)
    access_token = models.TextField(null=True, blank=True)
    refresh_token = models.TextField(null=True, blank=True)
    token_type = models.TextField(null=True, blank=True)
    expires_in = models.IntegerField(null=True, blank=True)
    expiry_time = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        abstract = True


class UserGmailToken(_UserOAuthTokenBase):
    class Meta(_UserOAuthTokenBase.Meta):
        db_table = "user_gmail_tokens"
        verbose_name = "User Gmail Token"
        verbose_name_plural = "User Gmail Tokens"


class UserOutlookToken(_UserOAuthTokenBase):
    class Meta(_UserOAuthTokenBase.Meta):
        db_table = "user_outlook_tokens"
        verbose_name = "User Outlook Token"
        verbose_name_plural = "User Outlook Tokens"
