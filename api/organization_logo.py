import os
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser
from authentication.custom_jwt_auth import CustomJWTAuthentication
from public.auth.session import get_connection_and_user_details
from public.utils.exists import error_record
from api.models import Organization
from CacheService.cache import CacheService

ALLOWED_TYPES = {"image/jpeg", "image/png"}
MAX_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB


class OrganizationLogoView(APIView):
    """
    GET  /v2/api/organization/logo  → returns current org logo URL (or null)
    PATCH /v2/api/organization/logo → upload / replace org logo (JPEG/PNG < 2MB)
    """
    authentication_classes = [CustomJWTAuthentication]
    parser_classes = [MultiPartParser, FormParser]

    def _get_org(self, request):
        """Return (org_id, org_name) for the authenticated user."""
        user, org, _conn, _profile_id, _schema, _referer = get_connection_and_user_details(request)
        if not org:
            raise PermissionError("Could not determine organisation for this user.")
        return org.get("id"), org.get("name", "")

    def _build_logo_url(self, request, logo_field):
        """Return an absolute URL for the logo, or None."""
        if not logo_field:
            return None
        try:
            base = request.build_absolute_uri("/").replace("http://", "https://", 1)
            return f"{base}api{logo_field.url}"
        except Exception:
            return None

    def get(self, request):
        try:
            org_id, org_name = self._get_org(request)
            org = Organization.objects.get(pk=org_id)
            return Response({
                "logo_url": self._build_logo_url(request, org.logo),
                "org_name": org_name,
            }, status=200)
        except PermissionError as e:
            return Response({"message": str(e)}, status=403)
        except Organization.DoesNotExist:
            return Response({"logo_url": None, "org_name": org_name}, status=200)
        except Exception as e:
            error_record(er=e)
            return Response({"message": str(e)}, status=500)

    def patch(self, request):
        try:
            org_id, _org_name = self._get_org(request)

            logo_file = request.FILES.get("logo")
            if not logo_file:
                return Response({"message": "No logo file provided."}, status=400)

            # --- Validate content type ---
            content_type = logo_file.content_type
            if content_type not in ALLOWED_TYPES:
                return Response(
                    {"message": "Only JPEG and PNG images are allowed."},
                    status=400,
                )

            # --- Validate file size ---
            if logo_file.size > MAX_SIZE_BYTES:
                return Response(
                    {"message": "Image must be smaller than 2 MB."},
                    status=400,
                )

            org = Organization.objects.get(pk=org_id)

            # Delete old logo file from disk to avoid orphans
            if org.logo:
                old_path = org.logo.path
                try:
                    if os.path.isfile(old_path):
                        os.remove(old_path)
                except Exception:
                    pass  # Non-fatal

            org.logo = logo_file
            org.save(update_fields=["logo"])

            # Invalidate cached org data so session.py re-fetches on next request
            try:
                cache = CacheService()
                cache.invalidate_by_id(request.user.__dict__.get("id"), "users_org")
            except Exception:
                pass

            return Response({
                "logo_url": self._build_logo_url(request, org.logo),
                "message": "Logo updated successfully.",
            }, status=200)

        except PermissionError as e:
            return Response({"message": str(e)}, status=403)
        except Organization.DoesNotExist:
            return Response({"message": "Organisation not found."}, status=404)
        except Exception as e:
            error_record(er=e)
            return Response({"message": str(e)}, status=500)
