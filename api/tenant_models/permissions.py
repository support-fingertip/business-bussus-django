"""Object/field/tab/app permissions — the per-profile access grants."""

from __future__ import annotations

from django.db import models

from api.tenant_models._base import TenantModel
from api.tenant_models.authz import Profile
from api.tenant_models.objects import Field, PlatformObject


class _ObjectProfilePermissionBase(TenantModel):
    """Shared scaffolding for the object/field/tab permission tables.

    Each row represents a (object, profile) grant; the boolean columns
    on the concrete subclasses encode which actions the profile may
    perform.
    """

    id = models.CharField(max_length=64, primary_key=True)
    profile = models.ForeignKey(
        Profile,
        db_column="profile_id",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )

    class Meta(TenantModel.Meta):
        abstract = True


class ObjectPermission(_ObjectProfilePermissionBase):
    """``object_permissions`` — per-(object, profile) CRUD grants."""

    object = models.ForeignKey(
        PlatformObject,
        db_column="object_id",
        related_name="object_permissions",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )

    # Action grants — names match the legacy column names so existing
    # raw-SQL queries (and the Phase 2 VALID_PERMISSION_TYPES whitelist)
    # remain compatible.
    read = models.BooleanField(default=False)
    write = models.BooleanField(default=False)
    edit = models.BooleanField(default=False)
    delete = models.BooleanField(default=False)
    view_all = models.BooleanField(default=False)
    modify_all = models.BooleanField(default=False)

    class Meta(TenantModel.Meta):
        db_table = "object_permissions"
        verbose_name = "Object Permission"
        verbose_name_plural = "Object Permissions"
        unique_together = (("object", "profile"),)

    def __str__(self) -> str:
        actions = "/".join(
            a for a in ("read", "write", "edit", "delete", "view_all", "modify_all")
            if getattr(self, a)
        ) or "none"
        return f"{self.object_id}:{self.profile_id} → {actions}"


class FieldPermission(_ObjectProfilePermissionBase):
    """``field_permissions`` — per-(field, profile) field-level grants.

    The legacy schema has overlapping flags (``read_access`` /
    ``edit_access`` / ``write_access`` / ``delete_access`` plus a
    ``read_only`` / ``visible`` pair on some tenants). All represented
    here so the ORM matches whatever shape the underlying tenant has;
    callers should treat ``*_access`` as authoritative when present.
    """

    object = models.ForeignKey(
        PlatformObject,
        db_column="object_id",
        related_name="field_permissions",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    field = models.ForeignKey(
        Field,
        db_column="fields_id",
        related_name="permissions",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )

    read_access = models.BooleanField(default=False)
    edit_access = models.BooleanField(default=False)
    write_access = models.BooleanField(default=False, null=True)
    delete_access = models.BooleanField(default=False, null=True)

    # Legacy presentation flags still present in some tenants.
    read_only = models.BooleanField(null=True)
    visible = models.BooleanField(null=True)

    class Meta(TenantModel.Meta):
        db_table = "field_permissions"
        verbose_name = "Field Permission"
        verbose_name_plural = "Field Permissions"
        unique_together = (("field", "profile"),)

    def __str__(self) -> str:
        return f"{self.field_id}:{self.profile_id}"


class TabPermission(TenantModel):
    """``tab_permissions`` — per-(object, profile) tab visibility grants."""

    id = models.CharField(max_length=64, primary_key=True)
    object = models.ForeignKey(
        PlatformObject,
        db_column="object_id",
        related_name="tab_permissions",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    profile = models.ForeignKey(
        Profile,
        db_column="profile_id",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    # Legacy column ``type`` carries the visibility setting
    # ('default_on', 'default_off', 'tab_hidden').
    type = models.CharField(max_length=32)

    class Meta(TenantModel.Meta):
        db_table = "tab_permissions"
        verbose_name = "Tab Permission"
        verbose_name_plural = "Tab Permissions"
        unique_together = (("object", "profile"),)

    def __str__(self) -> str:
        return f"{self.object_id}:{self.profile_id} = {self.type}"


class AppPermission(TenantModel):
    """``app_permissions`` — per-(app, profile) visibility flag."""

    id = models.CharField(max_length=64, primary_key=True)
    # ``app_id`` → app.id; the App model is a setup-table candidate
    # for a future wave. Use plain CharField for now.
    app_id = models.CharField(max_length=64)
    profile = models.ForeignKey(
        Profile,
        db_column="profile_id",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    access = models.BooleanField(default=False)

    class Meta(TenantModel.Meta):
        db_table = "app_permissions"
        verbose_name = "App Permission"
        verbose_name_plural = "App Permissions"
        unique_together = (("app_id", "profile"),)

    def __str__(self) -> str:
        return f"{self.app_id}:{self.profile_id} = {self.access}"
