from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _log(db: Session, user_id, action, entity=None, entity_id=None, details=None):
    db.add(models.AuditLog(
        user_id=user_id, action=action, entity=entity,
        entity_id=str(entity_id) if entity_id is not None else None, details=details,
    ))


@router.post("/request-otp", response_model=schemas.RequestOTPResponse)
def request_otp(payload: schemas.RequestOTP, db: Session = Depends(get_db)):
    # find-or-create the user by email
    user = db.query(models.User).filter(models.User.email == payload.email).first()
    if not user:
        user = models.User(name=payload.name, email=payload.email, phone=payload.phone)
        db.add(user)
        db.flush()

    # enforce a resend cooldown per user+purpose
    existing = (
        db.query(models.OTPVerification)
        .filter(
            models.OTPVerification.user_id == user.id,
            models.OTPVerification.purpose == payload.purpose,
            models.OTPVerification.verified == False,  # noqa: E712
        )
        .order_by(models.OTPVerification.created_at.desc())
        .first()
    )
    if existing and existing.last_sent_at:
        elapsed = (datetime.utcnow() - existing.last_sent_at).total_seconds()
        if elapsed < security.OTP_RESEND_COOLDOWN_SECONDS:
            wait = int(security.OTP_RESEND_COOLDOWN_SECONDS - elapsed)
            raise HTTPException(429, f"Please wait {wait}s before requesting another OTP")

    otp = security.generate_otp()
    verification_id = models.gen_uuid()  # generated up front so we can hash before insert
    verification = models.OTPVerification(
        verification_id=verification_id,
        user_id=user.id,
        purpose=payload.purpose,
        otp_hash=security.hash_otp(otp, verification_id),
        expires_at=datetime.utcnow() + timedelta(seconds=security.OTP_TTL_SECONDS),
        resend_count=(existing.resend_count + 1) if existing else 0,
    )
    db.add(verification)
    db.flush()

    security.deliver_otp(user.email, user.phone, otp)
    _log(db, user.id, "OTP_REQUESTED", "OTPVerification", verification.verification_id)
    db.commit()

    return schemas.RequestOTPResponse(
        verification_id=verification.verification_id,
        expires_in_seconds=security.OTP_TTL_SECONDS,
        dev_otp=otp if security.OTP_DELIVERY_MODE == "dev" else None,
    )


@router.post("/verify-otp", response_model=schemas.VerifyOTPResponse)
def verify_otp(payload: schemas.VerifyOTP, db: Session = Depends(get_db)):
    verification = (
        db.query(models.OTPVerification)
        .filter(models.OTPVerification.verification_id == payload.verification_id)
        .first()
    )
    if not verification:
        raise HTTPException(404, "Verification session not found")
    if verification.verified:
        raise HTTPException(400, "This OTP has already been used")
    if datetime.utcnow() > verification.expires_at:
        raise HTTPException(400, "OTP expired — please request a new one")
    if verification.attempts >= verification.max_attempts:
        raise HTTPException(429, "Too many incorrect attempts — request a new OTP")

    verification.attempts += 1

    if not security.verify_otp_hash(payload.otp, verification.verification_id, verification.otp_hash):
        db.commit()
        remaining = verification.max_attempts - verification.attempts
        raise HTTPException(400, f"Incorrect OTP — {remaining} attempt(s) left")

    verification.verified = True
    _log(db, verification.user_id, "OTP_VERIFIED", "OTPVerification", verification.verification_id)
    db.commit()

    return schemas.VerifyOTPResponse(
        verified=True, user_id=verification.user_id, message="OTP verified successfully"
    )
