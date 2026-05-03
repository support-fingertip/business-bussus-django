# utils/gmail_service.py
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from googleapiclient.discovery import build
from .gmail_auth import authenticate,save_token,save_user_email
from django.utils.html import strip_tags
import re

from .gmail_auth import get_user_gmail_credentials

def is_html_template(template):
    return bool(re.search(r'</?(html|head|body|p|div|span|br|h\d|strong|em|table|tr|td|a)[^>]*>', template, re.IGNORECASE))

def _join_recipients(recipients):
    if recipients is None:
        return None
    if isinstance(recipients, (list, tuple)):
        return ", ".join(str(r) for r in recipients if r)
    return str(recipients)


def create_message(to, subject, html_content, cc=None):
    """Build a MIME message; supports optional CC (list or string)."""
    to_header = _join_recipients(to)
    cc_header = _join_recipients(cc)

    if is_html_template(html_content):
        plain_text = strip_tags(html_content)
        message = MIMEMultipart('alternative')
        message['to'] = to_header
        message['subject'] = subject
        if cc_header:
            message['cc'] = cc_header
        part1 = MIMEText(plain_text, 'plain')
        part2 = MIMEText(html_content, 'html')
        message.attach(part1)
        message.attach(part2)
    else:
        message = MIMEText(html_content, 'plain')
        message['to'] = to_header
        message['subject'] = subject
        if cc_header:
            message['cc'] = cc_header

    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    return {'raw': raw}


def send_email_using_gmail_api(to_email, subject, body, user_id, cc=None, **kwargs):
    print("Starting Gmail email send process...")
    try:
        creds = authenticate(user_id,**kwargs)
        if isinstance(creds, dict) and "authurl" in creds:
            return creds
    except Exception as e:
        if e.args:
            if 'invalid_grant' in e.args[0]:
                    token_path = 'api/emailsend/token.json'
                    import os
                    if os.path.exists(token_path):
                        os.remove(token_path)
                    creds = authenticate(user_id,**kwargs)
            else:
                raise e
    try:
        service = build('gmail', 'v1', credentials=creds)
        message = create_message(to_email, subject, body, cc=cc)
        sent = service.users().messages().send(userId='me', body=message).execute()
        return sent['id']
    except Exception as er:
        raise er




#Per user credentials 


# def send_email_using_gmail_api(user_id, to_email, subject, body):
#     creds = get_user_gmail_credentials(user_id)  # 👈 Per-user credentials
#     service = build('gmail', 'v1', credentials=creds)
#     message = create_message(to_email, subject, body)
#     sent = service.users().messages().send(userId='me', body=message).execute()
#     return sent['id']


# from googleapiclient.discovery import build

def get_authenticated_gmail_address(creds):
    service = build('gmail', 'v1', credentials=creds)
    profile = service.users().getProfile(userId='me').execute()
    return profile['emailAddress']


