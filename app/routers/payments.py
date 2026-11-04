"""
Payments — real Razorpay Orders API integration for order creation, plus
signature verification for confirming a payment actually went through.

Flow:
  1. create_order: booking must be AWAITING_PAYMENT (i.e. OTP already
     verified). We call Razorpay's Orders API server-side (HTTP Basic Auth
     with your Key ID/Secret) to mint a REAL order — checkout.js validates
     the order_id against Razorpay's own servers the instant it loads, so a
     locally-generated fake ID fails immediately, before any card is even
     entered. This is what a "Payment Failed" dialog on load (rather than
     after entering card details) usually means.
  2. verify_payment: checks the HMAC signature Razorpay sends back. Only on
     success do seats flip HELD -> BOOKED and the booking flip
     AWAITING_PAYMENT -> CONFIRMED. Nothing is confirmed until a signature
     actually checks out — no `setTimeout(...900)` fake confirmations.
"""
import os
import secrets

import requests
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db

router = APIRouter(prefix="/api/payments", tags=["payments"])

RAZORPAY_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_dev_key")
RAZORPAY_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "dev-only-gateway-secret")
RAZORPAY_ORDERS_URL = "https://api.razorpay.com/v1/orders"

# Whether real keys look configured (vs. still on the built-in placeholders).
# When not configured, we fall back to a locally-generated order id so the
# rest of the app is still exercisable via the /_dev/sign-mock-payment
# endpoint — but the real Razorpay checkout widget will always reject that,
# since it isn't a real order id from Razorpay's system.
USING_REAL_KEYS = (
    RAZORPAY_KEY_ID != "rzp_test_dev_key"
    and RAZORPAY_KEY_SECRET != "dev-only-gateway-secret"
)


@router.post("/create-order", response_model=schemas.CreateOrderResponse)
def create_order(payload: schemas.CreateOrderRequest, db: Session = Depends(get_db)):
    booking = db.query(models.Booking).filter(models.Booking.pnr == payload.pnr).first()
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking.status != models.BookingStatus.AWAITING_PAYMENT:
        raise HTTPException(400, f"Booking not ready for payment (status={booking.status})")

    amount_paise = int(round(booking.total * 100))

    if USING_REAL_KEYS:
        try:
            resp = requests.post(
                RAZORPAY_ORDERS_URL,
                auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET),
                json={
                    "amount": amount_paise,
                    "currency": "INR",
                    "receipt": booking.pnr,
                    "payment_capture": 1,
                },
                timeout=10,
            )
        except requests.RequestException as e:
            raise HTTPException(502, f"Could not reach Razorpay: {e}")

        if resp.status_code >= 300:
            # Surfaces Razorpay's own error message (e.g. invalid key,
            # auth failure) instead of a generic 500.
            detail = resp.json().get("error", {}).get("description", resp.text)
            raise HTTPException(502, f"Razorpay order creation failed: {detail}")

        order_id = resp.json()["id"]
    else:
        # No real keys configured yet — see USING_REAL_KEYS above. This lets
        # /_dev/sign-mock-payment exercise the rest of the flow, but the real
        # checkout widget will fail on this order id (as expected).
        order_id = f"order_{secrets.token_hex(10)}"

    payment = booking.payment
    if payment is None:
        payment = models.Payment(booking_id=booking.id, amount=booking.total)
        db.add(payment)
    payment.gateway_order_id = order_id
    payment.status = models.PaymentStatus.CREATED
    db.commit()

    return schemas.CreateOrderResponse(
        gateway_order_id=order_id, amount=booking.total, key_id=RAZORPAY_KEY_ID,
    )


@router.post("/verify", response_model=schemas.VerifyPaymentResponse)
def verify_payment(payload: schemas.VerifyPaymentRequest, db: Session = Depends(get_db)):
    booking = db.query(models.Booking).filter(models.Booking.pnr == payload.pnr).first()
    if not booking:
        raise HTTPException(404, "Booking not found")

    payment = booking.payment
    if not payment or payment.gateway_order_id != payload.gateway_order_id:
        raise HTTPException(400, "Order mismatch")

    valid = security.verify_signature(
        payload.gateway_order_id, payload.gateway_payment_id, payload.gateway_signature
    )
    if not valid:
        payment.status = models.PaymentStatus.FAILED
        db.add(models.AuditLog(
            user_id=booking.user_id, action="PAYMENT_SIGNATURE_INVALID",
            entity="Booking", entity_id=booking.pnr,
        ))
        db.commit()
        raise HTTPException(400, "Payment signature verification failed")

    payment.gateway_payment_id = payload.gateway_payment_id
    payment.gateway_signature = payload.gateway_signature
    payment.status = models.PaymentStatus.SUCCESS
    if payload.method:
        payment.method = payload.method

    # Only now do seats become permanently booked.
    seat_numbers = [p.seat_number for p in booking.passengers]
    seats = db.query(models.SeatInventory).filter(
        models.SeatInventory.route_id == booking.route_id,
        models.SeatInventory.seat_number.in_(seat_numbers),
    ).all()
    for s in seats:
        s.status = models.SeatStatus.BOOKED
        s.held_by_session = None
        s.hold_expires_at = None

    booking.status = models.BookingStatus.CONFIRMED
    db.add(models.AuditLog(
        user_id=booking.user_id, action="PAYMENT_VERIFIED", entity="Booking",
        entity_id=booking.pnr, details=f"payment_id={payload.gateway_payment_id}",
    ))
    db.commit()

    return schemas.VerifyPaymentResponse(
        status="CONFIRMED", pnr=booking.pnr, message="Payment verified, booking confirmed",
    )


@router.post("/_dev/sign-mock-payment", include_in_schema=False)
def dev_sign_mock_payment(payload: dict):
    """
    DEV/DEMO ONLY. Real Razorpay checkout.js runs in the browser, collects
    card/UPI details, and hands back payment_id + signature itself — the
    server never generates them. This stub exists only so this demo can
    exercise the full /create-order -> /verify round trip without a live
    Razorpay account. It only works while USING_REAL_KEYS is False, since a
    real order_id is only mintable by Razorpay itself. Remove before going
    anywhere near production.
    """
    if USING_REAL_KEYS:
        raise HTTPException(403, "Real Razorpay keys are configured — use the actual checkout widget instead")
    if security.OTP_DELIVERY_MODE != "dev":
        raise HTTPException(403, "Dev-only endpoint disabled outside dev mode")
    order_id = payload.get("order_id")
    payment_id = payload.get("payment_id")
    if not order_id or not payment_id:
        raise HTTPException(400, "order_id and payment_id required")
    signature = security.sign_order(order_id, payment_id)
    return {"signature": signature}


@router.post("/webhook")
def payment_webhook(payload: dict, db: Session = Depends(get_db)):
    """
    Placeholder for the gateway's server-to-server webhook (recommended in
    production as a backstop in case the client never calls /verify, e.g. the
    user closes the tab right after paying). Verify the webhook signature
    header per the gateway's docs before trusting this payload.
    """
    db.add(models.AuditLog(action="PAYMENT_WEBHOOK_RECEIVED", details=str(payload)[:500]))
    db.commit()
    return {"received": True}
