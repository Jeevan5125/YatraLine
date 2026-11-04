from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from .. import models
from ..database import get_db

router = APIRouter(prefix="/api/admin", tags=["admin"])
# NOTE: add real auth/role checks (e.g. an admin-only dependency) before
# exposing this outside a trusted demo environment.


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    total_bookings = db.query(models.Booking).count()
    confirmed = db.query(models.Booking).filter(
        models.Booking.status == models.BookingStatus.CONFIRMED
    ).count()
    revenue = db.query(func.coalesce(func.sum(models.Booking.total), 0.0)).filter(
        models.Booking.status == models.BookingStatus.CONFIRMED
    ).scalar()
    seats_booked = db.query(models.SeatInventory).filter(
        models.SeatInventory.status == models.SeatStatus.BOOKED
    ).count()
    total_seats = db.query(func.coalesce(func.sum(models.Bus.total_seats), 0)).scalar()
    total_routes = db.query(models.Route).count()

    success_rate = round((confirmed / total_bookings) * 100, 1) if total_bookings else 0.0
    occupancy = round((seats_booked / total_seats) * 100, 1) if total_seats else 0.0

    # avg time from booking creation to payment verification, for confirmed bookings
    confirmed_bookings = db.query(models.Booking).filter(
        models.Booking.status == models.BookingStatus.CONFIRMED
    ).all()
    completion_times = []
    for b in confirmed_bookings:
        verified_log = db.query(models.AuditLog).filter(
            models.AuditLog.action == "PAYMENT_VERIFIED",
            models.AuditLog.entity_id == b.pnr,
        ).first()
        if verified_log:
            completion_times.append((verified_log.timestamp - b.created_at).total_seconds())
    avg_completion_seconds = round(sum(completion_times) / len(completion_times)) if completion_times else 0

    return {
        "total_bookings": total_bookings,
        "confirmed_bookings": confirmed,
        "success_rate_pct": success_rate,
        "avg_completion_seconds": avg_completion_seconds,
        "total_revenue": revenue,
        "seats_booked": seats_booked,
        "fleet_occupancy_pct": occupancy,
        "total_routes": total_routes,
    }


@router.get("/fleet")
def fleet(db: Session = Depends(get_db)):
    routes = db.query(models.Route).all()
    return [
        {
            "bus_number": r.bus.bus_number,
            "operator": r.bus.operator,
            "route": f"{r.from_city} -> {r.to_city}",
            "bus_type": r.bus.bus_type,
            "fare": r.fare,
        }
        for r in routes
    ]


@router.get("/bookings")
def all_bookings(db: Session = Depends(get_db), limit: int = 100):
    bookings = db.query(models.Booking).order_by(
        models.Booking.created_at.desc()
    ).limit(limit).all()
    return [
        {
            "pnr": b.pnr,
            "user": b.user.name,
            "route": f"{b.route.from_city} -> {b.route.to_city}",
            "seats": [p.seat_number for p in b.passengers],
            "status": b.status,
            "total": b.total,
            "created_at": b.created_at,
        }
        for b in bookings
    ]


@router.get("/logs")
def audit_logs(db: Session = Depends(get_db), limit: int = 200):
    logs = db.query(models.AuditLog).order_by(
        models.AuditLog.timestamp.desc()
    ).limit(limit).all()
    return [
        {
            "action": l.action, "entity": l.entity, "entity_id": l.entity_id,
            "details": l.details, "timestamp": l.timestamp, "user_id": l.user_id,
        }
        for l in logs
    ]
