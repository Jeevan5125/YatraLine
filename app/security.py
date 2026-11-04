"""
Security helpers: OTP generation & hashing, HMAC "gateway" signature
verification for the mock payment flow, and hold-token helpers.

Real deployment notes:
- Set OTP_PEPPER and RAZORPAY_KEY_SECRET via environment variables, never
  hardcode them.
- Swap MockPaymentGateway for the real Razorpay SDK; keep verify_signature's
  shape (order_id|payment_id signed with the secret) since that's the same
  scheme Razorpay uses.
"""
import hashlib
import hmac
import os
import secrets
import string

OTP_PEPPER = os.environ.get("OTP_PEPPER", "dev-only-pepper-change-me")
GATEWAY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "dev-only-gateway-secret")
OTP_DELIVERY_MODE = os.environ.get("OTP_DELIVERY_MODE", "dev")  # "dev" | "production"

OTP_TTL_SECONDS = 5 * 60
OTP_RESEND_COOLDOWN_SECONDS = 30
SEAT_HOLD_TTL_SECONDS = 10 * 60


def generate_otp(length: int = 6) -> str:
    return "".join(secrets.choice(string.digits) for _ in range(length))


def hash_otp(otp: str, verification_id: str) -> str:
    """Salted hash so a DB leak doesn't expose usable OTPs."""
    msg = f"{verification_id}:{otp}:{OTP_PEPPER}".encode()
    return hashlib.sha256(msg).hexdigest()


def verify_otp_hash(otp: str, verification_id: str, stored_hash: str) -> bool:
    candidate = hash_otp(otp, verification_id)
    return hmac.compare_digest(candidate, stored_hash)


def deliver_otp(email: str, phone: str, otp: str) -> None:
    """
    Dev mode: log it (and the API returns it in the response for convenience).
    Production: plug in an email/SMS provider here (SES, Twilio, MSG91, etc.)
    and DO NOT return the OTP in the API response.
    """
    if OTP_DELIVERY_MODE == "dev":
        print(f"[DEV OTP] to {email} / {phone}: {otp}")
    else:
        # TODO: integrate real email/SMS provider
        raise NotImplementedError("Configure a production OTP delivery provider")


def new_hold_token() -> str:
    return secrets.token_hex(16)


def sign_order(order_id: str, payment_id: str) -> str:
    """Mimics Razorpay's HMAC-SHA256(order_id|payment_id, key_secret) scheme."""
    msg = f"{order_id}|{payment_id}".encode()
    return hmac.new(GATEWAY_SECRET.encode(), msg, hashlib.sha256).hexdigest()


def verify_signature(order_id: str, payment_id: str, signature: str) -> bool:
    expected = sign_order(order_id, payment_id)
    return hmac.compare_digest(expected, signature)
