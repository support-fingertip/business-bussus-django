from django.urls import path
from api.APIs.dispatcher import Dispatcher
from api.emailsend.views import GmailOAuthCallbackView, SendTestEmailAPIView, OutlookAuthURLView, OutlookOAuthCallbackView
from api.telephony.views import *
from api.organization_logo import OrganizationLogoView
from api.pdfgen.views import InvoicePDFView


urlpatterns = [
    #Organization logo
    path('api/organization/logo', OrganizationLogoView.as_view(), name='org_logo'),

    #Invoice PDF print
    path('api/invoice/<str:invoice_id>/pdf', InvoicePDFView.as_view(), name='invoice_pdf'),

    #Business logic APIs
    path('api/<str:object_name>/<str:another_object>/<str:param3>', Dispatcher.as_view(), name='data_manipulation3'),
    path('api/<str:object_name>/<str:another_object>', Dispatcher.as_view(), name='data_manipulation2'),
    path('api/<str:object_name>', Dispatcher.as_view(), name='data_manipulation'),

    #Email related callback APIs
    path('api/send-email/', SendTestEmailAPIView.as_view(), name='send_email'),
    path('api/gmail/oauth/callback/', GmailOAuthCallbackView.as_view(), name='gmail-oauth-callback'),
    path('api/outlook/connect-url/', OutlookAuthURLView.as_view(), name="outlook-auth-url"),
    path('api/outlook/oauth/callback/', OutlookOAuthCallbackView.as_view(), name="outlook-auth-callback"),

    #Call related APIs 
    path('telephony/route', telephony_route),
    path('telephony/connecting', telephony_connecting),
    path('telephony/hangup', telephony_hangup),
    path('telephony/cdr', telephony_cdr),
    path('telephony/outgoing', telephony_outgoing),
    path("incoming-call/",incoming_call),
]

# path('nylas/call-back',nylas_callBack,name="nylas-email-verification"),
# path('nylas/one/call-back',another_callback,name="nylasemailverification"),
# path("make-call/",make_call),
# path("connect-agent/",connect_agent),
# path("generate-twilio-token/",generate_twilo_token),
# path("get-call-status/",get_Call_status),
# path("api/test-api-call/",execute_test_api),
# path("accept-call/",accept_call),
# path("test-functions/",user_can_make_call),
# path("test-jwt/",test_jwt),
# path('forgot_password', ForgotPasswordView.as_view(), name='forgot_password'),
# path('user', UserRegistrationView.as_view(), name='user'),
# path('api/email/connect-url/', GmailAuthURLView.as_view(), name='gmail-auth-url'),