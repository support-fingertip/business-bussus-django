# yourapp/routing.py
from django.urls import re_path
from .consumer import TelephonyConsumer,Notification, WhatsappConsumer

websocket_urlpatterns = [
    re_path(r'ws/telephony/$', TelephonyConsumer.as_asgi()),
    re_path(r'ws/notifications/$',Notification.as_asgi()),
    re_path(r"ws/whatsapp/$", WhatsappConsumer.as_asgi()),
]
