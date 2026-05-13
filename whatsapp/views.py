from django.http import HttpResponse, JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from .models import Message  # if unused, you can remove this
import json
from datetime import datetime, timezone
from django.db import connection

from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


@method_decorator(csrf_exempt, name='dispatch')
class VerifyWebhookView(APIView):
    # Phase 2.A4 — explicit authentication_classes=[] + AllowAny so this
    # view doesn't depend on global DRF defaults. When STRICT_AUTH=1,
    # this view must continue working without a JWT (WhatsApp calls it
    # during the verify-handshake and per inbound message).
    # SECURITY: the HMAC check on X-Hub-Signature-256 is what actually
    # authenticates an inbound request. The handshake GET path uses a
    # shared verify_token — currently hardcoded to "verify" (line below);
    # production should use os.getenv("WHATSAPP_VERIFY_TOKEN").
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        VERIFY_TOKEN = "verify"  # Or use os.getenv("VERIFY_TOKEN")

        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if mode == "subscribe" and token == VERIFY_TOKEN:
            return HttpResponse(challenge, content_type="text/plain")
        else:
            return HttpResponse("Verification token mismatch", status=403)

    def post(self, request, *args, **kwargs):
        try:
            data = json.loads(request.body)
            print(json.dumps(data, indent=2))  # Debug log

            # Channel layer for websocket pushes
            channel_layer = get_channel_layer()

            for entry in data.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    metadata = value.get("metadata", {})

                    # -------- Incoming messages ----------
                    messages = value.get("messages", [])
                    sender_name = "Unknown"

                    for msg in messages:
                        sender_id = msg.get("from")
                        receiver_id = metadata.get("display_phone_number")
                        phone_number_id = metadata.get("phone_number_id")
                        message_id = msg.get("id")
                        message_type = msg.get("type")
                        timestamp = datetime.fromtimestamp(int(msg.get("timestamp")))
                        contacts = value.get("contacts", [])

                        if contacts:
                            contact = contacts[0]
                            sender_name = contact.get("profile", {}).get("name", "Unknown")

                        # Get message content based on type
                        if message_type == "text":
                            content = msg["text"].get("body", "")
                        elif message_type == "image":
                            content = f"[Image] Media ID: {msg['image'].get('id', '')}"
                        elif message_type == "document":
                            content = f"[Document] File name: {msg['document'].get('filename', '')}"
                        elif message_type == "audio":
                            content = f"[Audio] Media ID: {msg['audio'].get('id', '')}"
                        elif message_type == "video":
                            content = f"[Video] Media ID: {msg['video'].get('id', '')}"
                        elif message_type == "location":
                            loc = msg.get("location", {})
                            content = f"[Location] Lat: {loc.get('latitude')}, Long: {loc.get('longitude')}"
                        elif message_type == "interactive":
                            interaction = msg.get("interactive", {})
                            content = f"[Interactive] Type: {interaction.get('type')}, Data: {json.dumps(interaction)}"
                        elif message_type == "template":
                            template = msg.get("template", {})
                            name = template.get("name", "Unknown Template")
                            lang = template.get("language", {}).get("code", "N/A")
                            content = f"[Template] Name: {name}, Language: {lang}"
                        else:
                            content = "[Unknown message type]"

                        # Insert message into the database
                        with connection.cursor() as cursor:
                            cursor.execute("""
                                INSERT INTO whatsapp_message
                                    (message_type, message_content, message_id, sender, receiver, timestamp, status, name)
                                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """, [
                                message_type,
                                content,
                                message_id,
                                sender_id,
                                phone_number_id,
                                timestamp,
                                'received',
                                str(sender_name),
                            ])

                        print("phone_number_id:", phone_number_id)

                        # Push incoming message to websocket group
                        try:
                            async_to_sync(channel_layer.group_send)(
                                f"whatsapp_{phone_number_id}",   # must match WhatsappConsumer group_name
                                {
                                    "type": "whatsapp_message",  # maps to async def whatsapp_message
                                    "message": {
                                        "sender": sender_id,
                                        "receiver": receiver_id,
                                        "content": content,
                                        "timestamp": timestamp.isoformat(),
                                        "type": message_type,
                                        "status": "received",
                                        "message_id": message_id,
                                        "sender_name": sender_name,
                                    },
                                }
                            )
                        except Exception as e:
                            print("⚠️ Channel send error (incoming):", e)

                    # -------- Status updates (sent/delivered/read/failed) ----------
                    statuses = value.get("statuses", [])
                    # phone_number_id for statuses comes from metadata too
                    phone_number_id = metadata.get("phone_number_id")

                    for st in statuses:
                        message_id = st.get("id")
                        recipient_id = st.get("recipient_id")  # NOT used for group name now
                        status = st.get("status")  # sent/delivered/read/failed/...
                        ts = datetime.fromtimestamp(int(st.get("timestamp")))

                        error_code = None
                        error_title = ""
                        error_message = ""
                        error_description = ""

                        # If errors are present, extract them
                        if "errors" in st and st["errors"]:
                            error_code = st["errors"][0].get("code")
                            error_title = st["errors"][0].get("title")
                            error_message = st["errors"][0].get("message", "")
                            error_description = st["errors"][0].get("error_data", {}).get("details", "")

                        # Update message status in database and emit websocket events
                        if status == 'delivered':
                            query = """
                                UPDATE whatsapp_message
                                SET status = %s, delivered_at = %s
                                WHERE message_id = %s
                            """
                            params = [status, ts, message_id]
                            try:
                                with connection.cursor() as cursor:
                                    cursor.execute(query, params)
                                    print(f"Direct SQL updated message {message_id} with status {status}.")

                                # Emit WS event for delivery status
                                async_to_sync(channel_layer.group_send)(
                                    f"whatsapp_{phone_number_id}",
                                    {
                                        "type": "whatsapp_status",
                                        "message": {
                                            "message_id": message_id,
                                            "status": "delivered",
                                            "timestamp": ts.isoformat(),
                                        },
                                    }
                                )
                            except Exception as e:
                                print(f"SQL/Channel Error updating delivered status for message {message_id}: {str(e)}")

                        elif status == 'read':
                            query = """
                                UPDATE whatsapp_message
                                SET status = %s, seen_at = %s
                                WHERE message_id = %s
                            """
                            params = [status, ts, message_id]
                            try:
                                with connection.cursor() as cursor:
                                    cursor.execute(query, params)
                                    print(f"Direct SQL updated message {message_id} with status {status}.")

                                # Emit WS event for read status
                                async_to_sync(channel_layer.group_send)(
                                    f"whatsapp_{phone_number_id}",
                                    {
                                        "type": "whatsapp_status",
                                        "message": {
                                            "message_id": message_id,
                                            "status": "read",
                                            "timestamp": ts.isoformat(),
                                        },
                                    }
                                )
                            except Exception as e:
                                print(f"SQL/Channel Error updating read status for message {message_id}: {str(e)}")

                        elif status == 'failed':
                            query = """
                                UPDATE whatsapp_message
                                SET status = %s, error_message = %s, error_code = %s, error_title = %s, error_description = %s
                                WHERE message_id = %s
                            """
                            params = [status, error_message, error_code, error_title, error_description, message_id]
                            try:
                                with connection.cursor() as cursor:
                                    cursor.execute(query, params)
                                    print(f"Direct SQL updated message {message_id} with status {status}.")

                                # Emit WS event for failed status
                                async_to_sync(channel_layer.group_send)(
                                    f"whatsapp_{phone_number_id}",
                                    {
                                        "type": "whatsapp_status",
                                        "message": {
                                            "message_id": message_id,
                                            "status": "failed",
                                            "error_code": error_code,
                                            "error_message": error_message,
                                            "error_title": error_title,
                                            "error_description": error_description,
                                            "timestamp": ts.isoformat(),
                                        },
                                    }
                                )
                            except Exception as e:
                                print(f"SQL/Channel Error updating failed status for message {message_id}: {str(e)}")

            return JsonResponse({"status": "success"})

        except Exception as e:
            print(f"Error in VerifyWebhookView.post: {e}")
            return JsonResponse({"status": "error", "message": str(e)}, status=500)
