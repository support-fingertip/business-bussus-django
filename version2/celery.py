import os
from celery import Celery
from celery.schedules import crontab
from datetime import timedelta
# Set the default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'version2.settings')

app = Celery('version2')

# Load task modules from all registered Django apps
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks in all installed Django apps
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')

# Celery Beat Schedule
app.conf.beat_schedule = {
    # 'sync_salesforce_every_5_minutes': {
    #     'task': 'sf_integration.tasks.process_salesforce_sync',
    #     'schedule': crontab(minute='*/1'),  # Runs every 1 minutes
    # },
    #     'auto_delete_old_bin_records_daily': {
    #     'task': 'custom_models.tasks.auto_delete_expired_bin_records',
    #     'schedule': crontab(minute='*/1'),  # runs daily at 1:00 AM
    # },
    #     'send_due_email_campaigns': {
    #     'task': 'api.emailsend.tasks.process_due_email_campaigns',
    #     'schedule': crontab(minute='*/1'),  # every 1 minute
    # },
    'send_email_verfication_notify':{
        'task':'api.emailsend.tasks.send_notify_email_verification',
        'schedule': timedelta(minutes=5) #Run daily at midnight crontab(hour=0,minute=0)
    }
}
