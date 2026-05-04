"""Phase 3.B (+ Phase 4.A) — miscellaneous tenant-scoped models.

Tables modeled here:
  task            — Task (per-tenant task / to-do)
  notifications   — Notification (in-app / email / push)
  shared_records  — SharedRecord  (per-RECORD ad-hoc sharing grants —
                                   NOT to be confused with
                                   ``sharing_records`` which is per-OBJECT
                                   default access; see Phase 2.RM
                                   ``api/tenant_models/sharing.py``
                                   docstring for the full disambiguation)
  org_company     — OrgCompany (per-tenant company info — added in
                                Phase 4.A after the DDL block was
                                un-commented; see operator notes)

All models managed=False; FKs db_constraint=False. See ADR-0003.
"""

from __future__ import annotations

from django.db import models

from api.tenant_models._base import TenantModel
from api.tenant_models.objects import PlatformObject


class Task(TenantModel):
    """``task`` — per-tenant task/to-do, optionally linked to a record."""

    id = models.CharField(max_length=64, primary_key=True)
    # The DDL uses a sequence-based default `'TASK-' || nextval(...)`
    # — the model treats it as a plain CharField; the DB fills it.
    name = models.CharField(max_length=16, blank=True)
    subject = models.CharField(max_length=512)
    description = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=255)
    due_date = models.DateField()

    related_to_object_id = models.CharField(max_length=64, null=True, blank=True)
    object = models.ForeignKey(
        PlatformObject,
        db_column="object_id",
        related_name="tasks",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )
    assigned_to_id = models.CharField(max_length=64, null=True, blank=True)
    organisation = models.CharField(max_length=64, null=True, blank=True)

    owner_id = models.CharField(max_length=64, null=True, blank=True)
    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    deleted_by_id = models.CharField(max_length=255, null=True, blank=True)
    is_deleted = models.BooleanField(default=False)

    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)
    deleted_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "task"
        verbose_name = "Task"
        verbose_name_plural = "Tasks"


class Notification(TenantModel):
    """``notifications`` — in-app / email / push notification queue.

    Channel/type/status/priority columns mirror the DB-level CHECK
    constraints in default_tables.sql; the choices below are
    documentation but Django's choice validation is also a useful
    model-form belt-and-braces.
    """

    id = models.CharField(max_length=64, primary_key=True)
    owner_id = models.CharField(max_length=64)
    title = models.CharField(max_length=255, null=True, blank=True)
    message = models.TextField()

    CHANNEL_CHOICES = [
        ("email", "Email"), ("whatsapp", "WhatsApp"),
        ("app", "App"), ("sms", "SMS"), ("push", "Push"),
    ]
    TYPE_CHOICES = [
        ("verification", "Verification"), ("reminder", "Reminder"),
        ("alert", "Alert"), ("system", "System"), ("chat", "Chat"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"), ("sent", "Sent"),
        ("delivered", "Delivered"), ("read", "Read"),
        ("failed", "Failed"),
    ]
    PRIORITY_CHOICES = [
        ("low", "Low"), ("normal", "Normal"), ("high", "High"),
    ]
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES)
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending",
    )
    priority = models.CharField(
        max_length=10, choices=PRIORITY_CHOICES, default="normal",
    )

    metadata = models.JSONField(null=True, blank=True)
    url = models.CharField(max_length=2048, null=True, blank=True)

    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "notifications"
        verbose_name = "Notification"
        verbose_name_plural = "Notifications"


class SharedRecord(TenantModel):
    """``shared_records`` — per-RECORD ad-hoc sharing grants.

    DO NOT CONFUSE with ``sharing_records`` (per-OBJECT default access
    level). See ``api/tenant_models/sharing.py`` module docstring for
    the disambiguation; the matching reader code is at
    ``api/permissions/FetchUsers/fetch_shared_records.py``.

    ``access_mask`` is a bitmask:
        1 = READ
        2 = WRITE
        4 = DELETE
        8 = SHARE
    """

    id = models.CharField(max_length=64, primary_key=True)
    object_name = models.TextField()
    record_id = models.CharField(max_length=64)
    user_id = models.CharField(max_length=64)
    owner_id = models.CharField(max_length=64)
    access_mask = models.IntegerField()

    ROW_CAUSE_CHOICES = [
        ("OWNER", "Owner"),
        ("OWD", "Org-Wide Default"),
        ("MANUAL", "Manual"),
        ("HIERARCHY", "Role Hierarchy"),
        ("RULE", "Sharing Rule"),
        ("PARENT", "Parent Implicit"),
    ]
    row_cause = models.CharField(max_length=32, choices=ROW_CAUSE_CHOICES)

    created_date = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # Bitmask convenience constants — match fetch_shared_records.access_mask_map.
    ACCESS_READ = 1
    ACCESS_WRITE = 2
    ACCESS_DELETE = 4
    ACCESS_SHARE = 8

    class Meta(TenantModel.Meta):
        db_table = "shared_records"
        verbose_name = "Shared Record (per-record grant)"
        verbose_name_plural = "Shared Records (per-record grants)"


class OrgCompany(TenantModel):
    """``org_company`` — per-tenant company information (single-row by convention).

    Added in Phase 4.A after the DDL block was un-commented in
    ``default_tables.sql``. The shape was already complete in source
    control — every line was just `--`-prefixed. No code queries this
    table yet; the model exists so future feature work can use the
    ORM directly.
    """

    id = models.CharField(max_length=64, primary_key=True)
    company_name = models.CharField(max_length=255)
    primary_contact = models.CharField(max_length=255, null=True, blank=True)
    division = models.CharField(max_length=255, null=True, blank=True)
    phone = models.CharField(max_length=64, null=True, blank=True)
    fax = models.CharField(max_length=64, null=True, blank=True)
    email = models.CharField(max_length=255, null=True, blank=True)
    website = models.CharField(max_length=512, null=True, blank=True)
    street = models.CharField(max_length=512, null=True, blank=True)
    city = models.CharField(max_length=255, null=True, blank=True)
    state = models.CharField(max_length=255, null=True, blank=True)
    postal_code = models.CharField(max_length=32, null=True, blank=True)
    country = models.CharField(max_length=255, null=True, blank=True)
    default_currency = models.CharField(max_length=8, default="USD")
    default_language = models.CharField(max_length=8, default="en")
    timezone = models.CharField(max_length=64, default="UTC")
    fiscal_year_start_month = models.CharField(max_length=16, default="April")
    description = models.TextField(null=True, blank=True)
    logo = models.CharField(max_length=2048, null=True, blank=True)

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    deleted_by_id = models.CharField(max_length=64, null=True, blank=True)
    is_deleted = models.BooleanField(default=False)

    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)
    deleted_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "org_company"
        verbose_name = "Organization Company"
        verbose_name_plural = "Organization Companies"
