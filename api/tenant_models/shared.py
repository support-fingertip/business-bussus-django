"""Phase 4.A — shared-schema (public) models.

Most models in this package are **per-tenant** (live in each tenant's
PostgreSQL schema, ``managed = False``). A small set of tables are
SHARED instead — they live in the ``public`` schema and rows are
scoped by an ``organization_id`` column rather than by schema.

The canonical list of shared tables is in
``api/ORM/sqlFunctions/getQueryBuilder.py:SHARED_TABLES`` —
``{"organizations", "lead_capture", "user_login_history"}``.

Of those three, ``organizations`` and ``user_login_history`` are
already Django-managed models (see ``api/models.py``). ``lead_capture``
was the odd one out — queried from raw cursor at
``facebook/leadwebhook.py:159`` but with no Django model and no
canonical DDL anywhere in source control.

Phase 4.A closes the gap. This module adds ``LeadCapture`` as a
``managed = False`` model (production deployments may already have a
divergent table; we don't want Django migrations to touch it). The
canonical DDL ships in ``sqlfiles/shared_tables.sql`` for operators
to apply manually after introspecting the production shape.

The column shape was inferred from
``files/fields_inserts_no_id.sql:2206-2284`` (the field registry —
the strongest evidence we have for the canonical column list) plus
the runtime query at ``facebook/leadwebhook.py:159``.
"""

from __future__ import annotations

from django.db import models


class LeadCapture(models.Model):
    """``lead_capture`` — Facebook Lead Ads capture configuration (shared).

    NOT a tenant-scoped table — lives in the ``public`` schema. Rows
    are filtered by ``organization_id`` rather than by search_path.
    The query builder enforces this scoping (see
    ``getQueryBuilder.py:SHARED_TABLES``).
    """

    id = models.CharField(max_length=64, primary_key=True)
    organization_id = models.CharField(max_length=64, db_index=True)
    lead_page_id = models.CharField(max_length=255, null=True, blank=True)
    lead_page_name = models.CharField(max_length=255, null=True, blank=True)
    lead_form_id = models.CharField(max_length=255, db_index=True, null=True, blank=True)
    lead_form_name = models.CharField(max_length=255, null=True, blank=True)
    page_access_token = models.TextField(null=True, blank=True)
    form_status = models.CharField(max_length=64, null=True, blank=True)
    field_mapping = models.JSONField(null=True, blank=True)
    task_status = models.CharField(max_length=64, null=True, blank=True)
    webhook_url = models.CharField(max_length=2048, null=True, blank=True)

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    owner_id = models.CharField(max_length=64, null=True, blank=True)

    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False  # Production may have divergent shape; reconcile via sqlfiles/shared_tables.sql
        app_label = "api"
        db_table = "lead_capture"
        verbose_name = "Lead Capture"
        verbose_name_plural = "Lead Captures"
