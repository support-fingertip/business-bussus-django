from django.core.signing import TimestampSigner, BadSignature, SignatureExpired
from django.conf import settings

def validate_verification_proof(verification_proof: str, max_age_seconds=900):
    signer = TimestampSigner(settings.SECRET_KEY, salt="otp-proof")
    try:
        payload = signer.unsign(verification_proof, max_age=max_age_seconds)
        verification_id, email, purpose = payload.split(":", 2)
        return {"ok": True, "verification_id": verification_id, "email": email, "purpose": purpose}
    except SignatureExpired:
        return {"ok": False, "error": "expired"}
    except BadSignature:
        return {"ok": False, "error": "invalid"}
