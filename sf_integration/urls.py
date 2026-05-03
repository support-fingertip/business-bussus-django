from django.urls import path
from .views import get_salesforce_sync,sync_salesforce_metadata, update_salesforce_sync

urlpatterns = [
    # path('salesforce-settings/', salesforce_settings, name='salesforce_settings'),
    path('salesforce-sync/', get_salesforce_sync, name='get_salesforce_sync'),
    path('salesforce-sync-update/', update_salesforce_sync, name='update_salesforce_sync'),
    path("sync-metadata/", sync_salesforce_metadata, name="sync_metadata"),
    
]
