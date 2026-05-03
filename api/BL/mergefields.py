from django.apps import apps
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import re 
from django.core.mail import get_connection, EmailMultiAlternatives, send_mail
from django.utils.html import strip_tags
from utils.mergefields import get_record_from_sql, get_user_app_password, update_user_app_password


def replace_merge_fields(template, object_name, record_data):
    """
    Replace merge fields in the format {!Model.Field} or {!Model.Field, Default}
    Using a dictionary (record_data) fetched from raw SQL
    """
    pattern = r"{!([\w]+)\.([\w]+)(?:,\s*(.*?))?}"

    def replacer(match):
        model_name, field_name, default = match.groups()

        if model_name == object_name and field_name in record_data:
            value = record_data[field_name]
        else:
            value = None

        return str(value if value is not None else (default if default is not None else ''))

    return re.sub(pattern, replacer, template)

def is_html_template(template):
    return bool(re.search(r'</?(html|head|body|p|div|span|br|h\d|strong|em|table|tr|td|a)[^>]*>', template, re.IGNORECASE))


def send_test_email(request, user, data, **kwargs):
    object_name = data.get('selected_object')
    record_id = data.get('record_id')
    template_body = data.get('template_body')
    template_subject = data.get('template_subject', 'Test Email')
    app_password = data.get('app_password')

    if app_password:
        update_user_app_password(user.id, app_password)

    if not object_name or not record_id:
        raise Exception('Please provide valid object_name and record_id.')

    record_data = get_record_from_sql(object_name.lower(), record_id)
    recipient_email = record_data.get('email')
    if not recipient_email:
        raise Exception("Selected record does not have an 'email' field.")

    merged_template = replace_merge_fields(template_body, object_name, record_data)


    from_email = user.email
    user_app_password = get_user_app_password(user.id)

    if not user_app_password:
        raise Exception("No app password found. Please generate and paste your Gmail app password.")

    try:
        email_connection = get_connection(
            host='smtp.gmail.com',
            port=587,
            username=from_email,
            password=user_app_password,
            use_tls=True
        )

        is_html = is_html_template(merged_template)

        if is_html:
            plain_text = strip_tags(merged_template)
            email = EmailMultiAlternatives(
                subject=template_subject,
                body=plain_text,
                from_email=from_email,
                to=[recipient_email],
                connection=email_connection
            )
            email.attach_alternative(merged_template, "text/html")
            email.send()
        else:
            send_mail(
                subject=template_subject,
                message=merged_template,
                from_email=from_email,
                recipient_list=[recipient_email],
                fail_silently=False,
                connection=email_connection
            )

        return {
            "merged_template": merged_template,
            "message": f"Test email sent to {recipient_email}"
        }

    except Exception as e:
        return {"error": f"Failed to send email: {str(e)}"}


