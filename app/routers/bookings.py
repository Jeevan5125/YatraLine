from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/bookings", tags=["bookings"])

CONVENIENCE_FEE_FLAT = 25.0


@router.post("", response_model=schemas.BookingOut)
def create_booking(payload: schemas.CreateBookingRequest, db: Session = Depends(get_db)):
    route = db.query(models.Route).get(payload.route_id)
    if not route:
        raise HTTPException(404, "Route not found")

    user = db.query(models.User).get(payload.user_id)
    if not user:
        raise HTTPException(404, "User not found")

    seat_numbers = [p.seat_number for p in payload.passengers]
    seats = db.query(models.SeatInventory).filter(
        models.SeatInventory.route_id == payload.route_id,
        models.SeatInventory.seat_number.in_(seat_numbers),
    ).all()

    if len(seats) != len(seat_numbers):
        raise HTTPException(404, "One or more seats not found for this route")

    bad = [
        s.seat_number for s in seats
        if not (s.status == models.SeatStatus.HELD and s.held_by_session == payload.hold_token)
    ]
    if bad:
        raise HTTPException(
            409,
            f"Seat(s) not held by this session (hold may have expired): {', '.join(bad)}",
        )

    base_fare = route.fare * len(seat_numbers)
    total = base_fare + CONVENIENCE_FEE_FLAT

    booking = models.Booking(
        user_id=user.id,
        route_id=route.id,
        status=models.BookingStatus.PENDING,
        base_fare=base_fare,
        convenience_fee=CONVENIENCE_FEE_FLAT,
        total=total,
        hold_token=payload.hold_token,
    )
    db.add(booking)
    db.flush()

    for p in payload.passengers:
        db.add(models.Passenger(
            booking_id=booking.id, name=p.name, age=p.age,
            gender=p.gender, seat_number=p.seat_number,
        ))

    # Seats stay HELD (not yet BOOKED) until OTP + payment both succeed.
    # They flip to BOOKED only in payments.verify_payment.
    db.add(models.AuditLog(
        user_id=user.id, action="BOOKING_CREATED", entity="Booking",
        entity_id=booking.pnr, details=f"seats={seat_numbers}",
    ))
    db.commit()
    db.refresh(booking)
    return booking


@router.post("/{pnr}/confirm-otp", response_model=schemas.BookingOut)
def confirm_otp_for_booking(pnr: str, verification_id: str, db: Session = Depends(get_db)):
    """
    Links a verified OTPVerification to a booking and advances its state
    machine from PENDING -> AWAITING_PAYMENT. Called right after
    /api/auth/verify-otp succeeds on the frontend.
    """
    booking = db.query(models.Booking).filter(models.Booking.pnr == pnr).first()
    if not booking:
        raise HTTPException(404, "Booking not found")
    if booking.status != models.BookingStatus.PENDING:
        raise HTTPException(400, f"Booking is not awaiting OTP (status={booking.status})")

    verification = db.query(models.OTPVerification).filter(
        models.OTPVerification.verification_id == verification_id
    ).first()
    if not verification or not verification.verified:
        raise HTTPException(400, "OTP has not been verified for this session")
    if verification.user_id != booking.user_id:
        raise HTTPException(403, "OTP verification does not belong to this booking's user")

    booking.otp_verified = True
    booking.status = models.BookingStatus.AWAITING_PAYMENT
    db.add(models.AuditLog(
        user_id=booking.user_id, action="BOOKING_OTP_CONFIRMED",
        entity="Booking", entity_id=booking.pnr,
    ))
    db.commit()
    db.refresh(booking)
    return booking


@router.get("/{pnr}", response_model=schemas.BookingDetail)
def get_booking(pnr: str, db: Session = Depends(get_db)):
    booking = db.query(models.Booking).filter(models.Booking.pnr == pnr).first()
    if not booking:
        raise HTTPException(404, "Booking not found")
    route, bus = booking.route, booking.route.bus
    return schemas.BookingDetail(
        pnr=booking.pnr, status=booking.status, base_fare=booking.base_fare,
        convenience_fee=booking.convenience_fee, total=booking.total,
        operator=bus.operator, bus_type=bus.bus_type,
        from_city=route.from_city, to_city=route.to_city,
        departure=route.departure, arrival=route.arrival,
        passengers=booking.passengers,
        payment_method=booking.payment.method if booking.payment else None,
        created_at=booking.created_at,
    )


@router.get("/my/{user_id}", response_model=list[schemas.BookingDetail])
def my_bookings(user_id: int, db: Session = Depends(get_db)):
    bookings = db.query(models.Booking).filter(models.Booking.user_id == user_id).order_by(
        models.Booking.created_at.desc()
    ).all()
    out = []
    for booking in bookings:
        route, bus = booking.route, booking.route.bus
        out.append(schemas.BookingDetail(
            pnr=booking.pnr, status=booking.status, base_fare=booking.base_fare,
            convenience_fee=booking.convenience_fee, total=booking.total,
            operator=bus.operator, bus_type=bus.bus_type,
            from_city=route.from_city, to_city=route.to_city,
            departure=route.departure, arrival=route.arrival,
            passengers=booking.passengers,
            payment_method=booking.payment.method if booking.payment else None,
            created_at=booking.created_at,
        ))
    return out
