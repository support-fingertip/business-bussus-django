

import uuid
from django.db import models
class Channel(models.Model):
    id = models.CharField(primary_key=True, max_length=32, editable=False)
    name = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=15, unique=True)
    whatsapp_business_account_id = models.CharField(max_length=255)
    access_token = models.CharField(max_length=255)
    status = models.CharField(max_length=50, choices=[('active', 'Active'), ('inactive', 'Inactive')], default='active')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.name} ({self.phone_number})'
    
    class Meta:
        db_table = 'channel'
        verbose_name = 'Channel'
        verbose_name_plural = 'Channels' 


class Message(models.Model):
    id = models.CharField(primary_key=True, max_length=32, editable=False)
    MESSAGE_TYPES = [
        ('text', 'Text'),
        ('image', 'Image'),
        ('video', 'Video'),
        ('audio', 'Audio'),
        ('document', 'Document'),
        ('location', 'Location'),
        ('interactive', 'Interactive'),
        ('template', 'Template')
    ]
    
    STATUS_CHOICES = [
        ('sent',      'Sent'),       # outbound: queued by WA
        ('delivered', 'Delivered'),  # outbound: delivered to handset
        ('read',      'Read'),       # outbound: user read
        ('received',  'Received'),   # inbound: we received
        ('failed',    'Failed'),     # outbound: could not deliver
        ('deleted',   'Deleted'),    # outbound: user deleted
    ]
    name = models.CharField(max_length=255, null=True, blank=True)
    channel = models.ForeignKey(Channel, related_name='messages', on_delete=models.CASCADE, null=True, blank=True)
    message_type = models.CharField(max_length=50, choices=MESSAGE_TYPES)
    message_content = models.TextField()  # This can store different content types, like URLs or text.
    message_id = models.CharField(max_length=1024, null=True, blank=True)
    sender = models.CharField(max_length=255)
    receiver = models.CharField(max_length=255)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='sent')
    error = models.CharField(max_length=1024, blank=True, null=True)
    error_code  = models.IntegerField(null=True, blank=True)
    seen_at = models.DateTimeField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f'Message from {self.sender} to {self.receiver} via {self.channel.name}'
    
    def save(self, *args, **kwargs):
        if not self.id:  # Generate a UUID-based ID
            random_id = uuid.uuid4().hex[:10]  # Take the first 9 characters of a UUID
            self.id = f"001Aps{random_id}as"
        super().save(*args, **kwargs)
        
    class Meta:
        db_table = 'message'
        verbose_name = 'Message'
        verbose_name_plural = 'Messages' 
