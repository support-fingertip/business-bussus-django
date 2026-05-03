# consumers.py
# Token auth via first WebSocket message — NOT in the URL query string.
#
# IMPORT STRATEGY — nothing that touches Django/DRF is imported at module level.
# Uvicorn imports asgi.py -> routing.py -> consumer.py before Django settings are
# loaded. Any top-level DRF/project import triggers ImproperlyConfigured.
# All such imports are deferred to lazy wrappers or inside async methods.

# ── Safe top-level imports (stdlib + channels only) ──────────────────────────
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from urllib.parse import parse_qs
import json


# ── Lazy wrappers for Django-dependent modules ────────────────────────────────
def _run_query(*args, **kwargs):
    from api.telephony.views import run_query
    return run_query(*args, **kwargs)


def _error_record(ex):
    from public.utils.exists import error_record
    error_record(ex)


# ─────────────────────────────────────────────────────────────────────────────
_ALLOWED_CLIENT_ACTIONS = frozenset({
    "get_unread",
    "read_update",
    "read_notify"
})

# Seconds to wait for the auth message before closing the connection
_AUTH_TIMEOUT_SECONDS = 10


class _JWTAuthMixin:
    @database_sync_to_async
    def get_user_from_db(self, token):
        from rest_framework_simplejwt.authentication import JWTAuthentication
        from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
        jwt_auth = JWTAuthentication()
        validated_token = jwt_auth.get_validated_token(token)
        return jwt_auth.get_user(validated_token)


class TelephonyConsumer(_JWTAuthMixin, AsyncWebsocketConsumer):
    async def connect(self):
        # Accept the raw TCP/WS upgrade immediately — auth happens in receive()
        self._authenticated = False
        await self.accept()

    async def receive(self, text_data):
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            return

        # ── Auth handshake ───────────────────────────────────────────────────
        if not self._authenticated:
            if payload.get("action") != "authenticate":
                # First message MUST be the auth frame — reject anything else
                await self.send(text_data=json.dumps({
                    "action": "auth_failed",
                    "message": "First message must be authenticate",
                }))
                await self.close(code=4003)
                return

            token = payload.get("token", "")
            try:
                from rest_framework_simplejwt.tokens import UntypedToken
                from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
                UntypedToken(token)
                self.user = await self.get_user_from_db(token)
            except (TokenError, InvalidToken, Exception):
                await self.send(text_data=json.dumps({
                    "action": "auth_failed",
                    "message": "Invalid or expired token",
                }))
                await self.close(code=4003)
                return
            self._authenticated = True
            self.group_name = f"telephony_group_{self.user.id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.send(text_data=json.dumps({"action": "authenticated"}))
            return

        # Telephony consumer does not accept client messages beyond auth
        # (all events are server-push only)

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def show_popup(self, event):
        await self.send(text_data=json.dumps({"action": "popup", **event["data"]}))

    async def incoming(self, event):
        await self.send(text_data=json.dumps({**event["data"]}))

    async def call_connecting(self, event):
        await self.send(text_data=json.dumps({"action": "connect", **event["data"]}))

    async def hang_up(self, event):
        await self.send(text_data=json.dumps({"action": "hangup", **event["data"]}))

    async def close_popup(self, event):
        await self.send(text_data=json.dumps({"action": "closepopup", "data": {}}))

    async def error_responses(self, event):
        await self.send(text_data=json.dumps({"action": "error", **event}))

    async def call_accepted(self, event):
        await self.send(text_data=json.dumps({"action": "call_accepted"}))


class Notification(_JWTAuthMixin, AsyncWebsocketConsumer):
    async def connect(self):
        self._authenticated = False
        await self.accept()

    async def receive(self, text_data):
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            return

        action = payload.get("action", "")

        # ── Auth handshake ───────────────────────────────────────────────────
        if not self._authenticated:
            if action != "authenticate":
                await self.send(text_data=json.dumps({
                    "action": "auth_failed",
                    "message": "First message must be authenticate",
                }))
                await self.close(code=4003)
                return

            token = payload.get("token", "")
            try:
                from rest_framework_simplejwt.tokens import UntypedToken
                from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
                UntypedToken(token)
                self.user = await self.get_user_from_db(token)
            except (TokenError, InvalidToken, Exception):
                await self.send(text_data=json.dumps({
                    "action": "auth_failed",
                    "message": "Invalid or expired token",
                }))
                await self.close(code=4003)
                return

            self._authenticated = True
            self.group_name = f"user_{self.user.id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.send(text_data=json.dumps({"action": "authenticated"}))
            return

        # ── Normal client messages (post-auth) ───────────────────────────────
        if action not in _ALLOWED_CLIENT_ACTIONS:
            await self.send(text_data=json.dumps({
                "action": "error",
                "message": f"Unknown action: {action}",
            }))
            return

        await self.channel_layer.group_send(
            self.group_name,
            {"type": action, **payload},
        )

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def get_unread(self, event):
        try:
            result  = await self.fetch_unread_notifications()
            total   = await self.get_total_notifications()
            overall = await self.total_notification()
            await self.send(text_data=json.dumps({
                "action":  "get_unread",
                "data":    result,
                "total":   total[0],
                "overall": overall[0],
            }))
        except Exception as ex:
            await self._send_error(ex)

    async def read_update(self, event):
        await self.mark_notify_as_read()
        await self.send(text_data=json.dumps({"action": "read_update", "msg": "Updated"}))

    async def read_notify(self, event):
        notification_id = event.get("id")
        if not notification_id:
            return
        await self.read_notification(notification_id)
        await self.get_unread(event)

    async def get_notification(self, event):
        total   = await self.get_total_notifications()
        overall = await self.total_notification()
        payload = {**event, "total": total[0], "overall": overall[0]}
        await self.send(text_data=json.dumps(payload))

    @database_sync_to_async
    def mark_notify_as_read(self):
        try:
            org_query = """
                SELECT database_schema FROM organizations WHERE id = %s
            """
            organization_schema = _run_query(org_query, [self.user.organization_id])
            _run_query("UPDATE notifications SET status='read' WHERE owner_id=%s",
                      [self.user.id],
                      schema=organization_schema[0].get("database_schema"))
        except Exception as ex:
            _error_record(ex)

    @database_sync_to_async
    def fetch_unread_notifications(self):
        try:
            org_query = """
                SELECT database_schema FROM organizations WHERE id = %s
            """
            organization_schema = _run_query(org_query, [self.user.organization_id])
            query = """
                SELECT id, owner_id, title, message, channel, type,
                       status, priority,
                       CAST(created_at AS text) AS created_at, url
                FROM notifications
                WHERE owner_id = %s
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
            """
            return _run_query(query, [self.user.id, 10, 0],schema=organization_schema[0].get("database_schema"))
        except Exception as ex:
            _error_record(ex)
            return []

    @database_sync_to_async
    def get_total_notifications(self):
        org_query = """
            SELECT database_schema FROM organizations WHERE id = %s
        """
        organization_schema = _run_query(org_query, [self.user.organization_id])
        return _run_query(
            "SELECT COUNT(*) AS notify_count FROM notifications WHERE owner_id=%s AND status=%s",
            [self.user.id, "pending"],
            schema=organization_schema[0].get("database_schema")
        )

    @database_sync_to_async
    def total_notification(self):
        org_query = """
            SELECT database_schema FROM organizations WHERE id = %s
        """
        organization_schema = _run_query(org_query, [self.user.organization_id])
        return _run_query(
            "SELECT COUNT(*) AS overall FROM notifications WHERE owner_id=%s",
            [self.user.id],
            schema=organization_schema[0].get("database_schema")
        )

    @database_sync_to_async
    def read_notification(self, notification_id):
        org_query = """
            SELECT database_schema FROM organizations WHERE id = %s
        """
        organization_schema = _run_query(org_query, [self.user.organization_id])
        _run_query(
            "UPDATE notifications SET status='read' WHERE id=%s AND owner_id=%s",
            [notification_id, self.user.id],
            schema=organization_schema[0].get("database_schema")
        )

    async def _send_error(self, exc):
        await self.send(text_data=json.dumps({"action": "error", "message": str(exc)}))


class WhatsappConsumer(_JWTAuthMixin, AsyncWebsocketConsumer):
    async def connect(self):
        # phone_number_id still comes from URL (not sensitive) — only token moves to message
        query_str    = self.scope["query_string"].decode()
        params       = parse_qs(query_str)
        raw_phone_id = params.get("phone_number_id", [None])[0]

        if not raw_phone_id or not raw_phone_id.isdigit():
            await self.close(code=4002)
            return

        self.phone_number_id  = raw_phone_id
        self._authenticated   = False
        await self.accept()

    async def receive(self, text_data):
        try:
            payload = json.loads(text_data)
        except json.JSONDecodeError:
            return

        # ── Auth handshake ───────────────────────────────────────────────────
        if not self._authenticated:
            if payload.get("action") != "authenticate":
                await self.send(text_data=json.dumps({
                    "action": "auth_failed",
                    "message": "First message must be authenticate",
                }))
                await self.close(code=4003)
                return

            token = payload.get("token", "")
            try:
                from rest_framework_simplejwt.tokens import UntypedToken
                from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
                UntypedToken(token)
                self.user = await self.get_user_from_db(token)
            except (TokenError, InvalidToken, Exception):
                await self.send(text_data=json.dumps({
                    "action": "auth_failed",
                    "message": "Invalid or expired token",
                }))
                await self.close(code=4003)
                return

            self._authenticated = True
            self.group_name = f"whatsapp_{self.phone_number_id}"
            await self.channel_layer.group_add(self.group_name, self.channel_name)
            await self.send(text_data=json.dumps({"action": "authenticated"}))
            return

    async def disconnect(self, code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def whatsapp_message(self, event):
        await self.send(text_data=json.dumps({
            "event": "incoming_message",
            "data":  event["message"],
        }))

    async def whatsapp_status(self, event):
        await self.send(text_data=json.dumps({
            "event": "status_update",
            "data":  event["message"],
        }))