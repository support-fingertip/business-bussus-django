"""Sentry tag enrichment — Phase 10-risk #4 (error tracking).

In plain English
----------------

Settings already initialise Sentry when ``SENTRY_DSN`` is set. But by
default every Sentry event has no association with which tenant or
user triggered it — every error in a multi-tenant system would land
in one big bucket, making customer-specific incident triage painful.

This middleware adds three tags to every Sentry scope (and thus every
event sent during the request):

  * ``tenant_id`` — the org_id pinned by ``schema_authority.pin_request_tenant``
  * ``tenant_schema`` — the schema name (same info, useful for SQL-fluent debuggers)
  * ``user_id`` — the authenticated user's id

Why a middleware (not the Sentry Django integration's default)?
---------------------------------------------------------------

Sentry's ``DjangoIntegration`` adds ``user.id`` automatically from
``request.user``, but the platform uses a custom ``request.user_``
dict (not Django's ``request.user``), so the built-in path doesn't
fire. This middleware closes the gap.

Cost
----

Negligible — one ``sentry_sdk.set_tag`` per request. If sentry-sdk
isn't installed (some dev environments), the middleware is a no-op
because the import lives inside ``try``.
"""

from __future__ import annotations

import logging

from django.utils.deprecation import MiddlewareMixin

logger = logging.getLogger(__name__)


class SentryTenantTagMiddleware(MiddlewareMixin):
    """Tag every Sentry event raised during the request with tenant + user."""

    def process_request(self, request):
        # Import here so the middleware is a no-op when sentry-sdk
        # isn't installed (we'd rather degrade than fail).
        try:
            import sentry_sdk
        except ImportError:
            return None

        # The schema_authority pin runs in the dispatcher's
        # process_view, so for non-DRF views the tags are only set
        # AFTER pin_request_tenant runs (we use process_response
        # to catch those too). For DRF views the dispatcher runs
        # pin_request_tenant before this, so the tags are available
        # immediately.
        with sentry_sdk.configure_scope() as scope:
            tenant_id = getattr(request, "tenant_org_id", None)
            tenant_schema = getattr(request, "tenant_schema", None)
            if tenant_id:
                scope.set_tag("tenant_id", str(tenant_id))
            if tenant_schema:
                scope.set_tag("tenant_schema", str(tenant_schema))

            # user_ is the dict-shape "current user" the dispatcher
            # populates from the JWT. Fall back to Django's request.user
            # if it isn't set (some non-DRF views).
            user_ = getattr(request, "user_", None)
            user_id = None
            if isinstance(user_, dict):
                user_id = user_.get("id")
            elif user_ is not None:
                user_id = getattr(user_, "id", None)
            if user_id:
                scope.set_user({"id": str(user_id)})

        return None

    def process_response(self, request, response):
        # Some flows (e.g. background work that calls into Django views
        # internally) pin the tenant LATER in the request, after our
        # process_request fired. Re-set the tags on the way out so
        # late-arriving exceptions are correctly tagged.
        try:
            import sentry_sdk
        except ImportError:
            return response

        with sentry_sdk.configure_scope() as scope:
            tenant_id = getattr(request, "tenant_org_id", None)
            if tenant_id and not scope._tags.get("tenant_id"):
                scope.set_tag("tenant_id", str(tenant_id))
        return response
