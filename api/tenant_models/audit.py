"""Phase 3.B — audit / history models.

Tables modeled here:
  audit_trail_track     — AuditTrailTrack (action log)
  field_history_log     — FieldHistoryLog (per-field value change log)
  field_tracking_config — FieldTrackingConfig (which fields are tracked)

All models managed=False; FKs db_constraint=False. See ADR-0003.
"""

from __future__ import annotations

from django.db import models

from api.tenant_models._base import TenantModel


class AuditTrailTrack(TenantModel):
    """``audit_trail_track`` — append-only action log.

    One row per logged platform action (object/field create/update,
    profile change, login, etc.). Written via
    ``api.ORM.AuditLogs.audit_trail_logs.log_audit``.
    """

    id = models.CharField(max_length=64, primary_key=True)
    source_namespace_prefix = models.CharField(max_length=100, null=True, blank=True)
    action = models.TextField()
    section = models.CharField(max_length=100)
    is_delegate_user = models.BooleanField()
    changed_at = models.DateTimeField()
    user_id = models.CharField(max_length=64, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "audit_trail_track"
        verbose_name = "Audit Trail Track"
        verbose_name_plural = "Audit Trail Tracks"


class FieldHistoryLog(TenantModel):
    """``field_history_log`` — per-field value change log.

    Written when a field on a tracked object changes (see
    ``FieldTrackingConfig`` for which fields are tracked).
    """

    id = models.CharField(max_length=64, primary_key=True)
    object_name = models.CharField(max_length=255)
    record_id = models.CharField(max_length=255)
    field_name = models.CharField(max_length=255)
    old_value = models.TextField(null=True, blank=True)
    new_value = models.TextField(null=True, blank=True)
    user_id = models.CharField(max_length=64, null=True, blank=True)
    changed_at = models.DateTimeField()
    created_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "field_history_log"
        verbose_name = "Field History Log"
        verbose_name_plural = "Field History Log Entries"


class FieldTrackingConfig(TenantModel):
    """``field_tracking_config`` — per-(object, field) tracking flag.

    Drives whether a field's changes are written to FieldHistoryLog
    when an update happens.
    """

    id = models.CharField(max_length=64, primary_key=True)
    object_name = models.CharField(max_length=255)
    field_name = models.CharField(max_length=255)
    is_tracked = models.BooleanField()
    created_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "field_tracking_config"
        verbose_name = "Field Tracking Config"
        verbose_name_plural = "Field Tracking Configs"
        unique_together = (("object_name", "field_name"),)
