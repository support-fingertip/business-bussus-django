"""Authorization core: ``profile``, ``user_group``, ``user_group_users``.

Note: ``roles`` was originally part of Wave 2 but has been removed —
the table has no DDL anywhere in the repo and is referenced by zero
runtime queries. If/when the role-hierarchy feature is built, the
``Role`` model can be reintroduced alongside the DDL.
"""

from __future__ import annotations

from django.db import models

from api.tenant_models._base import TenantModel


class Profile(TenantModel):
    """``profile`` — per-tenant profile rows that drive object/field access."""

    id = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255)
    profile_type = models.CharField(
        max_length=64,
        help_text=(
            "Profile category — see api.permissions.permissions.ADMIN_ROLES "
            "for the privileged values."
        ),
    )
    description = models.TextField(null=True, blank=True)

    # Audit columns (server-set; never trust client values — see Phase 2.A.4).
    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "profile"
        verbose_name = "Profile"
        verbose_name_plural = "Profiles"

    def __str__(self) -> str:
        return f"{self.name} [{self.profile_type}]"


class UserGroup(TenantModel):
    """``user_group`` — named groupings of users for sharing/routing."""

    id = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "user_group"
        verbose_name = "User Group"
        verbose_name_plural = "User Groups"

    def __str__(self) -> str:
        return self.name


class UserGroupUser(TenantModel):
    """``user_group_users`` — junction (user_group ↔ user)."""

    id = models.CharField(max_length=64, primary_key=True)
    user_group = models.ForeignKey(
        UserGroup,
        db_column="user_group_id",
        related_name="memberships",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    # FK target lives in `public.users` (cross-schema). Avoid Django FK
    # since cross-schema FK constraints aren't enforced anyway.
    user_id = models.CharField(max_length=64)

    class Meta(TenantModel.Meta):
        db_table = "user_group_users"
        verbose_name = "User Group Membership"
        verbose_name_plural = "User Group Memberships"
        unique_together = (("user_group", "user_id"),)

    def __str__(self) -> str:
        return f"{self.user_group_id}:{self.user_id}"
