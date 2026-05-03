
from django.urls import path

# from facebook.webhook import LeadCaptureWebhookView
from .views import FetchLeadForms, GetPageAccessToken, facebook_login
from .leadwebhook import FacebookWebhookView

urlpatterns = [
    path('api/facebook/login/', facebook_login),
    path('fetch-lead-forms/', FetchLeadForms.as_view(), name='fetch_lead_forms'),
    path('get-page-access-token/', GetPageAccessToken.as_view(), name='get_page_access_token'),
    path('leadcapture/', FacebookWebhookView.as_view(), name='lead-capture-webhook'),
]

