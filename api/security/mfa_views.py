"""MFA enrollment / verification endpoints — Phase C9.

Four endpoints, all requiring a valid JWT (you must be logged in to
manage your own MFA):

  GET  /v2/mfa/status   — is MFA enabled for me?
  POST /v2/mfa/enroll   — start enrollment: returns a provisioning
                          URI (the frontend renders it as a QR code)
                          + 10 one-time recovery codes (shown ONCE)
  POST /v2/mfa/confirm  — finish enrollment: verify a 6-digit code
                          from the authenticator app -> MFA goes live
  POST /v2/mfa/disable  — turn MFA off: requires a current code

The actual login-time MFA challenge is wired into the login flow
separately — see docs/security/C9_MFA_INTEGRATION_GUIDE.md. These
endpoints only manage a user's own MFA enrollment.
"""

from __future__ import annotations

import logging

from django.utils.timezone import now
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from authentication.custom_jwt_auth import CustomJWTAuthentication
from api.security import mfa

logger = logging.getLogger(__name__)


def _current_user_id(request):
    """Resolve the authenticated user's id from the JWT-auth'd request."""
    user = getattr(request, "user", None)
    return getattr(user, "id", None)


class MFAStatusView(APIView):
    """GET /v2/mfa/status — whether the current user has MFA enabled."""

    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from api.models import UserMFA

        user_id = _current_user_id(request)
        row = UserMFA.objects.filter(user_id=user_id).first()
        return Response({
            "enabled": bool(row and row.enabled),
            "enrolled": bool(row),
        })


class MFAEnrollView(APIView):
    """POST /v2/mfa/enroll — begin MFA enrollment.

    Generates a fresh TOTP secret and 10 recovery codes. Creates (or
    replaces) a PENDING UserMFA row (enabled=False). Returns the
    provisioning URI + the plaintext recovery codes.

    The recovery codes are shown EXACTLY ONCE. They're stored hashed;
    we cannot show them again. The frontend must make the user save
    them before continuing.
    """

    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from api.models import User, UserMFA

        user_id = _current_user_id(request)
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."}, status=404)

        existing = UserMFA.objects.filter(user_id=user_id).first()
        if existing and existing.enabled:
            # Already on. Re-enrolling would silently invalidate the
            # old authenticator — make the user disable first.
            return Response(
                {"error": "MFA is already enabled. Disable it first to re-enroll."},
                status=409,
            )

        secret = mfa.generate_secret()
        plaintext_recovery = mfa.generate_recovery_codes()
        hashed_recovery = [mfa.hash_recovery_code(c) for c in plaintext_recovery]

        # Create or overwrite the pending row.
        UserMFA.objects.update_or_create(
            user=user,
            defaults={
                "secret": secret,            # EncryptedCharField -> encrypted at rest
                "enabled": False,
                "recovery_codes": hashed_recovery,
                "confirmed_at": None,
            },
        )

        uri = mfa.provisioning_uri(secret, account_email=user.email or str(user_id))

        return Response({
            "provisioning_uri": uri,          # frontend renders as QR
            "recovery_codes": plaintext_recovery,  # SHOWN ONCE
            "message": (
                "Scan the QR code with an authenticator app, then call "
                "/v2/mfa/confirm with a 6-digit code. Save the recovery "
                "codes now — they will not be shown again."
            ),
        }, status=201)


class MFAConfirmView(APIView):
    """POST /v2/mfa/confirm  {"code": "123456"} — finish enrollment."""

    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from api.models import UserMFA

        user_id = _current_user_id(request)
        code = (request.data or {}).get("code", "")

        row = UserMFA.objects.filter(user_id=user_id).first()
        if not row:
            return Response(
                {"error": "No pending MFA enrollment. Call /v2/mfa/enroll first."},
                status=400,
            )
        if row.enabled:
            return Response({"error": "MFA is already enabled."}, status=409)

        if not mfa.verify_totp(row.secret, code):
            return Response(
                {"error": "Invalid or expired code. Try again."},
                status=400,
            )

        row.enabled = True
        row.confirmed_at = now()
        row.last_used_at = now()
        row.save(update_fields=["enabled", "confirmed_at", "last_used_at"])

        logger.info("MFA enabled for user %s", user_id)
        return Response({"enabled": True, "message": "MFA is now enabled."})


class MFADisableView(APIView):
    """POST /v2/mfa/disable  {"code": "123456"} — turn MFA off.

    Requires a current code (or a recovery code) so a hijacked
    session can't silently strip the victim's MFA.
    """

    authentication_classes = [CustomJWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from api.models import UserMFA

        user_id = _current_user_id(request)
        code = (request.data or {}).get("code", "")

        row = UserMFA.objects.filter(user_id=user_id).first()
        if not row or not row.enabled:
            return Response({"error": "MFA is not enabled."}, status=400)

        # Accept either a TOTP code or a one-time recovery code.
        ok = mfa.verify_totp(row.secret, code)
        if not ok:
            idx = mfa.consume_recovery_code(code, row.recovery_codes)
            ok = idx is not None
        if not ok:
            return Response(
                {"error": "A valid authenticator or recovery code is required."},
                status=400,
            )

        row.delete()
        logger.info("MFA disabled for user %s", user_id)
        return Response({"enabled": False, "message": "MFA has been disabled."})
