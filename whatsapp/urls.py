
from django.urls import path
from .views import VerifyWebhookView

urlpatterns = [
    path('webhook/', VerifyWebhookView.as_view(), name='webhook'),
]
