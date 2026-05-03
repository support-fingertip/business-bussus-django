import requests
import os

def send_email_using_sendgrid(to_email_list, subject, content, sender_email):
    api_key = os.getenv("SENDGRID_API_KEY")
    if not api_key:
        raise Exception("SendGrid API key not configured.")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "personalizations": [
            {
                "to": [{"email": email} for email in to_email_list],
                "subject": subject
            }
        ],
        "from": {
            "email": sender_email
        },
        "content": [
            {
                "type": "text/plain",
                "value": content
            }
        ]
    }

    response = requests.post("https://api.sendgrid.com/v3/mail/send", headers=headers, json=payload)
    if response.status_code != 202:
        raise Exception(f"SendGrid Error: {response.status_code} {response.text}")

    return "sent"



#-------------------



def send_bulk_email_using_sendgrid(personalizations, sender_email, template_id):
    api_key = os.getenv("SENDGRID_API_KEY")
    payload = {
        "from": {"email": sender_email},
        "personalizations": personalizations,
        "template_id": template_id
    }

    print("Sending email to", len(personalizations), "recipients in one request")

    response = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        },
        json=payload
    )
    print("Response status code:", response)

    if response.status_code != 202:
        raise Exception(f"SendGrid Error: {response.status_code} {response.text}")

    return "sent"