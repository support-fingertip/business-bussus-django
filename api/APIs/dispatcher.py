import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from authentication.custom_jwt_auth import CustomJWTAuthentication
from api.BL.blcontroller import BusinessLogicHandler
from public.auth.session import get_connection_and_user_details
from public.utils.exists import error_record
from ..notifications.notify import get_admin, trigger_notication
from api.security.schema_authority import (
    TenantViolation,
    pin_request_tenant,
)
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)


def _safe_500(exc, request, action):
    """Log full exception server-side, return generic message to client."""
    logger.error(
        "Dispatcher %s failed: %s",
        action,
        exc,
        exc_info=True,
        extra={
            "user_id": getattr(getattr(request, "user_", None) or {}, "get",
                               lambda *_: None)("id") if isinstance(
                getattr(request, "user_", None), dict) else None,
            "schema": getattr(request, "tenant_schema", None) or getattr(request, "schema", None),
            "path": getattr(request, "path", None),
        },
    )
    error_record(er=exc)
    return Response(
        {"message": "An internal error occurred. Please try again later."},
        status=500,
    )


class Dispatcher(APIView):
    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def __init__(self, **kwargs):
        self.channel = get_channel_layer()

    def _init_request_context(self, request):
        """Attach browser and user/org details into request.

        Tenant resolution is gated through ``pin_request_tenant``: the
        JWT-asserted org/schema/profile values are reconciled against the
        database before any downstream layer sees them. ``request.tenant_*``
        attributes are the canonical, trusted source from this point on.
        """
        user_agent = request.META.get("HTTP_USER_AGENT", "").lower()
        request.request_from_browser = any(
            browser in user_agent for browser in ["mozilla", "chrome", "safari", "edge"]
        )
        # Get connection and user details from the session/JWT payload.
        # Treat the schema/org/profile here as ASSERTED — never trusted
        # until pin_request_tenant has reconciled them with the DB.
        user, org, db_connection, asserted_profile_id, asserted_schema, referer = (
            get_connection_and_user_details(request)
        )

        request.user_ = user
        if request.user_ and not request.user_.get("is_active", True):
            raise PermissionError("User account is inactive.")

        # Reconcile (user, org, schema, profile_id) against the DB. Any
        # cross-tenant mismatch raises TenantViolation (PermissionError),
        # which the view methods convert to a 403.
        user_id = (request.user_ or {}).get("id")
        asserted_org_id = (org or {}).get("id") if isinstance(org, dict) else None
        ctx = pin_request_tenant(
            request,
            user_id=user_id,
            asserted_org_id=asserted_org_id,
            asserted_schema=asserted_schema,
            asserted_profile_id=asserted_profile_id,
        )

        # Keep the legacy attribute names populated for callers that still
        # read `request.schema` / `request.profile_id`. Newly written code
        # should read `request.tenant_schema` / `request.tenant_profile_id`.
        request.org = org
        request.connection = db_connection
        request.profile_id = ctx.profile_id
        request.schema = ctx.schema
        request.referer = referer

    def _init_handler(self, request, object_name):
        """Initialize BL handler after context is set"""
        self._init_request_context(request)
        return BusinessLogicHandler(request, object_name)

    # Send notification to admin
    def generate_notication(self, request, **kwargs):
        another_object = kwargs.get("another_object")
        user_id = kwargs.get("user_", {}).get("id")
        adminid = get_admin(user_id)
        trigger_notication(
            owner_id=adminid,
            channel_layer=self.channel,
            title=another_object,
            notification_type="alert",
            user_id=user_id,
            channel="push",
            request=request,
            **kwargs
        )

    def get(self, request, object_name, another_object=None, param3=None):
        try:
            handler = self._init_handler(request, object_name)
            result = handler.get_business_logic(
                object_name=another_object,
                param3=param3,
                browser=request.request_from_browser,
                user_=request.user_,
                connection=request.connection,
                profile_id=request.profile_id,
                org=request.org,
                schema=request.schema,
            )
            return Response(data=result, status=200)
        except PermissionError as e:
            return Response({"message": str(e)}, status=403)
        except Exception as e:
            return _safe_500(e, request, "GET")

    def post(self, request, object_name, another_object=None, param3=None):
        data = request.data
        try:
            handler = self._init_handler(request, object_name)
            result = handler.post_business_logic(
                data,
                another_object=another_object,
                param3=param3,
                browser=request.request_from_browser,
                user_=request.user_,
                connection=request.connection,
                profile_id=request.profile_id,
                org=request.org,
                schema=request.schema,
                referer=request.referer
            )
            if isinstance(result, dict) and result.get("status") == "error" and result.get("success") == False:
                return Response(data=result, status=400)
            # if result.get("success") == True:
            #     self.generate_notication(
            #         another_object=another_object or object_name,
            #         user_=request.user_,
            #         request=request,
            #         message=f"New {another_object or object_name} created",
            #         data=result.get("data", []) if object_name != "setup" else result
            #     )
            return Response(data=result, status=201)
        except PermissionError as e:
            return Response({"message": str(e)}, status=403)
        except Exception as e:
            return _safe_500(e, request, "POST")

    def patch(self, request, object_name, another_object=None, param3=None):
        data = request.data
        try:
            handler = self._init_handler(request, object_name)
            result = handler.patch_business_logic(
                data,
                another_object=another_object,
                param3=param3,
                browser=request.request_from_browser,
                user_=request.user_,
                connection=request.connection,
                profile_id=request.profile_id,
                org=request.org,
                schema=request.schema,
            )
            if isinstance(result, dict) and result.get("success") == False:
                return Response(data=result, status=400)
            return Response(data=result, status=200)
        except PermissionError as e:
            return Response({"message": str(e)}, status=403)
        except Exception as e:
            return _safe_500(e, request, "PATCH")

    def delete(self, request, object_name, another_object=None, param3=None):
        data = request.data
        try:
            handler = self._init_handler(request, object_name)
            result = handler.delete_business_logic(
                data,
                another_object=another_object,
                param3=param3,
                browser=request.request_from_browser,
                user_=request.user_,
                connection=request.connection,
                profile_id=request.profile_id,
                org=request.org,
                schema=request.schema,
            )
            return Response(data=result, status=200)
        except PermissionError as e:
            return Response({"message": str(e)}, status=403)
        except Exception as e:
            return _safe_500(e, request, "DELETE")
