"""
Server-authoritative seat locking.

This replaces the old client-side flow where the browser pushed straight
into a `booked` array after payment. Here:
  1. POST /hold atomically checks + reserves seats for a short TTL.
  2. Booking creation later converts HELD -> BOOKED for the same hold_token.
  3. DELETE /release lets the client give back seats it no longer wants.
  4. Expired holds are lazily reclaimed (see buses.get_seats and here).
"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .. import models, schemas, security
from ..database import get_db

router = APIRouter(prefix="/api/seats", tags=["seats"])


def _reclaim_expired(db: Session, route_id: int):
    expired = db.query(models.SeatInventory).filter(
        models.SeatInventory.route_id == route_id,
        models.SeatInventory.status == models.SeatStatus.HELD,
        models.SeatInventory.hold_expires_at < datetime.utcnow(),
    ).all()
    for seat in expired:
        seat.status = models.SeatStatus.AVAILABLE
        seat.held_by_session = None
        seat.hold_expires_at = None


@router.post("/hold", response_model=schemas.HoldSeatsResponse)
def hold_seats(payload: schemas.HoldSeatsRequest, db: Session = Depends(get_db)):
    _reclaim_expired(db, payload.route_id)

    hold_token = payload.hold_token or security.new_hold_token()
    expires_at = datetime.utcnow() + timedelta(seconds=security.SEAT_HOLD_TTL_SECONDS)

    seats = db.query(models.SeatInventory).filter(
        models.SeatInventory.route_id == payload.route_id,
        models.SeatInventory.seat_number.in_(payload.seat_numbers),
    ).with_for_update(read=False).all()  # row lock; SQLite ignores this but Postgres honors it

    found_numbers = {s.seat_number for s in seats}
    missing = set(payload.seat_numbers) - found_numbers
    if missing:
        raise HTTPException(404, f"Unknown seat(s): {', '.join(sorted(missing))}")

    unavailable = [
        s.seat_number for s in seats
        if s.status == models.SeatStatus.BOOKED
        or (s.status == models.SeatStatus.HELD and s.held_by_session != hold_token)
    ]
    if unavailable:
        raise HTTPException(409, f"Seat(s) no longer available: {', '.join(unavailable)}")

    for s in seats:
        s.status = models.SeatStatus.HELD
        s.held_by_session = hold_token
        s.hold_expires_at = expires_at

    db.commit()
    return schemas.HoldSeatsResponse(
        hold_token=hold_token,
        held_seats=sorted(found_numbers),
        hold_expires_at=expires_at,
    )


@router.delete("/release")
def release_seats(payload: schemas.ReleaseSeatsRequest, db: Session = Depends(get_db)):
    seats = db.query(models.SeatInventory).filter(
        models.SeatInventory.seat_number.in_(payload.seat_numbers),
        models.SeatInventory.held_by_session == payload.hold_token,
        models.SeatInventory.status == models.SeatStatus.HELD,
    ).all()
    for s in seats:
        s.status = models.SeatStatus.AVAILABLE
        s.held_by_session = None
        s.hold_expires_at = None
    db.commit()
    return {"released": [s.seat_number for s in seats]}
