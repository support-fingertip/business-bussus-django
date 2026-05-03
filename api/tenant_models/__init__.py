"""Tenant-scoped Django models (Phase 2 ORM Wave 2).

These are Django representations of the per-tenant setup tables that
live in each tenant's PostgreSQL schema (``profile``, ``object``,
``fields``, ``object_permissions``, ``field_permissions``,
``tab_permissions``, ``app_permissions``, ``sharing_records``, ``owd``,
``user_group``, ``user_group_users``, ``roles``).

Important notes:

  * **All models have ``Meta.managed = False``.** The tables already
    exist per-tenant; Django doesn't own their schema and must not try
    to ``CREATE TABLE`` / ``ALTER TABLE`` them. The Django ORM is used
    purely as a query / serialization layer.
  * **Tenant scoping is automatic** when the request goes through
    ``api.security.tenant_schema_middleware.TenantSchemaMiddleware``,
    which sets the connection's ``search_path`` to the pinned tenant
    after Phase 1's schema_authority resolves the request. Without
    that middleware these models will read from whatever schema is
    current on the connection (default: ``public``).
  * **Foreign keys use ``db_constraint=False``** so Django doesn't try
    to enforce constraints the underlying schema may or may not have.
    The legacy hand-rolled DDL doesn't always create FK constraints
    consistently across tenants.
  * **PKs use ``CharField``** not ``BigAutoField`` because the platform
    uses prefixed string IDs (``oBt_…``, ``002oBj…``).

These are imported by ``api/models.py`` so Django picks them up under
the ``api`` app — see ADR-0001 for why we don't split apps.
"""

from api.tenant_models.objects import PlatformObject, Field
from api.tenant_models.authz import (
    Profile,
    UserGroup,
    UserGroupUser,
)
from api.tenant_models.permissions import (
    ObjectPermission,
    FieldPermission,
    TabPermission,
    AppPermission,
)
from api.tenant_models.sharing import SharingRecord


__all__ = [
    # Object metadata
    "PlatformObject",
    "Field",
    # Authorization core
    "Profile",
    "UserGroup",
    "UserGroupUser",
    # Permissions
    "ObjectPermission",
    "FieldPermission",
    "TabPermission",
    "AppPermission",
    # Sharing
    "SharingRecord",
]
