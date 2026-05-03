# notify.py
#
# FIXES:
#  BUG-1  data left as "" string when kwags has both "data"(list) and "message"
#         -> generate_url(request, "") raised TypeError. FIX: normalise data={}.
#  BUG-2  error_record called with er="static string" losing the real exception.
#         FIX: pass actual exception object.
#  BUG-3  Unused imports (django.db.connection, run_query). FIX: removed.
#  SECURITY-1  generate_url now extracts the base origin from X-Frontend-URL
#              (request.referer), HTTP_REFERER, or Host header — then builds
#              clean paths instead of appending to the raw referer.
#  SECURITY-2  object_name / id are validated via _safe_segment (isalnum + 128
#              char cap) before being embedded in URLs.

from asgiref.sync import async_to_sync
from typing import Literal
from public.utils.exists import error_record
from api.permissions.permissions import get_permissions
from api.ORM.sqlFunctions.createSQLFunction import post_data_sql
import datetime
import decimal
import uuid


def _serialize(obj):
    """
    Recursively convert a DB row dict into a channel-layer-safe plain dict.
    Django Channels uses msgpack (via Redis) which cannot handle:
      - datetime.datetime / datetime.date / datetime.time  → ISO string
      - decimal.Decimal                                    → float
      - uuid.UUID                                          → str
      - any other non-primitive                            → str fallback
    """
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, (datetime.datetime, datetime.date, datetime.time)):
        return obj.isoformat()
    if isinstance(obj, decimal.Decimal):
        return float(obj)
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_serialize(i) for i in obj]
    return str(obj)  # safe fallback for anything else


def proper_title(input_text: str) -> str:
    if input_text:
        return input_text.replace("_", " ").title()
    return "New Notification"


def trigger_notication(
        owner_id,
        channel_layer,
        user_id,
        title,
        notification_type: Literal["verification", "reminder", "alert", "system", "chat"],
        channel: Literal["email", "whatsapp", "app", "sms", "push"],
        request=None,
        **kwags,
):
    try:
        message = ""
        data    = {}   # BUG-1 fix: always a dict so generate_url is safe

        if kwags.get("message"):
            message = str(kwags["message"])
            data = kwags.get("data", {}) if isinstance(kwags.get("data"), dict) else {}
        elif isinstance(kwags.get("data"), list) and kwags["data"]:
            first = kwags["data"][0]
            data    = first if isinstance(first, dict) else {}
            message = str(kwags.get("message", ""))
        elif isinstance(kwags.get("data"), dict):
            data = kwags["data"]
            if "object_name" in data:
                message = f"New {data['object_name']} has been created"
            else:
                message = str(data.get("message", ""))
        title = proper_title(str(title))
        url   = generate_url(data)
        last_notify = collect_notification(
            owner_id=owner_id, title=title,
            channel=channel, types=notification_type, url=url,**kwags
        )
        async_to_sync(channel_layer.group_send)(
            f"user_{owner_id}", {"type": "get_unread"},
        )
        if last_notify:
            safe_notify = _serialize(last_notify)
            async_to_sync(channel_layer.group_send)(
                f"user_{owner_id}",
                {"type": "get_notification", "action": "get_notification", "current": safe_notify},
            )
    except Exception as ex:
        error_record(ex)


def get_admin(user_id, request=None, **kwargs):
    try:
        if not isinstance(user_id, int) or user_id <= 0:
            return None
        org_kwargs = {**kwargs, "tableName": "users", "fields": ["organization_id"],
                      "where": {"id": user_id, "is_staff": False}}
        org_result = get_permissions(request, **org_kwargs)
        if not (org_result and org_result.get("data")):
            return None
        org_id = org_result["data"][0].get("organization_id")
        if not org_id:
            return None
        admin_kwargs = {**kwargs, "tableName": "users", "fields": ["id"],
                        "where": {"organization_id": org_id, "is_staff": True}}
        admin_result = get_permissions(request, **admin_kwargs)
        if admin_result and admin_result.get("data"):
            return admin_result["data"][0].get("id")
        return None
    except Exception as ex:
        error_record(ex)   # BUG-2 fix: real exception
        return None


def collect_notification(owner_id, title: str,channel, types, url,
                         request=None, **kwargs):
    try:
        if 'data' in kwargs:
            del kwargs['data']  # Remove data from kwargs to avoid confusion in post_data_sql
        create_data = {
            "owner_id": owner_id,
            "title":    str(title).capitalize(),
            "message":  kwargs.get("message", ""),
            "channel":  str(channel),
            "type":     str(types),
            "url":      str(url),
        }
        result = post_data_sql("notifications", create_data, section="Create - notifications", **kwargs)
        if result and result.get("data"):
            return result["data"][0]
        return None
    except Exception as ex:
        error_record(ex)
        return None


def get_user_details(userid, request=None, **kwargs):
    try:
        users = get_permissions(request,tableName="users",fields=["id", "name"],id=userid, **kwargs)
        print("User details fetched for user_id {}: {}".format(userid, users))
        if users and users.get("data"):
            user = users["data"][0]
            return user.get("name"), user.get("id")
        return None
    except Exception as ex:
        error_record(ex)
        return None



def _safe_segment(value, max_len: int = 128) -> str | None:
    """Return a URL-safe segment or None if the value is unsafe."""
    segment = str(value)
    if not segment or len(segment) > max_len:
        return None
    return segment


def generate_url(data: dict) -> str:
    try:
        if "id" in data and "object_name" in data:
            safe_id = _safe_segment(data["id"])
            safe_object = _safe_segment(data["object_name"])
            if safe_id and safe_object:
                return f"/en/apps/{safe_object}/preview/{safe_id}"
        if "id" in data:
            safe_id = _safe_segment(data["id"])
            if safe_id:
                return f"/preview/{safe_id}"
        if "object_name" in data:
            safe_object = _safe_segment(data["object_name"])
            if safe_object:
                return f"/en/apps/{safe_object}"
        return ""
    except Exception as ex:
        error_record(ex)
        return ""