from django.urls import path

from api.health.views import liveness, readiness

urlpatterns = [
    path("healthz", liveness, name="healthz"),
    path("livez", liveness, name="livez"),
    path("readyz", readiness, name="readyz"),
]
