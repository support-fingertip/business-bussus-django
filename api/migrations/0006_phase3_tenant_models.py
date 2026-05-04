"""Phase 3 — register Wave 3-5 tenant-scoped models in Django state.

Same pattern as 0005: ``managed = False`` + ``SeparateDatabaseAndState``
with empty ``database_operations``. Tables already exist per-tenant
from default_tables.sql; Django doesn't run DDL.

Adds 25 models:

  Wave 2 follow-up (originally missed):
    UserGroupProfile, UserGroupPublicGroup

  Wave 3 — UI / layout (10):
    App, PageLayout, SearchLayout, Listview, PageBuilder,
    PageComponent, PageBuilderAssignment, LayoutAssignment,
    HomepageAssignment, FieldMapping

  Wave 4 — reporting (8):
    Report, ReportFolder, ReportFolderSharing, Dashboard,
    DashboardComponent, DashboardFolder, DashboardFolderSharing,
    DashboardAssignment

  Wave 5 — workflow (5):
    Workflow, WorkflowNode, WorkflowEdge, PathBuilder, EmailTemplate

See ``docs/PHASE3_OPERATOR_NOTES.md`` for the rollout plan.
"""

from __future__ import annotations

from django.db import migrations, models


def _fk(*, db_column: str, related_name: str | None, to: str,
        null: bool = False, blank: bool = False):
    """All Phase 2/3 tenant-model FKs share these defaults."""
    kwargs = {
        "db_column": db_column,
        "db_constraint": False,
        "on_delete": models.deletion.DO_NOTHING,
        "to": to,
    }
    if related_name is not None:
        kwargs["related_name"] = related_name
    if null:
        kwargs["null"] = True
    if blank:
        kwargs["blank"] = True
    return models.ForeignKey(**kwargs)


def _id_field():
    return models.CharField(max_length=64, primary_key=True, serialize=False)


def _audit_fields():
    """The audit columns that appear on most tenant tables."""
    return [
        ("created_by_id", models.CharField(blank=True, max_length=64, null=True)),
        ("last_modified_by_id", models.CharField(blank=True, max_length=64, null=True)),
        ("created_date", models.DateTimeField(blank=True, null=True)),
        ("last_modified_date", models.DateTimeField(blank=True, null=True)),
    ]


_STATE_OPERATIONS = [
    # ---------------- Wave 2 follow-up ----------------
    migrations.CreateModel(
        name="UserGroupProfile",
        fields=[
            ("id", _id_field()),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("user_group", _fk(db_column="user_group_id",
                               related_name="profile_assignments",
                               to="api.usergroup")),
            ("profile", _fk(db_column="profile_id",
                            related_name="user_group_assignments",
                            to="api.profile")),
        ],
        options={
            "verbose_name": "User Group Profile",
            "verbose_name_plural": "User Group Profiles",
            "db_table": "user_group_profiles",
            "managed": False,
            "unique_together": {("user_group", "profile")},
        },
    ),
    migrations.CreateModel(
        name="UserGroupPublicGroup",
        fields=[
            ("id", _id_field()),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("user_group", _fk(db_column="user_group_id",
                               related_name="public_group_memberships",
                               to="api.usergroup")),
            ("public_group", _fk(db_column="public_group_id",
                                 related_name="parent_groups",
                                 to="api.usergroup")),
        ],
        options={
            "verbose_name": "User Group Public Group",
            "verbose_name_plural": "User Group Public Groups",
            "db_table": "user_group_public_groups",
            "managed": False,
            "unique_together": {("user_group", "public_group")},
        },
    ),

    # ---------------- Wave 3 — UI / layout ----------------
    migrations.CreateModel(
        name="App",
        fields=[
            ("id", _id_field()),
            ("name", models.CharField(max_length=255, unique=True)),
            ("label", models.CharField(default="Unknown", max_length=256)),
            ("description", models.CharField(blank=True, max_length=1024, null=True)),
            ("tabs", models.JSONField(blank=True, null=True)),
            ("developer", models.CharField(blank=True, max_length=255, null=True)),
            ("setup_experiance", models.CharField(blank=True, max_length=255, null=True)),
            ("navigation_style", models.CharField(blank=True, max_length=255, null=True)),
            ("form_factor", models.CharField(blank=True, max_length=255, null=True)),
            ("color", models.CharField(blank=True, max_length=7, null=True)),
            ("image", models.CharField(blank=True, max_length=1023, null=True)),
            ("logo", models.CharField(blank=True, max_length=2048, null=True)),
            ("utility_bar", models.TextField(blank=True, null=True)),
            ("default_landing_tab", models.CharField(blank=True, max_length=255, null=True)),
            ("organisation", models.CharField(blank=True, max_length=225, null=True)),
            ("organisation_id", models.CharField(blank=True, max_length=64, null=True)),
            ("disable_end_user_personalisation", models.BooleanField(default=False)),
            ("disable_temporary_tabs", models.BooleanField(default=False)),
            ("use_app_image_color_for_org_theme", models.BooleanField(default=False)),
            ("use_omni_channel_sidebar", models.BooleanField(default=False)),
            ("is_deleted", models.BooleanField(default=False)),
            ("owner_id", models.CharField(blank=True, max_length=64, null=True)),
            ("deleted_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("deleted_date", models.DateTimeField(blank=True, null=True)),
            *_audit_fields(),
        ],
        options={
            "verbose_name": "App",
            "verbose_name_plural": "Apps",
            "db_table": "app",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="PageLayout",
        fields=[
            ("id", _id_field()),
            ("object_name", models.CharField(max_length=255)),
            ("name", models.CharField(max_length=255)),
            ("label", models.CharField(max_length=255)),
            ("sections", models.JSONField()),
            ("layout", models.JSONField(blank=True, null=True)),
            ("buttons", models.JSONField(blank=True, null=True)),
            ("related_lists", models.JSONField(blank=True, null=True)),
            ("created_by", models.CharField(blank=True, max_length=255, null=True)),
            ("last_modified_by", models.CharField(blank=True, max_length=255, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
            ("object", _fk(db_column="object_id",
                           related_name="page_layouts",
                           to="api.platformobject", null=True, blank=True)),
        ],
        options={
            "verbose_name": "Page Layout",
            "verbose_name_plural": "Page Layouts",
            "db_table": "page_layouts",
            "managed": False,
            "unique_together": {("name", "object_name")},
        },
    ),
    migrations.CreateModel(
        name="SearchLayout",
        fields=[
            ("id", _id_field()),
            ("search_results_fields", models.JSONField(blank=True, null=True)),
            ("lookup_dialog_fields", models.JSONField(blank=True, null=True)),
            ("recent_items_fields", models.JSONField(blank=True, null=True)),
            ("owner_id", models.CharField(blank=True, max_length=255, null=True)),
            ("organisation", models.CharField(blank=True, max_length=225, null=True)),
            ("is_deleted", models.BooleanField(default=False)),
            ("created_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("last_modified_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
            ("object", _fk(db_column="object_id", related_name="search_layouts",
                           to="api.platformobject")),
        ],
        options={
            "verbose_name": "Search Layout",
            "verbose_name_plural": "Search Layouts",
            "db_table": "search_layouts",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="Listview",
        fields=[
            ("id", _id_field()),
            ("name", models.CharField(max_length=255)),
            ("label", models.CharField(max_length=255)),
            ("is_pinned", models.BooleanField(default=False)),
            ("filters", models.JSONField(blank=True, null=True)),
            ("filter_logic", models.CharField(blank=True, max_length=1024, null=True)),
            ("visible_columns", models.JSONField(blank=True, null=True)),
            ("owner_id", models.CharField(blank=True, max_length=255, null=True)),
            ("deleted_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("organisation", models.CharField(blank=True, max_length=225, null=True)),
            ("is_deleted", models.BooleanField(default=False)),
            ("created_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("last_modified_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
            ("deleted_date", models.DateTimeField(blank=True, null=True)),
            ("object", _fk(db_column="object_id", related_name="listviews",
                           to="api.platformobject")),
        ],
        options={
            "verbose_name": "Listview",
            "verbose_name_plural": "Listviews",
            "db_table": "listviews",
            "managed": False,
            "unique_together": {("name", "object")},
        },
    ),
    migrations.CreateModel(
        name="PageBuilder",
        fields=[
            ("id", _id_field()),
            ("name", models.CharField(max_length=255, unique=True)),
            ("description", models.CharField(blank=True, max_length=255, null=True)),
            ("folder_name", models.CharField(blank=True, max_length=255, null=True)),
            ("type", models.CharField(blank=True, max_length=100, null=True)),
            ("layout", models.JSONField(blank=True, null=True)),
            ("refresh_frequency", models.CharField(blank=True, max_length=100, null=True)),
            ("owner_id", models.CharField(blank=True, max_length=255, null=True)),
            ("deleted_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("organisation", models.CharField(blank=True, max_length=225, null=True)),
            ("is_deleted", models.BooleanField(default=False)),
            ("created_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("last_modified_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
            ("deleted_date", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Page Builder",
            "verbose_name_plural": "Page Builders",
            "db_table": "page_builder",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="PageComponent",
        fields=[
            ("id", _id_field()),
            ("name", models.CharField(max_length=255)),
            ("type", models.CharField(max_length=50)),
            ("data_source", models.CharField(blank=True, max_length=255, null=True)),
            ("listview_id", models.CharField(blank=True, max_length=255, null=True)),
            ("dashboard_component_id", models.CharField(blank=True, max_length=64, null=True)),
            ("filters", models.JSONField(blank=True, null=True)),
            ("metric_config", models.JSONField(blank=True, null=True)),
            ("chart_config", models.JSONField(blank=True, null=True)),
            ("geometry", models.JSONField(blank=True, null=True)),
            ("owner_id", models.CharField(blank=True, max_length=255, null=True)),
            ("deleted_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("organisation", models.CharField(blank=True, max_length=225, null=True)),
            ("is_deleted", models.BooleanField(default=False)),
            ("created_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("last_modified_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
            ("deleted_date", models.DateTimeField(blank=True, null=True)),
            ("page_builder", _fk(db_column="page_builder_id",
                                 related_name="components",
                                 to="api.pagebuilder", null=True, blank=True)),
        ],
        options={
            "verbose_name": "Page Component",
            "verbose_name_plural": "Page Components",
            "db_table": "page_component",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="PageBuilderAssignment",
        fields=[
            ("id", _id_field()),
            *_audit_fields(),
            ("profile", _fk(db_column="profile_id", related_name="+",
                            to="api.profile")),
            ("page_builder", _fk(db_column="page_builder_id",
                                 related_name="assignments",
                                 to="api.pagebuilder")),
        ],
        options={
            "verbose_name": "Page Builder Assignment",
            "verbose_name_plural": "Page Builder Assignments",
            "db_table": "page_builder_assignment",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="LayoutAssignment",
        fields=[
            ("id", _id_field()),
            ("record_type", models.TextField(default="default")),
            *_audit_fields(),
            ("profile", _fk(db_column="profile_id", related_name="+",
                            to="api.profile")),
            ("object", _fk(db_column="object_id",
                           related_name="layout_assignments",
                           to="api.platformobject")),
            ("page_layout", _fk(db_column="page_layouts_id",
                                related_name="assignments",
                                to="api.pagelayout")),
        ],
        options={
            "verbose_name": "Layout Assignment",
            "verbose_name_plural": "Layout Assignments",
            "db_table": "layout_assignment",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="HomepageAssignment",
        fields=[
            ("id", _id_field()),
            ("profile_id", models.CharField(blank=True, max_length=64, null=True)),
            ("page_builder_id", models.CharField(blank=True, max_length=64, null=True)),
            *_audit_fields(),
        ],
        options={
            "verbose_name": "Homepage Assignment",
            "verbose_name_plural": "Homepage Assignments",
            "db_table": "homepage_assignment",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="FieldMapping",
        fields=[
            ("id", _id_field()),
            ("mapped_fields", models.JSONField(default=dict)),
            *_audit_fields(),
            ("object", _fk(db_column="object_id",
                           related_name="field_mappings_from",
                           to="api.platformobject", null=True, blank=True)),
            ("mapped_with", _fk(db_column="mapped_with",
                                related_name="field_mappings_to",
                                to="api.platformobject", null=True, blank=True)),
        ],
        options={
            "verbose_name": "Field Mapping",
            "verbose_name_plural": "Field Mappings",
            "db_table": "field_mapping",
            "managed": False,
        },
    ),

    # ---------------- Wave 4 — reporting ----------------
    migrations.CreateModel(
        name="ReportFolder",
        fields=[
            ("id", _id_field()),
            ("name", models.CharField(max_length=255, unique=True)),
            ("description", models.TextField(blank=True, null=True)),
            ("visibility", models.CharField(default="private", max_length=20)),
            ("owner_id", models.CharField(blank=True, max_length=64, null=True)),
            ("deleted_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("organisation_id", models.CharField(blank=True, max_length=64, null=True)),
            ("is_deleted", models.BooleanField(default=False)),
            ("deleted_date", models.DateTimeField(blank=True, null=True)),
            *_audit_fields(),
            ("parent", _fk(db_column="parent_id", related_name="children",
                           to="api.reportfolder", null=True, blank=True)),
        ],
        options={
            "verbose_name": "Report Folder",
            "verbose_name_plural": "Report Folders",
            "db_table": "report_folder",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="Report",
        fields=[
            ("id", _id_field()),
            ("name", models.CharField(max_length=255)),
            ("report_type", models.CharField(blank=True, max_length=500, null=True)),
            ("fields", models.JSONField(blank=True, null=True)),
            ("filters", models.JSONField(blank=True, null=True)),
            ("filter_logic", models.TextField(blank=True, null=True)),
            ("filter_json", models.JSONField(blank=True, null=True)),
            ("group_by", models.JSONField(blank=True, null=True)),
            ("table_name", models.TextField(blank=True, null=True)),
            ("created_by_id", models.TextField(blank=True, null=True)),
            ("show_row_counts", models.BooleanField(default=True)),
            ("show_detail_rows", models.BooleanField(default=True)),
            ("show_subtotals", models.BooleanField(default=True)),
            ("show_grand_total", models.BooleanField(default=True)),
            ("is_deleted", models.BooleanField(default=False)),
            ("deleted_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
            ("deleted_date", models.DateTimeField(blank=True, null=True)),
            ("folder", _fk(db_column="folder_id", related_name="reports",
                           to="api.reportfolder", null=True, blank=True)),
        ],
        options={
            "verbose_name": "Report",
            "verbose_name_plural": "Reports",
            "db_table": "report",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="ReportFolderSharing",
        fields=[
            ("id", _id_field()),
            ("folder_id", models.CharField(blank=True, max_length=64, null=True)),
            ("shared_with_id", models.CharField(blank=True, max_length=64, null=True)),
            ("shared_with_type", models.CharField(blank=True, max_length=32, null=True)),
            ("access_level", models.CharField(blank=True, max_length=32, null=True)),
            ("created_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Report Folder Sharing",
            "verbose_name_plural": "Report Folder Sharings",
            "db_table": "report_folder_sharing",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="DashboardFolder",
        fields=[
            ("id", _id_field()),
            ("name", models.CharField(max_length=255)),
            ("label", models.CharField(max_length=255)),
            ("description", models.TextField(blank=True, null=True)),
            ("owner_id", models.CharField(blank=True, max_length=255, null=True)),
            ("deleted_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("organisation", models.CharField(blank=True, max_length=225, null=True)),
            ("is_deleted", models.BooleanField(default=False)),
            ("created_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("last_modified_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
            ("deleted_date", models.DateTimeField(blank=True, null=True)),
            ("parent", _fk(db_column="parent_id", related_name="children",
                           to="api.dashboardfolder", null=True, blank=True)),
        ],
        options={
            "verbose_name": "Dashboard Folder",
            "verbose_name_plural": "Dashboard Folders",
            "db_table": "dashboard_folders",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="Dashboard",
        fields=[
            ("id", _id_field()),
            ("name", models.CharField(max_length=255, unique=True)),
            ("description", models.CharField(blank=True, max_length=256, null=True)),
            ("components", models.JSONField(blank=True, null=True)),
            ("folder_name", models.CharField(blank=True, max_length=255, null=True)),
            ("running_user", models.CharField(blank=True, max_length=255, null=True)),
            ("dashboard_type", models.CharField(blank=True, max_length=100, null=True)),
            ("grid_layout", models.JSONField(blank=True, null=True)),
            ("refresh_frequency", models.CharField(blank=True, max_length=100, null=True)),
            ("layout", models.JSONField(blank=True, null=True)),
            ("created_by", models.CharField(blank=True, max_length=255, null=True)),
            ("last_modified_by", models.CharField(blank=True, max_length=255, null=True)),
            ("created_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("deleted_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("is_deleted", models.BooleanField(default=False)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("last_modified_date", models.DateTimeField(blank=True, null=True)),
            ("deleted_date", models.DateTimeField(blank=True, null=True)),
            ("folder", _fk(db_column="folder_id", related_name="dashboards",
                           to="api.dashboardfolder", null=True, blank=True)),
        ],
        options={
            "verbose_name": "Dashboard",
            "verbose_name_plural": "Dashboards",
            "db_table": "dashboard",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="DashboardComponent",
        fields=[
            ("id", _id_field()),
            ("name", models.CharField(max_length=255, unique=True)),
            ("type", models.CharField(max_length=50)),
            ("data_source", models.CharField(blank=True, max_length=255, null=True)),
            ("filters", models.JSONField(blank=True, null=True)),
            ("metric_config", models.JSONField(blank=True, null=True)),
            ("chart_config", models.JSONField(blank=True, null=True)),
            ("geometry", models.JSONField(blank=True, null=True)),
            ("chart_data", models.JSONField(blank=True, null=True)),
            ("filter_logic", models.TextField(blank=True, null=True)),
            ("widget_settings", models.JSONField(blank=True, null=True)),
            ("listview_id", models.CharField(blank=True, max_length=64, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("dashboard", _fk(db_column="dashboard_id",
                              related_name="dashboard_components",
                              to="api.dashboard", null=True, blank=True)),
            ("report", _fk(db_column="report_id",
                           related_name="dashboard_components",
                           to="api.report", null=True, blank=True)),
        ],
        options={
            "verbose_name": "Dashboard Component",
            "verbose_name_plural": "Dashboard Components",
            "db_table": "dashboard_component",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="DashboardFolderSharing",
        fields=[
            ("id", _id_field()),
            ("folder_id", models.CharField(blank=True, max_length=64, null=True)),
            ("shared_with_id", models.CharField(blank=True, max_length=64, null=True)),
            ("shared_with_type", models.CharField(blank=True, max_length=32, null=True)),
            ("access_level", models.CharField(blank=True, max_length=32, null=True)),
            ("created_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Dashboard Folder Sharing",
            "verbose_name_plural": "Dashboard Folder Sharings",
            "db_table": "dashboard_folder_sharing",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="DashboardAssignment",
        fields=[
            ("id", _id_field()),
            ("dashboard_id", models.CharField(blank=True, max_length=64, null=True)),
            ("target_id", models.CharField(blank=True, max_length=64, null=True)),
            ("target_type", models.CharField(blank=True, max_length=32, null=True)),
            ("created_by_id", models.CharField(blank=True, max_length=64, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
        ],
        options={
            "verbose_name": "Dashboard Assignment",
            "verbose_name_plural": "Dashboard Assignments",
            "db_table": "dashboard_assignment",
            "managed": False,
        },
    ),

    # ---------------- Wave 5 — workflow ----------------
    migrations.CreateModel(
        name="Workflow",
        fields=[
            ("id", _id_field()),
            ("name", models.CharField(max_length=255)),
            ("trigger_type", models.CharField(default="create", max_length=20)),
            ("module_name", models.CharField(blank=True, max_length=100, null=True)),
            ("description", models.TextField(blank=True, null=True)),
            *_audit_fields(),
        ],
        options={
            "verbose_name": "Workflow",
            "verbose_name_plural": "Workflows",
            "db_table": "workflow",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="WorkflowNode",
        fields=[
            ("id", _id_field()),
            ("label", models.CharField(max_length=255)),
            ("type", models.CharField(default="standard", max_length=64)),
            ("node_type", models.CharField(max_length=50)),
            ("position", models.JSONField(default=dict)),
            ("data", models.JSONField(default=dict)),
            ("measured", models.JSONField(default=dict)),
            *_audit_fields(),
            ("workflow", _fk(db_column="workflow_id", related_name="nodes",
                             to="api.workflow", null=True, blank=True)),
        ],
        options={
            "verbose_name": "Workflow Node",
            "verbose_name_plural": "Workflow Nodes",
            "db_table": "workflow_node",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="WorkflowEdge",
        fields=[
            ("id", _id_field()),
            ("source_handle", models.CharField(blank=True, max_length=50, null=True)),
            ("is_deleted", models.BooleanField(default=False)),
            *_audit_fields(),
            ("workflow", _fk(db_column="workflow_id", related_name="edges",
                             to="api.workflow", null=True, blank=True)),
            ("source", _fk(db_column="source_id",
                           related_name="outgoing_edges",
                           to="api.workflownode", null=True, blank=True)),
            ("target", _fk(db_column="target_id",
                           related_name="incoming_edges",
                           to="api.workflownode", null=True, blank=True)),
        ],
        options={
            "verbose_name": "Workflow Edge",
            "verbose_name_plural": "Workflow Edges",
            "db_table": "workflow_edge",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="PathBuilder",
        fields=[
            ("id", _id_field()),
            ("name", models.CharField(max_length=255, unique=True)),
            ("label", models.CharField(blank=True, max_length=255, null=True)),
            ("stages", models.JSONField(blank=True, null=True)),
            ("is_active", models.BooleanField(default=True)),
            ("owner_id", models.CharField(blank=True, max_length=64, null=True)),
            ("organisation_id", models.CharField(blank=True, max_length=64, null=True)),
            ("deleted_by_id", models.CharField(blank=True, max_length=255, null=True)),
            ("is_deleted", models.BooleanField(default=False)),
            ("deleted_date", models.DateTimeField(blank=True, null=True)),
            *_audit_fields(),
            ("object", _fk(db_column="object_id", related_name="paths",
                           to="api.platformobject", null=True, blank=True)),
            ("field", _fk(db_column="field_id", related_name="paths",
                          to="api.field", null=True, blank=True)),
        ],
        options={
            "verbose_name": "Path Builder",
            "verbose_name_plural": "Path Builders",
            "db_table": "path_builder",
            "managed": False,
        },
    ),
    migrations.CreateModel(
        name="EmailTemplate",
        fields=[
            ("id", models.TextField(primary_key=True, serialize=False)),
            ("name", models.CharField(max_length=255, unique=True)),
            ("description", models.TextField(blank=True, null=True)),
            ("available_for_use", models.BooleanField(default=True)),
            ("template_type", models.CharField(default="text", max_length=10)),
            ("subject", models.CharField(max_length=255)),
            ("body", models.TextField()),
            ("record_id", models.CharField(blank=True, max_length=255, null=True)),
            ("sendgrid_template_id", models.CharField(blank=True, max_length=255, null=True)),
            ("sendgrid_template_hash", models.CharField(blank=True, max_length=64, null=True)),
            ("author_id", models.TextField(blank=True, null=True)),
            ("created_at", models.DateTimeField(blank=True, null=True)),
            ("updated_at", models.DateTimeField(blank=True, null=True)),
            ("created_date", models.DateTimeField(blank=True, null=True)),
            ("selected_object", _fk(db_column="selected_object",
                                    related_name="email_templates",
                                    to="api.platformobject", null=True, blank=True)),
        ],
        options={
            "verbose_name": "Email Template",
            "verbose_name_plural": "Email Templates",
            "db_table": "email_templates",
            "managed": False,
        },
    ),
]


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0005_phase2_tenant_models"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=_STATE_OPERATIONS,
        ),
    ]
