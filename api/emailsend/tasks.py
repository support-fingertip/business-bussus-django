from celery import shared_task
from datetime import datetime
from api.emailsend.views import send_test_email
from django.db import connection
from datetime import datetime
from api.telephony.views import run_query

from channels.layers import get_channel_layer
from ..notifications.notify import trigger_notication

import json

@shared_task
def process_due_email_campaigns(request):
    now = datetime.utcnow()
    print(f"🔄 Checking for campaigns due before (UTC): {now.isoformat()}Z")


    # Step 1: Fetch due email campaigns
    campaign_query = """
        SELECT * FROM campaign
        WHERE status = 'draft'
        AND type = 'email'
        AND send_time <= %s
        AND is_deleted = FALSE
    """
    campaigns = run_query(campaign_query, [now])
    print(f"📦 Found {len(campaigns)} campaign(s) to process")

    for campaign in campaigns:
        campaign_id = campaign["id"]
        campaign_name = campaign["name"]
        module = campaign["module"]
        template_id = campaign["template"]
        user_id = campaign["created_by_id"]

        print(f"\n➡️ Processing Campaign: {campaign_name} (ID: {campaign_id})")

        # Step 2: Get template data
        template_query = "SELECT subject, body FROM email_templates WHERE id = %s"
        template_result = run_query(template_query, [template_id])
        if not template_result:
            print(f"⚠️ Skipping: Template ID '{template_id}' not found.")
            continue

        subject = template_result[0]["subject"]
        body = template_result[0]["body"]
        print(f"📝 Loaded Template: Subject='{subject[:30]}...'")

        # Step 3: Get campaign members
        member_query = "SELECT record_id FROM campaign_member WHERE campaign_id = %s"
        members = run_query(member_query, [campaign_id])
        record_ids = [m["record_id"] for m in members]
        print(f"👥 Found {len(record_ids)} campaign member(s)")

        if not record_ids:
            print("⚠️ Skipping: No members found for this campaign.")
            continue

        # Step 4: Get user details
        user = get_user_by_id(user_id)
        if not user:
            print(f"⚠️ Skipping: User ID '{user_id}' not found.")
            continue

        print(f"📧 Sending emails to records: {record_ids}")

        # Step 5: Send email
        send_test_email(request, user, {
            "template_subject": subject,
            "template_body": body,
            "selected_object": module,
            "record_ids": record_ids
        })

        # Step 6: Mark as completed
        print(f"✅ Updating status to 'completed' for campaign: {campaign_id}")
        run_query("UPDATE campaign SET status = 'completed' WHERE id = %s", [campaign_id])
        print(f"✅ Campaign '{campaign_name}' marked as completed.")


def get_user_by_id(user_id):
    query = """
        SELECT id, email, first_name, last_name
        FROM users
        WHERE id = %s
        LIMIT 1
    """
    result = run_query(query, [user_id])
    return result[0] if result else None


BATCH_SIZE = 100

@shared_task
def send_notify_email_verification():
    print("Starting email verification reminders...")
    offset = 0
    channel_layer = get_channel_layer()
    total_processed = 0

    while True:
        unverified_users_query = """
            SELECT id, name 
            FROM public.users 
            WHERE is_email_verified = %s
            LIMIT %s OFFSET %s
        """
        users = run_query(unverified_users_query, [False, BATCH_SIZE, offset])

        if not users:
            break  # no more records

        for user in users:
            user_id = user["id"]
            name = (user.get("name") or "").capitalize()
            title = "Email Verification"
            message = f"Hello {name}, it seems like your email is not verified yet!"

            trigger_notication(
                owner_id=user_id,
                channel_layer=channel_layer,
                title=title,
                message=message,
                notification_type="reminder",
                channel="email",
                user_id=user_id
            )
            total_processed += 1
        offset += BATCH_SIZE
    print("Starting email end")
    return f"Processed {total_processed} users"

    #Command for runing CELERY on windows
    #  celery -A project_name beat --loglevel=info 
    # celery -A version2.celery worker -l info  