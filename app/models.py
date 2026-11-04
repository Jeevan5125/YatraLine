"""
ORM models for YatraLine.

Design notes:
- Seat state lives in the DB (SeatInventory), not the browser — the server is
  authoritative for seat locking, as called out in the architecture.
- OTPVerification never stores the raw OTP, only a salted hash + expiry.
- Booking has a `status` state machine: PENDING -> AWAITING_PAYMENT -> CONFIRMED
  (or EXPIRED / CANCELLED), and only a verified Payment can move it to CONFIRMED.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Enum, Text
)
from sqlalchemy.orm import relationship

from .database import Base


def gen_uuid() -> str:
    return uuid.uuid4().hex


class BookingStatus(str, enum.Enum):
    PENDING = "PENDING"                # seat(s) held, passenger form in progress
    AWAITING_PAYMENT = "AWAITING_PAYMENT"  # OTP verified, payment order created
    CONFIRMED = "CONFIRMED"            # payment verified
    EXPIRED = "EXPIRED"                # hold/timer lapsed
    CANCELLED = "CANCELLED"


class SeatStatus(str, enum.Enum):
    AVAILABLE = "AVAILABLE"
    HELD = "HELD"          # temporarily locked while a user completes checkout
    BOOKED = "BOOKED"


class PaymentStatus(str, enum.Enum):
    CREATED = "CREATED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    bookings = relationship("Booking", back_populates="user")
    otps = relationship("OTPVerification", back_populates="user")


class OTPVerification(Base):
    __tablename__ = "otp_verifications"

    id = Column(Integer, primary_key=True, index=True)
    verification_id = Column(String, unique=True, index=True, default=gen_uuid)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    otp_hash = Column(String, nullable=False)      # hashed, never plaintext
    purpose = Column(String, default="booking")    # e.g. "booking", "login"
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0)
    max_attempts = Column(Integer, default=5)
    verified = Column(Boolean, default=False)
    last_sent_at = Column(DateTime, default=datetime.utcnow)
    resend_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="otps")


class Bus(Base):
    __tablename__ = "buses"

    id = Column(Integer, primary_key=True, index=True)
    bus_number = Column(String, unique=True, nullable=False)
    operator = Column(String, nullable=False)
    bus_type = Column(String, nullable=False)   # e.g. AC Sleeper, Non-AC Seater
    total_seats = Column(Integer, nullable=False)

    routes = relationship("Route", back_populates="bus")


class Route(Base):
    __tablename__ = "routes"

    id = Column(Integer, primary_key=True, index=True)
    bus_id = Column(Integer, ForeignKey("buses.id"), nullable=False)
    from_city = Column(String, index=True, nullable=False)
    to_city = Column(String, index=True, nullable=False)
    departure = Column(DateTime, nullable=False)
    arrival = Column(DateTime, nullable=False)
    fare = Column(Float, nullable=False)

    bus = relationship("Bus", back_populates="routes")
    seats = relationship("SeatInventory", back_populates="route")


class SeatInventory(Base):
    """
    One row per (route, seat_number). This is what makes the server
    authoritative for seat availability instead of the browser.
    """
    __tablename__ = "seat_inventory"

    id = Column(Integer, primary_key=True, index=True)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=False)
    seat_number = Column(String, nullable=False)
    status = Column(Enum(SeatStatus), default=SeatStatus.AVAILABLE)
    held_by_session = Column(String, nullable=True)   # opaque hold token
    hold_expires_at = Column(DateTime, nullable=True)

    route = relationship("Route", back_populates="seats")


class Booking(Base):
    __tablename__ = "bookings"

    id = Column(Integer, primary_key=True, index=True)
    pnr = Column(String, unique=True, index=True, default=lambda: gen_uuid()[:10].upper())
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    route_id = Column(Integer, ForeignKey("routes.id"), nullable=False)

    status = Column(Enum(BookingStatus), default=BookingStatus.PENDING)
    base_fare = Column(Float, nullable=False)
    convenience_fee = Column(Float, default=0.0)
    total = Column(Float, nullable=False)

    hold_token = Column(String, default=gen_uuid)   # ties this booking to its seat holds
    otp_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="bookings")
    route = relationship("Route")
    passengers = relationship("Passenger", back_populates="booking", cascade="all, delete-orphan")
    payment = relationship("Payment", back_populates="booking", uselist=False)


class Passenger(Base):
    __tablename__ = "passengers"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), nullable=False)
    name = Column(String, nullable=False)
    age = Column(Integer, nullable=False)
    gender = Column(String, nullable=False)
    seat_number = Column(String, nullable=False)

    booking = relationship("Booking", back_populates="passengers")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    booking_id = Column(Integer, ForeignKey("bookings.id"), unique=True, nullable=False)
    gateway_order_id = Column(String, nullable=True)
    gateway_payment_id = Column(String, nullable=True)
    gateway_signature = Column(String, nullable=True)
    amount = Column(Float, nullable=False)
    method = Column(String, nullable=True)
    status = Column(Enum(PaymentStatus), default=PaymentStatus.CREATED)
    created_at = Column(DateTime, default=datetime.utcnow)

    booking = relationship("Booking", back_populates="payment")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)
    entity = Column(String, nullable=True)
    entity_id = Column(String, nullable=True)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
