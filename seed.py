"""
Seeds the SQLite DB with the exact bus/route/seat dataset that the original
YatraLine frontend hardcoded client-side, so the backend-integrated version
looks identical on first run.

Run: python seed.py   (delete yatraline.db first to reseed from scratch)
"""
from datetime import datetime, timedelta

from app.database import Base, engine, SessionLocal
from app import models

Base.metadata.create_all(bind=engine)
db = SessionLocal()

# Same rows as the frontend's original `BUSES` array. Departure/arrival are
# stored as full datetimes (anchored to "today") but the frontend only ever
# displays the time-of-day — city pair matters for search, not the date.
TODAY = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)


def dt(hhmm: str, next_day: bool = False) -> datetime:
    h, m = map(int, hhmm.split(":"))
    base = TODAY + timedelta(days=1 if next_day else 0)
    return base.replace(hour=h, minute=m)


BUSES = [
    dict(bus_number="YL101", operator="Parveen Travels", bus_type="AC Sleeper",
         from_city="Chennai", to_city="Coimbatore", dep="22:00", arr="05:30", arr_next_day=True,
         fare=850, total_seats=40,
         booked=["1A", "1B", "2C", "3D", "5A", "6B", "6C", "8D", "9A"]),
    dict(bus_number="YL102", operator="Parveen Travels", bus_type="AC Sleeper",
         from_city="Coimbatore", to_city="Chennai", dep="21:30", arr="05:00", arr_next_day=True,
         fare=850, total_seats=40,
         booked=["1C", "2A", "4B", "4C", "7D"]),
    dict(bus_number="YL201", operator="KPN Travels", bus_type="AC Seater",
         from_city="Chennai", to_city="Madurai", dep="21:00", arr="04:30", arr_next_day=True,
         fare=650, total_seats=40,
         booked=["1A", "1B", "1C", "1D", "2A", "2B", "3C", "9A", "9B", "10D"]),
    dict(bus_number="YL202", operator="KPN Travels", bus_type="AC Seater",
         from_city="Madurai", to_city="Chennai", dep="22:00", arr="05:30", arr_next_day=True,
         fare=650, total_seats=40,
         booked=["4A", "5B"]),
    dict(bus_number="YL301", operator="SRM Travels", bus_type="AC Seater",
         from_city="Chennai", to_city="Tiruchirappalli", dep="22:30", arr="04:00", arr_next_day=True,
         fare=550, total_seats=40,
         booked=["1A", "1B", "1C", "1D", "2A", "2B", "2C", "2D", "3A", "3B", "3C", "3D", "6A"]),
    dict(bus_number="YL302", operator="SRM Travels", bus_type="AC Seater",
         from_city="Tiruchirappalli", to_city="Chennai", dep="23:00", arr="04:30", arr_next_day=True,
         fare=550, total_seats=40,
         booked=["5A", "5B", "5C"]),
    dict(bus_number="YL401", operator="Universal Travels", bus_type="Non-AC Seater",
         from_city="Coimbatore", to_city="Madurai", dep="07:00", arr="11:30", arr_next_day=False,
         fare=350, total_seats=40,
         booked=["2D", "3A", "3B", "8C"]),
    dict(bus_number="YL402", operator="Universal Travels", bus_type="Non-AC Seater",
         from_city="Madurai", to_city="Coimbatore", dep="15:00", arr="19:30", arr_next_day=False,
         fare=350, total_seats=40,
         booked=[]),
    dict(bus_number="YL501", operator="Sri Lakshmi Travels", bus_type="AC Seater",
         from_city="Chennai", to_city="Vellore", dep="06:00", arr="09:00", arr_next_day=False,
         fare=250, total_seats=40,
         booked=["1A", "1B", "10C", "10D"]),
    dict(bus_number="YL502", operator="Sri Lakshmi Travels", bus_type="AC Seater",
         from_city="Vellore", to_city="Chennai", dep="17:00", arr="20:00", arr_next_day=False,
         fare=250, total_seats=40,
         booked=["4D", "5A", "5B", "5C", "5D", "6A"]),
    dict(bus_number="YL601", operator="Cholan Roadways", bus_type="Non-AC Seater",
         from_city="Salem", to_city="Chennai", dep="08:00", arr="14:00", arr_next_day=False,
         fare=400, total_seats=40,
         booked=["1A", "2B"]),
    dict(bus_number="YL602", operator="Cholan Roadways", bus_type="Non-AC Seater",
         from_city="Chennai", to_city="Salem", dep="13:00", arr="19:00", arr_next_day=False,
         fare=400, total_seats=40,
         booked=[]),
]


def seat_codes(total: int):
    rows = total // 4
    cols = ["A", "B", "C", "D"]
    return [f"{r}{c}" for r in range(1, rows + 1) for c in cols]


if db.query(models.Bus).count() > 0:
    print("DB already seeded — skipping. Delete yatraline.db to reseed.")
else:
    for b in BUSES:
        bus = models.Bus(
            bus_number=b["bus_number"], operator=b["operator"],
            bus_type=b["bus_type"], total_seats=b["total_seats"],
        )
        db.add(bus)
        db.flush()

        departure = dt(b["dep"])
        arrival = dt(b["arr"], next_day=b["arr_next_day"])
        route = models.Route(
            bus_id=bus.id, from_city=b["from_city"], to_city=b["to_city"],
            departure=departure, arrival=arrival, fare=b["fare"],
        )
        db.add(route)
        db.flush()

        booked_set = set(b["booked"])
        for code in seat_codes(b["total_seats"]):
            db.add(models.SeatInventory(
                route_id=route.id, seat_number=code,
                status=models.SeatStatus.BOOKED if code in booked_set else models.SeatStatus.AVAILABLE,
            ))

    db.commit()
    print(f"Seeded {len(BUSES)} buses/routes with seat inventory matching the original frontend dataset.")

db.close()
