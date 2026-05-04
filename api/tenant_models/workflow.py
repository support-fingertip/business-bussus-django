"""Phase 3 Wave 5 — workflow / automation models.

Tables modeled here:
  workflow         — Workflow (top-level definition)
  workflow_node    — WorkflowNode (graph node)
  workflow_edge    — WorkflowEdge (graph edge)
  path_builder     — PathBuilder (stage-based progression UI)
  email_templates  — EmailTemplate (used by send-email workflow nodes)

All models managed=False; FKs db_constraint=False. See ADR-0003.
"""

from __future__ import annotations

from django.db import models

from api.tenant_models._base import TenantModel
from api.tenant_models.objects import Field, PlatformObject


class Workflow(TenantModel):
    """``workflow`` — top-level workflow definition."""

    id = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255)
    trigger_type = models.CharField(max_length=20, default="create")
    module_name = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "workflow"
        verbose_name = "Workflow"
        verbose_name_plural = "Workflows"


class WorkflowNode(TenantModel):
    """``workflow_node`` — node in a workflow graph."""

    id = models.CharField(max_length=64, primary_key=True)
    workflow = models.ForeignKey(
        Workflow,
        db_column="workflow_id",
        related_name="nodes",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )
    label = models.CharField(max_length=255)
    type = models.CharField(max_length=64, default="standard")
    node_type = models.CharField(max_length=50)
    position = models.JSONField(default=dict)
    data = models.JSONField(default=dict)
    measured = models.JSONField(default=dict)

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "workflow_node"
        verbose_name = "Workflow Node"
        verbose_name_plural = "Workflow Nodes"


class WorkflowEdge(TenantModel):
    """``workflow_edge`` — edge between two workflow nodes."""

    id = models.CharField(max_length=64, primary_key=True)
    workflow = models.ForeignKey(
        Workflow,
        db_column="workflow_id",
        related_name="edges",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )
    source = models.ForeignKey(
        WorkflowNode,
        db_column="source_id",
        related_name="outgoing_edges",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )
    target = models.ForeignKey(
        WorkflowNode,
        db_column="target_id",
        related_name="incoming_edges",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )
    source_handle = models.CharField(max_length=50, null=True, blank=True)
    is_deleted = models.BooleanField(default=False)

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "workflow_edge"
        verbose_name = "Workflow Edge"
        verbose_name_plural = "Workflow Edges"


class PathBuilder(TenantModel):
    """``path_builder`` — stage-based UI for an object's lifecycle."""

    id = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    label = models.CharField(max_length=255, null=True, blank=True)
    object = models.ForeignKey(
        PlatformObject,
        db_column="object_id",
        related_name="paths",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )
    field = models.ForeignKey(
        Field,
        db_column="field_id",
        related_name="paths",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )
    stages = models.JSONField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    owner_id = models.CharField(max_length=64, null=True, blank=True)
    organisation_id = models.CharField(max_length=64, null=True, blank=True)
    deleted_by_id = models.CharField(max_length=255, null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)
    deleted_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "path_builder"
        verbose_name = "Path Builder"
        verbose_name_plural = "Path Builders"


class EmailTemplate(TenantModel):
    """``email_templates`` — referenced by send-email workflow nodes
    and the standalone email-send view.

    Note: the ``id`` column uses TEXT not VARCHAR(64) — older rows have
    ``'TPL-' || gen_random_uuid()`` (~40 chars), so the model uses TextField.
    """

    id = models.TextField(primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(null=True, blank=True)
    available_for_use = models.BooleanField(default=True)
    template_type = models.CharField(max_length=10, default="text")
    subject = models.CharField(max_length=255)
    body = models.TextField()
    selected_object = models.ForeignKey(
        PlatformObject,
        db_column="selected_object",
        related_name="email_templates",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )
    record_id = models.CharField(max_length=255, null=True, blank=True)
    sendgrid_template_id = models.CharField(max_length=255, null=True, blank=True)
    sendgrid_template_hash = models.CharField(max_length=64, null=True, blank=True)

    author_id = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "email_templates"
        verbose_name = "Email Template"
        verbose_name_plural = "Email Templates"
