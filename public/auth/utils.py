# otp/proof.py
from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.conf import settings
from django.db import connection
from datetime import datetime, timezone

PENDING, VERIFIED, EXPIRED, CANCELLED = 0, 1, 2, 3

def validate_proof(verification_proof: str, max_age_seconds=900):
    signer = TimestampSigner(key=settings.SECRET_KEY, salt="otp-proof")
    try:
        payload = signer.unsign(verification_proof, max_age=max_age_seconds)
        # payload: verification_id:email:purpose
        verification_id, email, purpose = payload.split(":", 2)
        return {"ok": True, "verification_id": verification_id, "email": email, "purpose": purpose}
    except SignatureExpired:
        return {"ok": False, "error": "expired"}
    except BadSignature:
        return {"ok": False, "error": "invalid"}

def ensure_verified_and_consume(verification_id: str):
    """Ensure the session is VERIFIED (not expired), then consume it once."""
    now = datetime.now(timezone.utc)
    with connection.cursor() as cur:
        # lock row and re-check
        cur.execute("""
          SELECT status, expires_at FROM otp_verification_sessions
          WHERE id=%s FOR UPDATE
        """, [verification_id])
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "not_found"}
        status, expires_at = row
        if status != VERIFIED or now > expires_at:
            return {"ok": False, "error": "not_verified"}
        # consume (one-time use)
        cur.execute("""
          UPDATE otp_verification_sessions SET status=%s, updated_at=%s WHERE id=%s
        """, [CANCELLED, now, verification_id])
    return {"ok": True}
