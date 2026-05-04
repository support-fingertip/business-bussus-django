"""Phase 3 Wave 4 — reporting models.

Tables modeled here:
  report                    — Report (saved query/aggregation)
  report_folder             — ReportFolder
  report_folder_sharing     — ReportFolderSharing
  dashboard                 — Dashboard
  dashboard_component       — DashboardComponent (a chart/widget)
  dashboard_folders         — DashboardFolder (note: plural in DDL)
  dashboard_folder_sharing  — DashboardFolderSharing
  dashboard_assignment      — DashboardAssignment

All models managed=False; FKs db_constraint=False. See ADR-0003.
"""

from __future__ import annotations

from django.db import models

from api.tenant_models._base import TenantModel


class ReportFolder(TenantModel):
    """``report_folder`` — folder for organising reports."""

    id = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(null=True, blank=True)
    visibility = models.CharField(max_length=20, default="private")
    parent = models.ForeignKey(
        "self",
        db_column="parent_id",
        related_name="children",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    owner_id = models.CharField(max_length=64, null=True, blank=True)
    deleted_by_id = models.CharField(max_length=255, null=True, blank=True)
    organisation_id = models.CharField(max_length=64, null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)
    deleted_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "report_folder"
        verbose_name = "Report Folder"
        verbose_name_plural = "Report Folders"


class Report(TenantModel):
    """``report`` — saved report definition."""

    id = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255)
    report_type = models.CharField(max_length=500, null=True, blank=True)
    fields = models.JSONField(null=True, blank=True)
    filters = models.JSONField(null=True, blank=True)
    filter_logic = models.TextField(null=True, blank=True)
    filter_json = models.JSONField(null=True, blank=True)
    group_by = models.JSONField(null=True, blank=True)
    table_name = models.TextField(null=True, blank=True)

    folder = models.ForeignKey(
        ReportFolder,
        db_column="folder_id",
        related_name="reports",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )
    created_by_id = models.TextField(null=True, blank=True)

    show_row_counts = models.BooleanField(default=True)
    show_detail_rows = models.BooleanField(default=True)
    show_subtotals = models.BooleanField(default=True)
    show_grand_total = models.BooleanField(default=True)
    is_deleted = models.BooleanField(default=False)

    deleted_by_id = models.CharField(max_length=255, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)
    deleted_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "report"
        verbose_name = "Report"
        verbose_name_plural = "Reports"


class ReportFolderSharing(TenantModel):
    """``report_folder_sharing`` — per-folder share grants."""

    id = models.CharField(max_length=64, primary_key=True)
    folder_id = models.CharField(max_length=64, null=True, blank=True)
    shared_with_id = models.CharField(max_length=64, null=True, blank=True)
    shared_with_type = models.CharField(max_length=32, null=True, blank=True)
    access_level = models.CharField(max_length=32, null=True, blank=True)

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "report_folder_sharing"
        verbose_name = "Report Folder Sharing"
        verbose_name_plural = "Report Folder Sharings"


class DashboardFolder(TenantModel):
    """``dashboard_folders`` — folder for dashboards (note: DDL is plural)."""

    id = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255)
    label = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    parent = models.ForeignKey(
        "self",
        db_column="parent_id",
        related_name="children",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )

    created_by_id = models.CharField(max_length=255, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=255, null=True, blank=True)
    owner_id = models.CharField(max_length=255, null=True, blank=True)
    deleted_by_id = models.CharField(max_length=255, null=True, blank=True)
    organisation = models.CharField(max_length=225, null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)
    deleted_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "dashboard_folders"
        verbose_name = "Dashboard Folder"
        verbose_name_plural = "Dashboard Folders"


class Dashboard(TenantModel):
    """``dashboard`` — saved dashboard definition."""

    id = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    description = models.CharField(max_length=256, null=True, blank=True)
    components = models.JSONField(null=True, blank=True)
    folder_name = models.CharField(max_length=255, null=True, blank=True)
    running_user = models.CharField(max_length=255, null=True, blank=True)
    dashboard_type = models.CharField(max_length=100, null=True, blank=True)
    grid_layout = models.JSONField(null=True, blank=True)
    refresh_frequency = models.CharField(max_length=100, null=True, blank=True)
    layout = models.JSONField(null=True, blank=True)

    folder = models.ForeignKey(
        DashboardFolder,
        db_column="folder_id",
        related_name="dashboards",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )
    created_by = models.CharField(max_length=255, null=True, blank=True)
    last_modified_by = models.CharField(max_length=255, null=True, blank=True)
    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    deleted_by_id = models.CharField(max_length=255, null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)
    deleted_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "dashboard"
        verbose_name = "Dashboard"
        verbose_name_plural = "Dashboards"


class DashboardComponent(TenantModel):
    """``dashboard_component`` — chart/widget on a dashboard."""

    id = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    type = models.CharField(max_length=50)
    data_source = models.CharField(max_length=255, null=True, blank=True)
    filters = models.JSONField(null=True, blank=True)
    metric_config = models.JSONField(null=True, blank=True)
    chart_config = models.JSONField(null=True, blank=True)
    geometry = models.JSONField(null=True, blank=True)
    chart_data = models.JSONField(null=True, blank=True)
    filter_logic = models.TextField(null=True, blank=True)
    widget_settings = models.JSONField(null=True, blank=True)

    dashboard = models.ForeignKey(
        Dashboard,
        db_column="dashboard_id",
        related_name="dashboard_components",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )
    report = models.ForeignKey(
        Report,
        db_column="report_id",
        related_name="dashboard_components",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )
    listview_id = models.CharField(max_length=64, null=True, blank=True)

    created_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "dashboard_component"
        verbose_name = "Dashboard Component"
        verbose_name_plural = "Dashboard Components"


class DashboardFolderSharing(TenantModel):
    """``dashboard_folder_sharing`` — per-folder share grants."""

    id = models.CharField(max_length=64, primary_key=True)
    folder_id = models.CharField(max_length=64, null=True, blank=True)
    shared_with_id = models.CharField(max_length=64, null=True, blank=True)
    shared_with_type = models.CharField(max_length=32, null=True, blank=True)
    access_level = models.CharField(max_length=32, null=True, blank=True)

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "dashboard_folder_sharing"
        verbose_name = "Dashboard Folder Sharing"
        verbose_name_plural = "Dashboard Folder Sharings"


class DashboardAssignment(TenantModel):
    """``dashboard_assignment`` — per-(dashboard, target) visibility."""

    id = models.CharField(max_length=64, primary_key=True)
    dashboard_id = models.CharField(max_length=64, null=True, blank=True)
    target_id = models.CharField(max_length=64, null=True, blank=True)
    target_type = models.CharField(max_length=32, null=True, blank=True)

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "dashboard_assignment"
        verbose_name = "Dashboard Assignment"
        verbose_name_plural = "Dashboard Assignments"
