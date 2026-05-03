# public/utils/error_log.py
import json
import traceback
from django.db import connection

def log_tenant_error(*, user_id=None, email=None, organization_name=None,
                     schema_name=None, step=None, error=None, payload=None):
    error_message = str(error) if error else None
    error_details = traceback.format_exc()

    payload_json = None
    if payload is not None:
        try:
            payload_json = json.dumps(payload)
        except Exception:
            # fallback to string if payload isn't JSON-serializable
            payload_json = json.dumps({"raw": str(payload)})

    with connection.cursor() as cur:
        cur.execute("""
            INSERT INTO public.tenant_provisioning_errors
                (user_id, email, organization_name, schema_name,
                 step, error_message, error_details, payload, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
        """, [
            user_id,
            email,
            organization_name,
            schema_name,
            step,
            error_message,
            error_details,
            payload_json
        ])
