from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root():
    response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "RideMatch API is Running!"
    assert payload["version"] == "0.1.0"
    assert payload["docs"] == "/docs"