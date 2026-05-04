"""Tenant-scoped Django models (Phase 2 Wave 2 + Phase 3 Waves 3-5).

These are Django representations of the per-tenant setup tables that
live in each tenant's PostgreSQL schema. All models have
``Meta.managed = False``: the tables already exist per-tenant, and
Django doesn't own their schema. The Django ORM is used purely as a
query / serialization layer.

Tenant scoping is automatic when the request goes through
``api.security.tenant_schema_middleware.TenantSchemaMiddleware``,
which sets the connection's ``search_path`` to the pinned tenant
after Phase 1's schema_authority resolves the request. Background
work uses ``api.security.tenant_context.with_tenant_schema()`` to
get the same effect.

Foreign keys use ``db_constraint=False`` so Django doesn't try to
enforce constraints the underlying schema may or may not have.
PKs use ``CharField`` not ``BigAutoField`` because the platform
uses prefixed string IDs.

Imported by ``api/models.py`` so Django picks them up under the
``api`` app — see ADR-0001 for why we don't split apps.
"""

# Wave 2 — object metadata + authorization
from api.tenant_models.objects import PlatformObject, Field
from api.tenant_models.authz import (
    Profile,
    UserGroup,
    UserGroupUser,
    UserGroupProfile,
    UserGroupPublicGroup,
)
from api.tenant_models.permissions import (
    ObjectPermission,
    FieldPermission,
    TabPermission,
    AppPermission,
)
from api.tenant_models.sharing import SharingRecord

# Phase 3 Wave 3 — UI / layout
from api.tenant_models.ui import (
    App,
    PageLayout,
    SearchLayout,
    Listview,
    PageBuilder,
    PageComponent,
    PageBuilderAssignment,
    LayoutAssignment,
    HomepageAssignment,
    FieldMapping,
)

# Phase 3 Wave 4 — reporting
from api.tenant_models.reporting import (
    Report,
    ReportFolder,
    ReportFolderSharing,
    Dashboard,
    DashboardComponent,
    DashboardFolder,
    DashboardFolderSharing,
    DashboardAssignment,
)

# Phase 3 Wave 5 — workflow
from api.tenant_models.workflow import (
    Workflow,
    WorkflowNode,
    WorkflowEdge,
    PathBuilder,
    EmailTemplate,
)

# Phase 3.B — integration / telephony / email
from api.tenant_models.integration import (
    TelephonyConfig,
    LandingNumber,
    TelephonyUser,
    CallActivity,
    EmailProviderSetup,
    UserGmailToken,
    UserOutlookToken,
)

# Phase 3.B — audit / history
from api.tenant_models.audit import (
    AuditTrailTrack,
    FieldHistoryLog,
    FieldTrackingConfig,
)

# Phase 3.B — misc (+ Phase 4.A: OrgCompany)
from api.tenant_models.misc import (
    Task,
    Notification,
    SharedRecord,
    OrgCompany,
)

# Phase 4.A — shared-schema models (live in `public`, not per-tenant)
from api.tenant_models.shared import LeadCapture


__all__ = [
    # Wave 2 — object metadata
    "PlatformObject",
    "Field",
    # Wave 2 — authorization core
    "Profile",
    "UserGroup",
    "UserGroupUser",
    "UserGroupProfile",
    "UserGroupPublicGroup",
    # Wave 2 — permissions
    "ObjectPermission",
    "FieldPermission",
    "TabPermission",
    "AppPermission",
    # Wave 2 — sharing
    "SharingRecord",
    # Wave 3 — UI / layout
    "App",
    "PageLayout",
    "SearchLayout",
    "Listview",
    "PageBuilder",
    "PageComponent",
    "PageBuilderAssignment",
    "LayoutAssignment",
    "HomepageAssignment",
    "FieldMapping",
    # Wave 4 — reporting
    "Report",
    "ReportFolder",
    "ReportFolderSharing",
    "Dashboard",
    "DashboardComponent",
    "DashboardFolder",
    "DashboardFolderSharing",
    "DashboardAssignment",
    # Wave 5 — workflow
    "Workflow",
    "WorkflowNode",
    "WorkflowEdge",
    "PathBuilder",
    "EmailTemplate",
    # Wave 6 — integration / telephony / email (Phase 3.B)
    "TelephonyConfig",
    "LandingNumber",
    "TelephonyUser",
    "CallActivity",
    "EmailProviderSetup",
    "UserGmailToken",
    "UserOutlookToken",
    # Wave 7 — audit / history (Phase 3.B)
    "AuditTrailTrack",
    "FieldHistoryLog",
    "FieldTrackingConfig",
    # Wave 8 — misc (Phase 3.B + Phase 4.A: OrgCompany)
    "Task",
    "Notification",
    "SharedRecord",
    "OrgCompany",
    # Phase 4.A — shared-schema models
    "LeadCapture",
]
