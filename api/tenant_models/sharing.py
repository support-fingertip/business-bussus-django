"""``sharing_records`` — per-object default sharing posture.

Naming note (important — see ADR-0003 follow-up):

  - ``sharing_records``  ← THIS module. PER-OBJECT default access
                            level (Private / Public Read Only /
                            Public Read Write). One row per object.
                            The absence of a row means PRIVATE
                            (default-deny — Phase 2.A.1).

  - ``shared_records``   ← DIFFERENT TABLE in the same tenant schema.
                            PER-RECORD ad-hoc shares with TTL
                            (record_id + user_id + access_mask +
                            expires_at). Lives in
                            ``api/permissions/FetchUsers/fetch_shared_records.py``.

These two tables sound nearly identical and they are NOT the same.
Don't conflate them when writing queries or new code.

(``owd`` was originally part of Wave 2 but the table has no DDL
anywhere in the repo and zero runtime queries. The model was removed
in Phase 2 ORM Wave 2 cleanup. If/when an Org-Wide-Default feature
ships, reintroduce the model alongside the DDL.)
"""

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
    """``sharing_records`` — per-OBJECT default sharing posture.

    One row per object; the absence of a row means PRIVATE
    (default-deny — see Phase 2.A.1).

    NOT to be confused with ``shared_records`` (per-RECORD ad-hoc
    grants). See module docstring.
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
        verbose_name = "Sharing Record (per-object default)"
        verbose_name_plural = "Sharing Records (per-object defaults)"
        # One sharing posture per object — the legacy schema is keyed
        # this way even if a UNIQUE constraint isn't always present.
        unique_together = (("object",),)

    def __str__(self) -> str:
        return f"{self.object_id}: {self.access_level}"
