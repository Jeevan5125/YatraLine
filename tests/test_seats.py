from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_hold_unknown_route():
    response = client.post(
        "/api/seats/hold",
        json={
            "route_id": 999999,
            "seat_numbers": ["1A"],
        },
    )

    assert response.status_code == 404


def test_release_nonexistent_hold():
    response = client.request(
        "DELETE",
        "/api/seats/release",
        json={
            "hold_token": "nonexistent-token",
            "seat_numbers": ["1A"],
        },
    )

    assert response.status_code == 200
    assert response.json()["released"] == []