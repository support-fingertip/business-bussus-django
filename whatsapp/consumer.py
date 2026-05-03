from channels.generic.websocket import AsyncWebsocketConsumer
from urllib.parse import parse_qs
import json

class WhatsappConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # Example: ws://yourdomain/ws/whatsapp/?phone_number_id=123456789
        query_str = self.scope["query_string"].decode()
        params = parse_qs(query_str)

        self.phone_number_id = params.get("phone_number_id", [None])[0]

        if not self.phone_number_id:
            # No identifier = no connection
            await self.close()
            return

        self.group_name = f"whatsapp_{self.phone_number_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )

    # Incoming WhatsApp messages from webhook -> frontend
    async def whatsapp_message(self, event):
        # event["message"] comes from group_send
        await self.send(text_data=json.dumps({
            "event": "incoming_message",
            "data": event["message"],
        }))

    # Status updates (delivered/read/failed) from webhook -> frontend
    async def whatsapp_status(self, event):
        await self.send(text_data=json.dumps({
            "event": "status_update",
            "data": event["message"],
        }))
