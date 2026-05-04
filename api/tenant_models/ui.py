"""Phase 3 Wave 3 — UI / layout / navigation models.

Tables modeled here:
  app                    — App (per-tenant app definition)
  page_layouts           — PageLayout
  search_layouts         — SearchLayout
  listviews              — Listview
  page_builder           — PageBuilder
  page_component         — PageComponent
  page_builder_assignment — PageBuilderAssignment (junction)
  layout_assignment       — LayoutAssignment (junction)
  homepage_assignment     — HomepageAssignment
  field_mapping           — FieldMapping (object→object field map)

All models are managed=False (Django doesn't own the per-tenant DDL),
all FKs use db_constraint=False (legacy DDL drift across tenants).
See ADR-0003 for the rationale.
"""

from __future__ import annotations

from django.db import models

from api.tenant_models._base import TenantModel
from api.tenant_models.authz import Profile
from api.tenant_models.objects import PlatformObject


class App(TenantModel):
    """``app`` — per-tenant application (collection of tabs)."""

    id = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    label = models.CharField(max_length=256, default="Unknown")
    description = models.CharField(max_length=1024, null=True, blank=True)
    tabs = models.JSONField(null=True, blank=True)
    developer = models.CharField(max_length=255, null=True, blank=True)
    setup_experiance = models.CharField(max_length=255, null=True, blank=True)
    navigation_style = models.CharField(max_length=255, null=True, blank=True)
    form_factor = models.CharField(max_length=255, null=True, blank=True)
    color = models.CharField(max_length=7, null=True, blank=True)
    image = models.CharField(max_length=1023, null=True, blank=True)
    logo = models.CharField(max_length=2048, null=True, blank=True)
    utility_bar = models.TextField(null=True, blank=True)
    default_landing_tab = models.CharField(max_length=255, null=True, blank=True)
    organisation = models.CharField(max_length=225, null=True, blank=True)
    organisation_id = models.CharField(max_length=64, null=True, blank=True)

    disable_end_user_personalisation = models.BooleanField(default=False)
    disable_temporary_tabs = models.BooleanField(default=False)
    use_app_image_color_for_org_theme = models.BooleanField(default=False)
    use_omni_channel_sidebar = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    owner_id = models.CharField(max_length=64, null=True, blank=True)
    deleted_by_id = models.CharField(max_length=255, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)
    deleted_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "app"
        verbose_name = "App"
        verbose_name_plural = "Apps"

    def __str__(self) -> str:
        return self.name


class PageLayout(TenantModel):
    """``page_layouts`` — record-detail page layout per object."""

    id = models.CharField(max_length=64, primary_key=True)
    object_name = models.CharField(max_length=255)
    object = models.ForeignKey(
        PlatformObject,
        db_column="object_id",
        related_name="page_layouts",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )
    name = models.CharField(max_length=255)
    label = models.CharField(max_length=255)
    sections = models.JSONField()
    layout = models.JSONField(null=True, blank=True)
    buttons = models.JSONField(null=True, blank=True)
    related_lists = models.JSONField(null=True, blank=True)

    created_by = models.CharField(max_length=255, null=True, blank=True)
    last_modified_by = models.CharField(max_length=255, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "page_layouts"
        verbose_name = "Page Layout"
        verbose_name_plural = "Page Layouts"
        unique_together = (("name", "object_name"),)


class SearchLayout(TenantModel):
    """``search_layouts`` — per-object search-result column lists."""

    id = models.CharField(max_length=64, primary_key=True)
    object = models.ForeignKey(
        PlatformObject,
        db_column="object_id",
        related_name="search_layouts",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    search_results_fields = models.JSONField(null=True, blank=True)
    lookup_dialog_fields = models.JSONField(null=True, blank=True)
    recent_items_fields = models.JSONField(null=True, blank=True)

    created_by_id = models.CharField(max_length=255, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=255, null=True, blank=True)
    owner_id = models.CharField(max_length=255, null=True, blank=True)
    organisation = models.CharField(max_length=225, null=True, blank=True)
    is_deleted = models.BooleanField(default=False)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "search_layouts"
        verbose_name = "Search Layout"
        verbose_name_plural = "Search Layouts"


class Listview(TenantModel):
    """``listviews`` — per-object saved list view (filters + visible cols)."""

    id = models.CharField(max_length=64, primary_key=True)
    object = models.ForeignKey(
        PlatformObject,
        db_column="object_id",
        related_name="listviews",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    name = models.CharField(max_length=255)
    label = models.CharField(max_length=255)
    is_pinned = models.BooleanField(default=False)
    filters = models.JSONField(null=True, blank=True)
    filter_logic = models.CharField(max_length=1024, null=True, blank=True)
    visible_columns = models.JSONField(null=True, blank=True)

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
        db_table = "listviews"
        verbose_name = "Listview"
        verbose_name_plural = "Listviews"
        unique_together = (("name", "object"),)


class PageBuilder(TenantModel):
    """``page_builder`` — Lightning-style customizable page definition."""

    id = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255, unique=True)
    description = models.CharField(max_length=255, null=True, blank=True)
    folder_name = models.CharField(max_length=255, null=True, blank=True)
    type = models.CharField(max_length=100, null=True, blank=True)
    layout = models.JSONField(null=True, blank=True)
    refresh_frequency = models.CharField(max_length=100, null=True, blank=True)

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
        db_table = "page_builder"
        verbose_name = "Page Builder"
        verbose_name_plural = "Page Builders"


class PageComponent(TenantModel):
    """``page_component`` — widget on a page-builder page."""

    id = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=50)
    data_source = models.CharField(max_length=255, null=True, blank=True)
    listview_id = models.CharField(max_length=255, null=True, blank=True)
    page_builder = models.ForeignKey(
        PageBuilder,
        db_column="page_builder_id",
        related_name="components",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )
    dashboard_component_id = models.CharField(max_length=64, null=True, blank=True)
    filters = models.JSONField(null=True, blank=True)
    metric_config = models.JSONField(null=True, blank=True)
    chart_config = models.JSONField(null=True, blank=True)
    geometry = models.JSONField(null=True, blank=True)

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
        db_table = "page_component"
        verbose_name = "Page Component"
        verbose_name_plural = "Page Components"


class PageBuilderAssignment(TenantModel):
    """``page_builder_assignment`` — junction (page_builder ↔ profile)."""

    id = models.CharField(max_length=64, primary_key=True)
    profile = models.ForeignKey(
        Profile,
        db_column="profile_id",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    page_builder = models.ForeignKey(
        PageBuilder,
        db_column="page_builder_id",
        related_name="assignments",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "page_builder_assignment"
        verbose_name = "Page Builder Assignment"
        verbose_name_plural = "Page Builder Assignments"


class LayoutAssignment(TenantModel):
    """``layout_assignment`` — junction (page_layout ↔ profile ↔ object)."""

    id = models.CharField(max_length=64, primary_key=True)
    profile = models.ForeignKey(
        Profile,
        db_column="profile_id",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    object = models.ForeignKey(
        PlatformObject,
        db_column="object_id",
        related_name="layout_assignments",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    page_layout = models.ForeignKey(
        PageLayout,
        db_column="page_layouts_id",
        related_name="assignments",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    record_type = models.TextField(default="default")

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "layout_assignment"
        verbose_name = "Layout Assignment"
        verbose_name_plural = "Layout Assignments"


class HomepageAssignment(TenantModel):
    """``homepage_assignment`` — which page_builder is a profile's home."""

    id = models.CharField(max_length=64, primary_key=True)
    profile_id = models.CharField(max_length=64, null=True, blank=True)
    page_builder_id = models.CharField(max_length=64, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)
    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "homepage_assignment"
        verbose_name = "Homepage Assignment"
        verbose_name_plural = "Homepage Assignments"


class FieldMapping(TenantModel):
    """``field_mapping`` — declared field map between two objects."""

    id = models.CharField(max_length=64, primary_key=True)
    object = models.ForeignKey(
        PlatformObject,
        db_column="object_id",
        related_name="field_mappings_from",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )
    mapped_with = models.ForeignKey(
        PlatformObject,
        db_column="mapped_with",
        related_name="field_mappings_to",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        null=True, blank=True,
    )
    mapped_fields = models.JSONField(default=dict)

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "field_mapping"
        verbose_name = "Field Mapping"
        verbose_name_plural = "Field Mappings"
