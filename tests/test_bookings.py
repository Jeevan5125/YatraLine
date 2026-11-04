from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_booking_invalid_route():
    response = client.post(
        "/api/bookings",
        json={
            "route_id": 999999,
            "user_id": 999999,
            "hold_token": "test-token",
            "passengers": [
                {
                    "name": "Test User",
                    "age": 20,
                    "gender": "Male",
                    "seat_number": "1A",
                }
            ],
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Route not found"


def test_get_nonexistent_booking():
    response = client.get("/api/bookings/INVALID-PNR")

    assert response.status_code == 404
    assert response.json()["detail"] == "Booking not found"


def test_confirm_nonexistent_booking():
    response = client.post(
        "/api/bookings/INVALID-PNR/confirm-otp",
        params={"verification_id": "invalid-verification"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Booking not found"


def test_my_bookings_nonexistent_user():
    response = client.get("/api/bookings/my/999999")

    assert response.status_code == 200
    assert isinstance(response.json(), list)