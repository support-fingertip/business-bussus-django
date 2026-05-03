import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import transaction, connection
from django.contrib.auth.hashers import make_password
from django_ratelimit.decorators import ratelimit

from public.auth.utils import ensure_verified_and_consume, validate_proof

@csrf_exempt
@ratelimit(key='ip', rate='3/h', method='POST')
def set_password_with_proof(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    
    try:
        body = json.loads(request.body.decode())
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    
    email = (body.get("email") or "").strip().lower()
    new_password = body.get("password") or ""
    verification_proof = body.get("verification_proof") or ""

    if not email or '@' not in email:
        return JsonResponse({"error": "Valid email is required"}, status=400)
    if not new_password or len(new_password) < 8:
        return JsonResponse({"error": "Password must be at least 8 characters"}, status=400)
    if not verification_proof:
        return JsonResponse({"error": "verification_proof is required"}, status=400)

    v = validate_proof(verification_proof, max_age_seconds=900)
    if not v.get("ok") or v["purpose"] != "reset_password" or v["email"] != email:
        return JsonResponse({"ok": False, "error": "invalid_proof"}, status=400)

    c = ensure_verified_and_consume(v["verification_id"])
    if not c.get("ok"):
        return JsonResponse({"ok": False, "error": c.get("error")}, status=400)

    pwd_hash = make_password(new_password, hasher='pbkdf2_sha256')

    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("UPDATE users SET password=%s WHERE email=%s", [pwd_hash, email])
            if cur.rowcount == 0:
                return JsonResponse({"ok": False, "error": "user_not_found"}, status=404)

    return JsonResponse({"ok": True})
