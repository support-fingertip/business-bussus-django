"""
URL configuration for version2 project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from version2.view import empty_view
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('admin/', admin.site.urls),
    path('v2/', include('adminuser.urls')),
    path('v2/', include('api.urls')),
    path('v2/', include('public.urls')),
    path('salesforce/', include('sf_integration.urls')),
    path('facebook/', include('facebook.urls')),
    path('whatsapp/', include('whatsapp.urls')),
    path('', empty_view),
    path("export/", include("data_export.urls"))
]

from django.urls import re_path
from django.views.static import serve


def cached_media_serve(request, path, document_root=None):
    """Serve media files with browser-cache headers."""
    response = serve(request, path, document_root=document_root)
    response["Cache-Control"] = "public, max-age=86400"  # 24 hours
    return response


urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', cached_media_serve, {
        'document_root': settings.MEDIA_ROOT,
    }),
]