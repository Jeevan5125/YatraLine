from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from .. import models, schemas
from ..database import get_db

router = APIRouter(prefix="/api/buses", tags=["buses"])


@router.get("/cities", response_model=List[str])
def list_cities(db: Session = Depends(get_db)):
    froms = db.query(models.Route.from_city).distinct()
    tos = db.query(models.Route.to_city).distinct()
    cities = {c for (c,) in froms} | {c for (c,) in tos}
    return sorted(cities)


@router.get("/search", response_model=List[schemas.RouteSearchResult])
def search_buses(
    from_city: str = Query(...),
    to_city: str = Query(...),
    travel_date: Optional[date] = Query(None),
    db: Session = Depends(get_db),
):
    query = (
        db.query(models.Route)
        .join(models.Bus)
        .filter(
            func.lower(models.Route.from_city) == from_city.lower(),
            func.lower(models.Route.to_city) == to_city.lower(),
        )
    )
    if travel_date:
        query = query.filter(func.date(models.Route.departure) == travel_date)

    results = []
    for route in query.all():
        available = (
            db.query(models.SeatInventory)
            .filter(
                models.SeatInventory.route_id == route.id,
                models.SeatInventory.status == models.SeatStatus.AVAILABLE,
            )
            .count()
        )
        results.append(schemas.RouteSearchResult(
            route_id=route.id,
            bus_number=route.bus.bus_number,
            operator=route.bus.operator,
            bus_type=route.bus.bus_type,
            from_city=route.from_city,
            to_city=route.to_city,
            departure=route.departure,
            arrival=route.arrival,
            fare=route.fare,
            seats_available=available,
        ))
    return results


@router.get("/{route_id}/seats", response_model=List[schemas.SeatOut])
def get_seats(route_id: int, db: Session = Depends(get_db)):
    route = db.query(models.Route).get(route_id)
    if not route:
        raise HTTPException(404, "Route not found")

    # release any expired holds before reporting status
    expired = db.query(models.SeatInventory).filter(
        models.SeatInventory.route_id == route_id,
        models.SeatInventory.status == models.SeatStatus.HELD,
        models.SeatInventory.hold_expires_at < datetime.utcnow(),
    ).all()
    for seat in expired:
        seat.status = models.SeatStatus.AVAILABLE
        seat.held_by_session = None
        seat.hold_expires_at = None
    if expired:
        db.commit()

    seats = db.query(models.SeatInventory).filter(
        models.SeatInventory.route_id == route_id
    ).order_by(models.SeatInventory.seat_number).all()
    return seats
