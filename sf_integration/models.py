from django.db import models
from django.utils.timezone import now
from datetime import timedelta

from api.security.encrypted_fields import EncryptedCharField

class SalesforceMetadata(models.Model):
    object_name = models.CharField(max_length=255, unique=True)
    fields = models.JSONField()  # Stores field names and types in JSON format
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.object_name
    
    class Meta:
        db_table = 'salesforce_metadata'
        verbose_name = 'Salesforce Metadata'
        verbose_name_plural = 'Salesforce Metadata' 


class SalesforceSettings(models.Model):
    username = models.CharField(max_length=255)
    # Phase 3: Salesforce credentials encrypted at rest. max_length bumped
    # 255 → 1024 to fit Fernet's ~140 char overhead. Django migration
    # 0002 widens the underlying varchar column.
    password = EncryptedCharField(max_length=1024)
    client_id = models.CharField(max_length=255)
    client_secret = EncryptedCharField(max_length=1024)
    sync_enabled = models.BooleanField(default=True)  # Enable/disable sync globally
    
    class Meta:
        db_table = 'salesforce_settings'
        verbose_name = 'Salesforce Setting'
        verbose_name_plural = 'Salesforce Settings' 

class SalesforceSync(models.Model):
    object_name = models.CharField(max_length=255, unique=True)
    label = models.CharField(max_length=255, null=True, blank=True)
    syncing_frequency = models.IntegerField(default=30)  # in minutes
    salesforce_pull = models.BooleanField(default=False)
    salesforce_push = models.BooleanField(default=False)
    is_enabled = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    def is_sync_due(self):
        if not self.last_synced_at:
            return True
        return now() >= self.last_synced_at + timedelta(minutes=self.syncing_frequency)

    def __str__(self):
        return self.object_name
    
    class Meta:
        db_table = 'salesforce_sync'
        verbose_name = 'Salesforce Sync'
        verbose_name_plural = 'Salesforce Sync' 
