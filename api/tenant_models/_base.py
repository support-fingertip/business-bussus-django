"""Shared base class for tenant-scoped models.

Every Wave 2 model:
  - is unmanaged (Django doesn't run DDL),
  - lives in the per-tenant schema (set by TenantSchemaMiddleware),
  - belongs to the ``api`` Django app (per ADR-0001 we don't split apps).

The abstract base centralises ``Meta`` defaults so each model file
stays focused on the table-specific fields.
"""

from __future__ import annotations

from django.db import models


class TenantModel(models.Model):
    """Abstract base — sets ``managed = False`` and ``app_label = 'api'``."""

    class Meta:
        abstract = True
        managed = False
        app_label = "api"
