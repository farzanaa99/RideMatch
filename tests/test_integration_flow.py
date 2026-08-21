import uuid

import pytest


@pytest.mark.asyncio
async def test_end_to_end_request_queue_assign_complete(async_client):
    driver_payload = {
        "driver_name": "Flow Driver",
        "rating": 4.9,
        "lat": 40.7128,
        "lng": -74.0060,
        "max_capacity": 2,
    }
    driver_resp = await async_client.post("/api/v1/drivers/", json=driver_payload)
    assert driver_resp.status_code == 201
    driver_id = driver_resp.json()["id"]

    ride_payload = {
        "rider_id": str(uuid.uuid4()),
        "pickup_lat": 40.7130,
        "pickup_lng": -74.0050,
        "dropoff_lat": 40.7520,
        "dropoff_lng": -73.9800,
        "priority": 2,
        "max_retries": 3,
    }
    ride_resp = await async_client.post("/api/v1/rides/", json=ride_payload)
    assert ride_resp.status_code == 201
    ride = ride_resp.json()
    request_id = ride["id"]
    assert ride["status"] == "PENDING"

    queued_resp = await async_client.put(
        f"/api/v1/rides/{request_id}",
        json={"status": "QUEUED"},
    )
    assert queued_resp.status_code == 200
    assert queued_resp.json()["status"] == "QUEUED"

    assign_resp = await async_client.post(
        f"/api/v1/rides/{request_id}/assign/{driver_id}"
    )
    assert assign_resp.status_code == 200
    assigned_payload = assign_resp.json()
    assert assigned_payload["status"] == "ASSIGNED"
    assert assigned_payload["assigned_driver_id"] == driver_id

    pickup_resp = await async_client.post(f"/api/v1/rides/{request_id}/pickup")
    assert pickup_resp.status_code == 200
    assert pickup_resp.json()["status"] == "IN_PROGRESS"

    complete_resp = await async_client.post(f"/api/v1/rides/{request_id}/complete")
    assert complete_resp.status_code == 200
    complete_payload = complete_resp.json()
    assert complete_payload["status"] == "COMPLETED"
    assert complete_payload["completed_at"] is not None


@pytest.mark.asyncio
async def test_retry_limit_enforcement(async_client):
    ride_payload = {
        "rider_id": str(uuid.uuid4()),
        "pickup_lat": 40.7130,
        "pickup_lng": -74.0050,
        "dropoff_lat": 40.7520,
        "dropoff_lng": -73.9800,
        "priority": 2,
        "max_retries": 2,
    }

    ride_resp = await async_client.post("/api/v1/rides/", json=ride_payload)
    assert ride_resp.status_code == 201
    request_id = ride_resp.json()["id"]

    fail_1 = await async_client.post(f"/api/v1/rides/{request_id}/fail")
    assert fail_1.status_code == 200

    retry_1 = await async_client.post(f"/api/v1/rides/{request_id}/retry")
    assert retry_1.status_code == 200
    assert retry_1.json()["retry_count"] == 1

    fail_2 = await async_client.post(f"/api/v1/rides/{request_id}/fail")
    assert fail_2.status_code == 200

    retry_2 = await async_client.post(f"/api/v1/rides/{request_id}/retry")
    assert retry_2.status_code == 200
    assert retry_2.json()["retry_count"] == 2

    fail_3 = await async_client.post(f"/api/v1/rides/{request_id}/fail")
    assert fail_3.status_code == 200

    retry_3 = await async_client.post(f"/api/v1/rides/{request_id}/retry")
    assert retry_3.status_code == 400
