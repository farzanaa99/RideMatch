"""locustfile.py — run from the project root."""
import random

from locust import HttpUser, between, task


class RideMatchUser(HttpUser):
    wait_time = between(0.1, 0.5)

    @task(3)
    def create_ride(self):
        self.client.post(
            "/api/v1/rides/",
            json={
                "rider_id": f"rider-{random.randint(1, 100000)}",
                "pickup_lat": 40.71 + random.uniform(-0.05, 0.05),
                "pickup_lng": -74.0 + random.uniform(-0.05, 0.05),
                "dropoff_lat": 40.75 + random.uniform(-0.05, 0.05),
                "dropoff_lng": -73.98 + random.uniform(-0.05, 0.05),
                "priority": random.choice([1, 2, 3]),
            },
            name="/api/v1/rides/ [POST create]",
        )

    @task(1)
    def create_driver(self):
        self.client.post(
            "/api/v1/drivers/",
            json={
                "driver_name": f"driver-{random.randint(1, 5000)}",
                "rating": round(random.uniform(3.5, 5.0), 1),
                "lat": 40.71 + random.uniform(-0.05, 0.05),
                "lng": -74.0 + random.uniform(-0.05, 0.05),
                "max_capacity": 1,
            },
            name="/api/v1/drivers/ [POST create]",
        )

    @task(2)
    def list_pending(self):
        self.client.get("/api/v1/rides/pending/", name="/api/v1/rides/pending/ [GET]")