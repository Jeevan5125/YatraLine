from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import app
from app import models
from app.database import SessionLocal


client = TestClient(app)


def test_request_otp():
    email = "test_auth@example.com"

    response = client.post(
        "/api/auth/request-otp",
        json={
            "name": "Test User",
            "email": email,
            "phone": "9876543210",
            "purpose": "login",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert "verification_id" in data
    assert "expires_in_seconds" in data


def test_verify_nonexistent_otp():
    response = client.post(
        "/api/auth/verify-otp",
        json={
            "verification_id": "does-not-exist",
            "otp": "123456",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Verification session not found"