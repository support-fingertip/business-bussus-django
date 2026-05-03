
from django.db.models import Q
from whatsapp.utils import send_whatsapp_message
from whatsapp.models import Message

from django.db import connection

def get_whatsapp(request, **kwargs):
    receiver = kwargs.get('object_name')
    sender = request.GET.get('contact')
    if receiver.startswith('+'):
        receiver = receiver[1:]
    if len(receiver) == 10:
        receiver = '91' + receiver

    # Execute raw SQL to fetch messages between sender and receiver
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT *
            FROM whatsapp_message
            WHERE 
                (sender ILIKE %s AND receiver ILIKE %s)
                OR
                (sender ILIKE %s AND receiver ILIKE %s)
            ORDER BY timestamp DESC
        """, [sender, receiver, receiver, sender])

        columns = [col[0] for col in cursor.description]
        results = cursor.fetchall()

    return [dict(zip(columns, row)) for row in results]

from django.db import connection
from whatsapp.utils import send_whatsapp_message

class WhatsAppMessageException(Exception):
    """Custom exception for WhatsApp message errors."""
    pass

def post_whatsapp(contact, data, **kwargs):
    receiver_number = data.get('to')
    message_content = data.get('template') if data.get('template') else data.get('text')
    message_type = data.get('type')
    name = data.get('name', 'Unknown')

    if not message_content:
        raise WhatsAppMessageException("No message content found.")

    if not receiver_number:
        raise WhatsAppMessageException("No receiver number provided.")

    if message_type in ['text', 'template']:
        # Send message via API
        message_id = send_whatsapp_message(contact, receiver_number, message_content, message_type)

        if message_type == 'template':
            message_content = message_content.get("name")
        elif message_type == 'text':
            message_content = message_content.get("body")
        
        if len(receiver_number) == 10:
            receiver_number = '91' + receiver_number

        if message_id:
            # Insert into the database manually
            with connection.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO whatsapp_message
                    (name, message_type, message_content, sender, receiver, message_id, status, timestamp)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    RETURNING id, timestamp
                """, [
                    name,
                    message_type,
                    message_content,
                    contact,
                    receiver_number[1:] if "+" in receiver_number else receiver_number,  # remove "+" or "9"
                    message_id,
                    'sent'
                ])
                row = cursor.fetchone()

            return {
                "id": row[0],
                "name": name,
                "message_id": message_id,
                "message_content": message_content,
                "message_type": message_type,
                "status": 'sent',
                "channel_id": None,
                "sender": contact,
                "receiver": receiver_number[1:],
                "timestamp": row[1]
            }
        else:
            raise WhatsAppMessageException("Failed to send message via API.")
    else:
        raise WhatsAppMessageException("Unsupported message type.")
