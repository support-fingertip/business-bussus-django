from typing import List, Dict, Any, Callable, Optional
from dataclasses import dataclass
from api.BL.whatsapp.utils import get_whatsapp
from api.permissions.permissions import get_permissions, post_permission
from whatsapp.chat_list import get_chats_with_last_message
from whatsapp.templates import create_facebook_template, get_templates
from whatsapp.utils import get_long_lived_token, get_whatsapp_phone_numbers, register_account, subscribe_to_webhooks
from api.ORM.sqlFunctions.getQueryBuilder import build_query

@dataclass
class WhatsAppService:
    request: Any
    kwargs: Dict[str, Any]
    
    def _q(self, name:str, default: Optional[str] = None) -> Any:
        """Get a query parameter from the request."""
        if hasattr(self.request, 'GET'):
            return self.request.GET.get(name, default)
        return default
    
    def _require(self, value: Any, name: str) -> Any:
        """Require a non-empty value; raise a helpful error otherwise."""
        if value in (None, "", []):
            raise ValueError(f"Missing required parameter: {name}")
        return value
    # ---------- Public endpoints used by your current block ----------
    def chats(self) -> List[Dict[str, Any]]:
        """
        GET /whatsapp/chats?contact=...
        """
        contact = self._require(self._q("contact"), "contact")
        chat_list = get_chats_with_last_message(contact)
        return chat_list

    def templates(self) -> Any:
        """
        GET /whatsapp/templates
        """
        waba_id = "577630585438281"
        try:
            waba_id = self._require(self._q("id"), "id")
        except ValueError:
            pass
        if len(waba_id) > 20:
            raise ValueError("WABA ID cannot be empty.")
        return get_templates(waba_id)
    
    
    def create_template(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        name = payload.get('name')
        header = payload.get('header', None)
        body = payload.get('body', None)
        footer = payload.get('footer', None)
        # Construct the components dynamically
        components = []

        if header:
            components.append({
                "type": "header",
                "format": "TEXT",
                "text": header,
            })   
        if body:
            components.append({
                "type": "body",
                "text": body,
            })     
        if footer:
            components.append({
                "type": "footer",
                "text": footer,
            })   
        
        return create_facebook_template(name,"en_US", components, **self.kwargs)

    def accounts(self) -> List[Dict[str, Any]]:
        """
        GET /whatsapp/accounts
        """
        org = self.kwargs.get("org")
        if not isinstance(org, dict):
            raise ValueError("Expected 'org' in kwargs (dict).")
        # result = get_permissions(
        #     self.request,
        #     tableName="whatsapp_accounts",
        #     where=[{"field": "organization_id", "operator": "=", "value": org.get("id")}],
        #     **self.kwargs,
        # )
        result = build_query(
            tableName="whatsapp_accounts",
            where=[{"field": "organization_id", "operator": "=", "value": org.get("id")}],
            schema="public",
            fields=["id", "display_name", "phone_number", "status", "waba_id","business_phone_number_id"] ,
        )
        return result
    
    def register_account(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /whatsapp/accounts  JSON: { ...accountPayload }
        """
        payload_ = {
            "messaging_product": "whatsapp",
            "pin": payload.get("pin"),
        }
        number_id = payload.get("phone_number_id")
        return register_account(payload_, number_id)
    
    def create_account(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST /whatsapp/accounts/create  JSON: { ...accountPayload }
        """
        waba_id = payload.get("waba_id")
        result = get_whatsapp_phone_numbers(waba_id)
        access_token = get_long_lived_token(short_lived_token=payload.get("code"))
        subscribe_to_webhooks(waba_id, access_token)
        phone_numbers = result.get("data", [])
        selected_number = {}
        for i in phone_numbers:
            if i.get("id") == payload.get("phone_number_id"):
                selected_number = i
                break       
                
        payload_ = {
            "display_name": selected_number.get("verified_name", ""),
            "business_phone_number_id": payload.get("phone_number_id"),
            "business_id": payload.get("business_id"),
            "waba_id": payload.get("waba_id"),
            "status": "active",
            "organization_id": self.kwargs.get("org", {}).get("id"),   
            "phone_number": selected_number.get("display_phone_number", ""),
            "token": access_token
        }
        result = post_permission(
            self.request,
            table_name="whatsapp_accounts",
            create_data=payload_,
            **self.kwargs,
        )
        return result
        

    def leads(self) -> List[Dict[str, Any]]:
        """
        GET /whatsapp/leads?search=...
        """
        limit = self.request.GET.get("limit", 10)
        offset = self.request.GET.get("offset", 0)
        search_term = self.request.GET.get("search", None)
        filters = [{"field":"is_deleted", "operator":"=", "value": False}]
        if search_term:
            filters.extend(
                [
                    {"field": "name", "operator": "ilike", "value": f"%{search_term}%"},
                    {"field": "phone", "operator": "ilike", "value": f"%{search_term}%"},
                    {"field": "email", "operator": "ilike", "value": f"%{search_term}%"},
                    {"field": "company", "operator": "ilike", "value": f"%{search_term}%"},
                ]
            )
        result = get_permissions(
            self.request,
            tableName="leads",
            where = filters,
            fields=["name", "phone", "email", "company"],
            limit=limit,
            offset=offset,
            **self.kwargs,
        )
        return result.get("data", [])

    def default(self) -> Any:
        """
        Fallback: GET /whatsapp
        """
        return get_whatsapp(self.request, **self.kwargs)

    # ---------- Extra methods you can wire up later ----------
    def send_text(self) -> Dict[str, Any]:
        """
        POST /whatsapp/send-text?to=...  JSON: { "message": "..." }
        """
        to = self._require(self._q("to"), "to")
        payload = getattr(self.request, "data", {}) or getattr(self.request, "POST", {})
        message = self._require(payload.get("message"), "message")
        # TODO: Replace with your actual send implementation
        # result = send_text_message_api(to=to, message=message, **self.kwargs)
        result = {"ok": True, "to": to, "message": message}
        return result

    def send_media(self) -> Dict[str, Any]:
        """
        POST /whatsapp/send-media?to=...  JSON: { "media_url": "...", "caption": "..." }
        """
        to = self._require(self._q("to"), "to")
        payload = getattr(self.request, "data", {}) or getattr(self.request, "POST", {})
        media_url = self._require(payload.get("media_url"), "media_url")
        caption = payload.get("caption")
        # TODO: Replace with real implementation
        result = {"ok": True, "to": to, "media_url": media_url, "caption": caption}
        return result

    def chat_history(self) -> List[Dict[str, Any]]:
        """
        GET /whatsapp/chat-history?contact=...&limit=50&before=<iso-ts>
        """
        contact = self._require(self._q("contact"), "contact")
        limit = int(self._q("limit", "50"))
        before = self._q("before")
        # TODO: Replace with your data source
        history = []  # fetch_chat_history(contact, limit=limit, before=before, **self.kwargs)
        return history

    def mark_read(self) -> Dict[str, Any]:
        """
        POST /whatsapp/mark-read?contact=...
        """
        contact = self._require(self._q("contact"), "contact")
        # TODO: Replace with real implementation
        return {"ok": True, "contact": contact, "status": "read"}

    def archive_chat(self) -> Dict[str, Any]:
        """
        POST /whatsapp/archive?contact=...
        """
        contact = self._require(self._q("contact"), "contact")
        # TODO: Replace with real implementation
        return {"ok": True, "contact": contact, "status": "archived"}

    def upsert_template(self) -> Dict[str, Any]:
        """
        POST /whatsapp/templates  JSON: { ...templatePayload }
        or PUT  /whatsapp/templates/:id
        """
        payload = getattr(self.request, "data", {}) or getattr(self.request, "POST", {})
        # TODO: Replace with your persistence logic
        return {"ok": True, "template": payload}

    def delete_template(self) -> Dict[str, Any]:
        """
        DELETE /whatsapp/templates?id=...
        """
        template_id = self._require(self._q("id"), "id")
        # TODO: Replace with your delete logic
        return {"ok": True, "deleted_id": template_id}

    # ---------- Dispatcher ----------
    def dispatch(self, another_object: Optional[str]) -> Any:
        """
        Central routing for /whatsapp/<another_object?>
        Add new routes here without touching the view.
        """
        routes: Dict[str, Callable[[], Any]] = {
            "chats": self.chats,
            "templates": self.templates,
            "accounts": self.accounts,
            "leads": self.leads,
            "send-text": self.send_text,
            "send-media": self.send_media,
            "chat-history": self.chat_history,
            "mark-read": self.mark_read,
            "archive": self.archive_chat,
            "upsert-template": self.upsert_template,
            "delete-template": self.delete_template,
        }
        handler = routes.get(another_object or "", self.default)
        return handler()
        
    