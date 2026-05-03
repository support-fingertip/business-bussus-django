"""``sharing_records`` and ``owd`` — record-sharing and OWD."""

from __future__ import annotations

from django.db import models

from api.tenant_models._base import TenantModel
from api.tenant_models.objects import PlatformObject


# Sharing-records access level values. Mirrors the constant in
# api/permissions/permissions.py — keep both in sync.
ACCESS_LEVEL_PRIVATE = "Private"
ACCESS_LEVEL_PUBLIC_READ_ONLY = "Public Read Only"
ACCESS_LEVEL_PUBLIC_READ_WRITE = "Public Read Write"

ACCESS_LEVEL_CHOICES = [
    (ACCESS_LEVEL_PRIVATE, "Private"),
    (ACCESS_LEVEL_PUBLIC_READ_ONLY, "Public Read Only"),
    (ACCESS_LEVEL_PUBLIC_READ_WRITE, "Public Read Write"),
]


class SharingRecord(TenantModel):
    """``sharing_records`` — per-object default sharing posture.

    One row per object; the absence of a row now means PRIVATE
    (default-deny — see Phase 2.A.1).
    """

    id = models.CharField(max_length=64, primary_key=True)
    object = models.ForeignKey(
        PlatformObject,
        db_column="object_id",
        related_name="sharing_records",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    access_level = models.CharField(
        max_length=32,
        choices=ACCESS_LEVEL_CHOICES,
    )

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "sharing_records"
        verbose_name = "Sharing Record"
        verbose_name_plural = "Sharing Records"
        # One sharing posture per object — the legacy schema is keyed
        # this way even if a UNIQUE constraint isn't always present.
        unique_together = (("object",),)

    def __str__(self) -> str:
        return f"{self.object_id}: {self.access_level}"


class OrganizationWideDefault(TenantModel):
    """``owd`` — org-wide default access table (legacy-named singleton-ish).

    Each row maps an object to a default access level — semantically the
    same shape as ``sharing_records`` but kept as a separate table for
    historical reasons. Phase 2 documents both; the merge is a Phase 4
    candidate.
    """

    id = models.CharField(max_length=64, primary_key=True)
    object = models.ForeignKey(
        PlatformObject,
        db_column="object_id",
        related_name="owd_entries",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
    )
    access_level = models.CharField(
        max_length=32,
        choices=ACCESS_LEVEL_CHOICES,
        default=ACCESS_LEVEL_PRIVATE,
    )

    created_by_id = models.CharField(max_length=64, null=True, blank=True)
    last_modified_by_id = models.CharField(max_length=64, null=True, blank=True)
    created_date = models.DateTimeField(null=True, blank=True)
    last_modified_date = models.DateTimeField(null=True, blank=True)

    class Meta(TenantModel.Meta):
        db_table = "owd"
        verbose_name = "Organization-Wide Default"
        verbose_name_plural = "Organization-Wide Defaults"
        unique_together = (("object",),)

    def __str__(self) -> str:
        return f"{self.object_id}: {self.access_level}"
