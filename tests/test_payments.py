from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_create_order_invalid_booking():
    response = client.post(
        "/api/payments/create-order",
        json={
            "pnr": "INVALID-PNR"
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Booking not found"


def test_verify_invalid_booking():
    response = client.post(
        "/api/payments/verify",
        json={
            "pnr": "INVALID-PNR",
            "gateway_order_id": "order_test",
            "gateway_payment_id": "pay_test",
            "gateway_signature": "invalid-signature",
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Booking not found"


def test_mock_payment_missing_data():
    response = client.post(
        "/api/payments/_dev/sign-mock-payment",
        json={}
    )

    assert response.status_code == 403



def test_webhook():
    response = client.post(
        "/api/payments/webhook",
        json={
            "event": "payment.test",
            "id": "test-event"
        },
    )

    assert response.status_code == 200
    assert response.json() == {"received": True}