from django.db import models

class FacebookLead(models.Model):
    lead_id = models.CharField(max_length=255, unique=True)
    page_id = models.CharField(max_length=255)
    form_id = models.CharField(max_length=255)
    created_time = models.DateTimeField(auto_now_add=True)
    raw_data = models.JSONField()

    def __str__(self):
        return f"Lead {self.lead_id} from Page {self.page_id}"
    
    class Meta:
        db_table = 'facebook_lead'
        verbose_name = 'Facebook Lead'
        verbose_name_plural = 'Facebook Leads' 
    
    
class Webhook(models.Model):
    #tenant = models.ForeignKey(Organisation, on_delete=models.CASCADE, related_name="webhooks")  # Link to tenant
    url = models.URLField(max_length=1024)  # The URL where the webhook sends data (e.g., your webhook handler URL)
    status = models.CharField(max_length=50, choices=[('ACTIVE', 'Active'), ('INACTIVE', 'Inactive')], default='ACTIVE')  # Webhook status
    created_at = models.DateTimeField(auto_now_add=True)  # Timestamp when the webhook was created
    updated_at = models.DateTimeField(auto_now=True)  # Timestamp for when the webhook was last updated
    last_received = models.DateTimeField(null=True, blank=True)  # Timestamp of the last webhook received

    def __str__(self):
        return f"Webhook for {self.tenant.name} - {self.url}"
    
    class Meta:
        db_table = 'webhook'
        verbose_name = 'Webhook'
        verbose_name_plural = 'Webhooks' 
