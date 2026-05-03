"""``object`` and ``fields`` — the platform metadata that drives every
custom-business-object table.

Note: ``Object`` is a Python builtin, so the Python class is named
``PlatformObject`` while the underlying table stays ``object``.
"""

from __future__ import annotations

from django.db import models

from api.tenant_models._base import TenantModel


class PlatformObject(TenantModel):
    """``object`` registry — one row per setup or business-object table."""

    id = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=63, unique=True)
    label = models.CharField(max_length=255, null=True, blank=True)
    plural_label = models.CharField(max_length=255, null=True, blank=True)
    record_name = models.CharField(max_length=255, null=True, blank=True)
    description = models.TextField(null=True, blank=True)

    # Object-level flags (stored as text 'True'/'False' in legacy data,
    # but new rows use proper booleans). Use NullBooleanField semantics
    # via BooleanField(null=True) so we can read both.
    allow_activities = models.BooleanField(null=True)
    allow_bulk_api_access = models.BooleanField(null=True)
    allow_in_chatter_groups = models.BooleanField(null=True)
    allow_reports = models.BooleanField(null=True)
    allow_sharing = models.BooleanField(null=True)
    allow_streaming_api_access = models.BooleanField(null=True)
    enable_licensing = models.BooleanField(null=True)
    show_tab = models.BooleanField(null=True)
    starts_with_vowel_sound = models.BooleanField(null=True)
    track_field_history = models.BooleanField(null=True)

    datatype = models.CharField(max_length=64, null=True, blank=True)
    icon = models.CharField(max_length=255, null=True, blank=True)
    icon_color = models.CharField(max_length=32, null=True, blank=True)
    deployment_status = models.CharField(max_length=32, null=True, blank=True)
    search_status = models.CharField(max_length=32, null=True, blank=True)
    prefix = models.CharField(max_length=8, null=True, blank=True)
    default_access_level = models.CharField(max_length=32, null=True, blank=True)
    type = models.CharField(max_length=32, null=True, blank=True)

    # Whether this row represents a metadata/setup table (TRUE) or a
    # custom-business-object data table (FALSE).
    setup = models.BooleanField()

    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "object"
        verbose_name = "Object (Platform Metadata)"
        verbose_name_plural = "Objects (Platform Metadata)"

    def __str__(self) -> str:
        return f"{self.name} ({'setup' if self.setup else self.type})"


class Field(TenantModel):
    """``fields`` — column definitions per object."""

    id = models.CharField(max_length=64, primary_key=True)
    object = models.ForeignKey(
        PlatformObject,
        db_column="object_id",
        related_name="fields",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    name = models.CharField(max_length=63)
    label = models.CharField(max_length=255, null=True, blank=True)
    datatype = models.CharField(max_length=64)

    required = models.BooleanField(null=True, default=False)
    is_modifiable = models.BooleanField(null=True, default=True)

    parent_object = models.CharField(max_length=63, null=True, blank=True)
    relationship_name = models.CharField(max_length=63, null=True, blank=True)

    # Picklist + presentation flags
    pickup_values = models.JSONField(null=True, blank=True)
    sort_alpha = models.BooleanField(null=True)
    first_as_default = models.BooleanField(null=True)
    limit_predefined_values = models.BooleanField(null=True)
    no_skip = models.BooleanField(null=True)
    no_rollback = models.BooleanField(null=True)

    default_value = models.CharField(max_length=255, null=True, blank=True)
    default_value_in_checkbox = models.CharField(max_length=32, null=True, blank=True)

    # Text/number sizing
    number_length = models.IntegerField(null=True, blank=True)

    # Email-specific
    send_mail = models.BooleanField(null=True)

    # Formula-specific
    formula_expression = models.TextField(null=True, blank=True)
    formula_return_type = models.CharField(max_length=32, null=True, blank=True)

    # Rollup-summary specific
    summarized_object = models.CharField(max_length=63, null=True, blank=True)
    rollup_type = models.CharField(max_length=32, null=True, blank=True)
    field_to_aggregate = models.CharField(max_length=63, null=True, blank=True)
    filter_criteria = models.JSONField(null=True, blank=True)

    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "fields"
        verbose_name = "Field"
        verbose_name_plural = "Fields"
        # The hand-rolled DDL has a UNIQUE on (object_id, name); declare it
        # so model-level validation matches the DB.
        unique_together = (("object", "name"),)

    def __str__(self) -> str:
        return f"{self.name} ({self.datatype})"
