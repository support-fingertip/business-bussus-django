from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from public.auth import otp_verification, reset_password, signup
from public.auth.login import LoginView
from public.auth.logout import LogoutView
from public.utils.exists import ExistsView
from public.utils.suggestions import CheckUsernameExistsView, SuggestionDomainView, SuggestionUsernameView
# Phase C9 — multi-factor-auth enrollment endpoints.
from api.security.mfa_views import (
    MFAConfirmView,
    MFADisableView,
    MFAEnrollView,
    MFAStatusView,
)

urlpatterns = [
    path('login', LoginView.as_view(), name='login'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('reset_password', reset_password.set_password_with_proof, name='reset_password'),
    # Phase C9 — MFA (TOTP) enrollment + management. All require a JWT.
    path('mfa/status', MFAStatusView.as_view(), name='mfa_status'),
    path('mfa/enroll', MFAEnrollView.as_view(), name='mfa_enroll'),
    path('mfa/confirm', MFAConfirmView.as_view(), name='mfa_confirm'),
    path('mfa/disable', MFADisableView.as_view(), name='mfa_disable'),
    # OTP Verification APIs
    path("start", csrf_exempt(otp_verification.start_otp)),
    path("verify", csrf_exempt(otp_verification.verify_otp)),
    path("resend", csrf_exempt(otp_verification.resend_otp)),
    path("status", otp_verification.status_otp),
    path("cancel", otp_verification.cancel_otp),
    path("auth/signup", signup.signup_with_proof, name='signup_with_proof'),
    path("exists/<str:table_name>", ExistsView.as_view(), name='exists'),
    path("suggestion/domain", SuggestionDomainView.as_view(), name='suggestion_domain'),
    path("suggestion/email", SuggestionUsernameView.as_view(), name='suggestion_email'),

    path("check/username/", CheckUsernameExistsView.as_view(), name='check_username'),
]