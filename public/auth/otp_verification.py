import json
import os
import uuid
import secrets
import time
from datetime import datetime, timedelta, timezone
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To

from django.conf import settings
from django.core.cache import caches
from django.core.mail import EmailMultiAlternatives, get_connection
from django.db import connection, transaction
from django.http import JsonResponse, HttpRequest
from django.contrib.auth.hashers import make_password, check_password
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django_ratelimit.decorators import ratelimit
import logging

logger = logging.getLogger(__name__)
cache = caches["default"]

PENDING, VERIFIED, EXPIRED, CANCELLED = 0, 1, 2, 3

def _now():
    return datetime.now(timezone.utc)

def _rate_key(prefix, value):
    return f"otp:{prefix}:{value}"

def _incr_with_ttl(key, ttl, amount=1):
    try:
        v = cache.get(key)
        if v is None:
            cache.set(key, amount, ttl)
            return amount
        cache.incr(key, amount)
        return cache.get(key)
    except Exception:
        return 1  # fail-open minimal

def _throttle(email, ip):
    email_hits = _incr_with_ttl(_rate_key("email_hour", email), 3600)
    ip_hits = _incr_with_ttl(_rate_key("ip_hour", ip), 3600)
    if email_hits > int(getattr(settings, "RATE_LIMIT_PER_EMAIL_PER_HOUR", 10)) or \
        ip_hits > int(getattr(settings, "RATE_LIMIT_PER_IP_PER_HOUR", 30)):
        return True
    return False

def _generate_otp(length):
    # digits only; change to alnum if you prefer
    n = 10 ** length
    otp = str(secrets.randbelow(n)).zfill(length)
    return otp

def _send_email(email, company, otp, ttl_sec, purpose):
    logger.info(f"Sending OTP email to {email} for {str(purpose).replace('_', ' ').capitalize()}")
    subject = f"{company} verification code"
    text = f"Your {purpose} verification code is {otp}. It expires in {ttl_sec//60} minutes."
    html = f"""
        <p>Use this code to complete your <b>{purpose}</b>:</p>
        <h2 style="letter-spacing:2px">{otp}</h2>
        <p>This code expires in {ttl_sec//60} minutes. If you didn’t request it, you can ignore this email.</p>
    """
    
    api_key = os.getenv("SENDGRID_API_KEY")
    sender_email = 'support@bussus.com'
    sg = SendGridAPIClient(api_key)
    
    message = Mail(
                from_email=Email(sender_email),
                to_emails=[To(email)],
                subject=subject,
                html_content=html
            )
    
    try:
        response = sg.send(message)
        logger.info(f"Sent OTP email to {email} — Status: {response.status_code}")
        if response.status_code != 202:
            logger.warning(f"SendGrid warning: {response.status_code}")
        return 1  # success
    except Exception as e:
        logger.error(f"Error sending email to {email}: {str(e)}")
        raise
    # from_email = getattr(settings, "DEFAULT_FROM_EMAIL", None) or getattr(settings, "EMAIL_HOST_USER", None)

    # try:
    #     with get_connection(
    #         backend=getattr(settings, "EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend"),
    #         host=settings.EMAIL_HOST,
    #         port=settings.EMAIL_PORT,
    #         username=settings.EMAIL_HOST_USER,
    #         password=settings.EMAIL_HOST_PASSWORD,
    #         use_tls=getattr(settings, "EMAIL_USE_TLS", False),
    #         use_ssl=getattr(settings, "EMAIL_USE_SSL", False),
    #         timeout=getattr(settings, "EMAIL_TIMEOUT", 15),
    #     ) as conn:
    #         msg = EmailMultiAlternatives(subject, text, from_email, [email], connection=conn)
    #         msg.attach_alternative(html, "text/html")
    #         sent = msg.send(fail_silently=False)
    #         return sent  # 1 = success
    # except Exception as e:
    #     print(f"Error sending email to {email}: {e}")
    #     # bubble up or handle as you prefer
    #     raise

def _anti_enum_response():
    # Always ambiguous to prevent user/email enumeration
    return JsonResponse({"ok": True, "message": "If the email is valid, a code has been sent."})

@ratelimit(key='ip', rate='5/m', method='POST')
def start_otp(request: HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    try:
        body = json.loads(request.body.decode())
        email = (body.get("email") or "").strip().lower()
        purpose = (body.get("purpose") or "login").strip().lower()
        company = "Bussus"
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not email:
        return JsonResponse({"error": "email required"}, status=400)

    ip = request.META.get("REMOTE_ADDR", "")
    ua = request.META.get("HTTP_USER_AGENT", "")
    
    if purpose == 'sign_up':
        try:
            cur = connection.cursor()
            cur.execute("SELECT 1 FROM users WHERE email=%s", [email])
            res = cur.fetchone()
            if res:
                return JsonResponse({"ok": False, "error": "email_exists"}, status=409)
        except Exception as e:
            logger.error(f"Error checking existing user: {str(e)}")

    if _throttle(email, ip):
        # Do not reveal throttling specifics (anti-enum)
        return _anti_enum_response()
    otp = _generate_otp(settings.OTP_LENGTH)
    try:
        otp_hash = make_password(otp)
    except Exception as e:
        logger.error(f"Error hashing OTP: {str(e)}")
        return JsonResponse({"error": "Internal error"}, status=500)
    verification_id = str(uuid.uuid4())
    now = _now()
    expires = now + timedelta(seconds=settings.OTP_TTL_SECONDS)
    logger.debug(f"OTP generated for {email} ({purpose}), expires in {settings.OTP_TTL_SECONDS}s")

    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("""
                INSERT INTO otp_verification_sessions
                (id, email, purpose, otp_hash, expires_at, created_at, updated_at, attempts,
                max_attempts, status, last_sent_at, send_count, ip_address, user_agent, metadata)
                VALUES (%s,%s,%s,%s,%s,%s,%s,0,%s,%s,%s,1,%s,%s,%s)
            """, [
                verification_id, email, purpose, otp_hash, expires, now, now,
                settings.OTP_MAX_ATTEMPTS, PENDING, now, ip, ua, json.dumps({})
            ])

    # Resend cooldown state (per verification id)
    cache.set(_rate_key("resend", verification_id), 1, settings.OTP_RESEND_COOLDOWN)

    # Send email
    try:
        _send_email(email, company, otp, settings.OTP_TTL_SECONDS, purpose)
    except Exception:
        # Do not leak sending failures (anti-enum)
        pass

    # Return opaque id only
    return JsonResponse({"ok": True, "verification_id": verification_id})

@ratelimit(key='ip', rate='10/m', method='POST')
def verify_otp(request: HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    try:
        body = json.loads(request.body.decode())
        verification_id = body.get("verification_id")
        otp = (body.get("otp") or "").strip()
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not verification_id or not otp:
        return JsonResponse({"error": "verification_id and otp required"}, status=400)

    now = _now()

    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("""
                SELECT email, purpose, otp_hash, expires_at, attempts, max_attempts, status
                FROM otp_verification_sessions WHERE id=%s FOR UPDATE
            """, [verification_id])
            row = cur.fetchone()
            if row is None:
                # avoid enumeration
                return JsonResponse({"ok": False, "message": "Invalid code or expired"}, status=400)

            email, purpose, otp_hash, expires_at, attempts, max_attempts, status = row

            if status != PENDING:
                if status == VERIFIED:
                    return JsonResponse({"ok": True, "message": "Already verified"}, status=200)
                elif status == EXPIRED:
                    cur.execute("UPDATE otp_verification_sessions SET status=%s, updated_at=%s WHERE id=%s",
                                [EXPIRED, now, verification_id])
                    return JsonResponse({"ok": False, "message": "Invalid code or expired"}, status=400)
                return JsonResponse({"ok": False, "message": "Invalid code or expired"}, status=400)

            if now > expires_at:
                cur.execute("UPDATE otp_verification_sessions SET status=%s, updated_at=%s WHERE id=%s",
                            [EXPIRED, now, verification_id])
                return JsonResponse({"ok": False, "message": "Invalid code or expired"}, status=400)

            if attempts >= max_attempts:
                cur.execute("UPDATE otp_verification_sessions SET status=%s, updated_at=%s WHERE id=%s",
                            [CANCELLED, now, verification_id])
                return JsonResponse({"ok": False, "message": "Too many attempts"}, status=429)

            # Verify
            ok = check_password(otp, otp_hash)
            cur.execute("UPDATE otp_verification_sessions SET attempts=attempts+1, updated_at=%s WHERE id=%s",
                        [now, verification_id])

            if not ok:
                return JsonResponse({"ok": False, "message": "Invalid code or expired"}, status=400)

            # Mark verified
            cur.execute("UPDATE otp_verification_sessions SET status=%s, updated_at=%s WHERE id=%s",
                        [VERIFIED, now, verification_id])
    # Return a short-lived signed proof for other services
    
    signer = TimestampSigner(key=settings.SECRET_KEY, salt="otp-proof")
    proof_payload = f"{verification_id}:{email}:{purpose}"
    verification_proof = signer.sign(proof_payload)  # can validate later with max_age

    return JsonResponse({
        "ok": True,
        "email": email,
        "purpose": purpose,
        "verification_proof": verification_proof  # keep private; send via HTTPS only
    })

@ratelimit(key='ip', rate='3/m', method='POST')
def resend_otp(request: HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    try:
        body = json.loads(request.body.decode())
        verification_id = body.get("verification_id")
        company = "Bussus"
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    if not verification_id:
        return JsonResponse({"error": "verification_id required"}, status=400)

    # cooldown
    if cache.get(_rate_key("resend", verification_id)):
        return JsonResponse({"ok": False, "message": "Please wait before resending"}, status=429)

    now = _now()
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("""
                SELECT email, purpose, expires_at, status, send_count
                FROM otp_verification_sessions WHERE id=%s FOR UPDATE
            """, [verification_id])
            row = cur.fetchone()
            if not row:
                return _anti_enum_response()
            email, purpose, expires_at, status, send_count = row

            if status != PENDING or now > expires_at or send_count >= settings.OTP_MAX_SENDS:
                return _anti_enum_response()

            # generate new code and extend expiry (optional; here we keep same expiry)
            otp = _generate_otp(settings.OTP_LENGTH)
            otp_hash = make_password(otp)
            cur.execute("""
                UPDATE otp_verification_sessions
                SET otp_hash=%s, updated_at=%s, last_sent_at=%s, send_count=send_count+1
                WHERE id=%s
            """, [otp_hash, now, now, verification_id])

    cache.set(_rate_key("resend", verification_id), 1, settings.OTP_RESEND_COOLDOWN)

    try:
        _send_email(email, company, otp, int((expires_at - now).total_seconds()), purpose)
    except Exception:
        pass
    return JsonResponse({"ok": True, "message": "If eligible, a new code has been sent."})

def status_otp(request: HttpRequest):
    # GET /api/otp/status?verification_id=...
    verification_id = request.GET.get("verification_id")
    if not verification_id:
        return JsonResponse({"error": "verification_id required"}, status=400)
    with connection.cursor() as cur:
        cur.execute("SELECT status FROM otp_verification_sessions WHERE id=%s", [verification_id])
        row = cur.fetchone()
        if not row:
            return JsonResponse({"ok": False, "status": "unknown"})
        status = row[0]
    mapping = {PENDING: "pending", VERIFIED: "verified", EXPIRED: "expired", CANCELLED: "cancelled"}
    return JsonResponse({"ok": True, "status": mapping.get(status, "unknown")})

def cancel_otp(request: HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)
    try:
        body = json.loads(request.body.decode())
        verification_id = body.get("verification_id")
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not verification_id:
        return JsonResponse({"error": "verification_id required"}, status=400)

    with connection.cursor() as cur:
        cur.execute("UPDATE otp_verification_sessions SET status=%s, updated_at=%s WHERE id=%s AND status=%s",
                    [CANCELLED, _now(), verification_id, PENDING])
    return JsonResponse({"ok": True})
