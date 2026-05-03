from django.urls import path

from adminuser.LoginView import LoginView
from adminuser.views import YourAPIView


urlpatterns = [
    path('admin/login', LoginView.as_view(), name='admin_login'),
    path('admin/<str:table>/<str:second>/<str:third>', YourAPIView.as_view(), name='admin_logout'),
    path('admin/<str:table>/<str:second>', YourAPIView.as_view(), name='admin_logout'),
    path('admin/<str:table>', YourAPIView.as_view(), name='admin_logout'),
]
