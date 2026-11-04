from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field


# ---------- Auth / OTP ----------
class RequestOTP(BaseModel):
    name: str
    email: EmailStr
    phone: str = Field(min_length=10, max_length=15)
    purpose: str = "booking"


class RequestOTPResponse(BaseModel):
    verification_id: str
    expires_in_seconds: int
    # dev_otp is only populated when OTP_DELIVERY_MODE=dev — never in production
    dev_otp: Optional[str] = None


class VerifyOTP(BaseModel):
    verification_id: str
    otp: str = Field(min_length=6, max_length=6)


class VerifyOTPResponse(BaseModel):
    verified: bool
    user_id: int
    message: str


# ---------- Buses / Search ----------
class RouteSearchResult(BaseModel):
    route_id: int
    bus_number: str
    operator: str
    bus_type: str
    from_city: str
    to_city: str
    departure: datetime
    arrival: datetime
    fare: float
    seats_available: int

    class Config:
        from_attributes = True


class SeatOut(BaseModel):
    seat_number: str
    status: str

    class Config:
        from_attributes = True


# ---------- Seat holding ----------
class HoldSeatsRequest(BaseModel):
    route_id: int
    seat_numbers: List[str]
    hold_token: Optional[str] = None  # reuse existing hold, else a new one is issued


class HoldSeatsResponse(BaseModel):
    hold_token: str
    held_seats: List[str]
    hold_expires_at: datetime


class ReleaseSeatsRequest(BaseModel):
    hold_token: str
    seat_numbers: List[str]


# ---------- Passengers / Booking ----------
class PassengerIn(BaseModel):
    name: str
    age: int
    gender: str
    seat_number: str


class PassengerOut(BaseModel):
    name: str
    age: int
    gender: str
    seat_number: str

    class Config:
        from_attributes = True


class CreateBookingRequest(BaseModel):
    route_id: int
    hold_token: str
    user_id: int
    passengers: List[PassengerIn]


class BookingOut(BaseModel):
    pnr: str
    status: str
    base_fare: float
    convenience_fee: float
    total: float

    class Config:
        from_attributes = True


class BookingDetail(BaseModel):
    pnr: str
    status: str
    base_fare: float
    convenience_fee: float
    total: float
    operator: str
    bus_type: str
    from_city: str
    to_city: str
    departure: datetime
    arrival: datetime
    passengers: List[PassengerOut]
    payment_method: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# ---------- Payments ----------
class CreateOrderRequest(BaseModel):
    pnr: str


class CreateOrderResponse(BaseModel):
    gateway_order_id: str
    amount: float
    currency: str = "INR"
    key_id: str  # public/test key for the checkout widget


class VerifyPaymentRequest(BaseModel):
    pnr: str
    gateway_order_id: str
    gateway_payment_id: str
    gateway_signature: str
    method: Optional[str] = None


class VerifyPaymentResponse(BaseModel):
    status: str
    pnr: str
    message: str
