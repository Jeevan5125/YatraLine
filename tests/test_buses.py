from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_cities():
    response = client.get("/api/buses/cities")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_search_buses():
    response = client.get(
        "/api/buses/search",
        params={
            "from_city": "Chennai",
            "to_city": "Bangalore",
        },
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_seats_invalid_route():
    response = client.get("/api/buses/999999/seats")

    assert response.status_code == 404
    assert response.json()["detail"] == "Route not found"