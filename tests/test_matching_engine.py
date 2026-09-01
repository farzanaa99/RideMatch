from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

import pytest

from app.engine.matching_engine import MatchingEngine, haversine_distance
from app.models.enums import RidePriority, RideStatus


@dataclass
class FakeRequest:
    request_id: str
    pickup_lat: float
    pickup_lng: float
    dropoff_lat: float
    dropoff_lng: float
    priority: RidePriority
    retry_count: int = 0
    max_retries: int = 3

    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries


@dataclass
class FakeDriver:
    driver_id: str
    lat: float
    lng: float
    max_capacity: int = 1
    status: str = "AVAILABLE"
    rides: list[FakeRequest] = field(default_factory=list)

    @property
    def current_location(self):
        return (self.lat, self.lng)

    @property
    def active_ride_count(self) -> int:
        return len(self.rides)

    @property
    def is_assignable(self) -> bool:
        return (
            self.active_ride_count < self.max_capacity
            and self.status == "AVAILABLE"
        )

    def assign_ride(self, request: FakeRequest):
        self.rides.append(request)
        return True


class FakeQueueManager:
    def __init__(self, requests: list[FakeRequest], drivers: list[FakeDriver]):
        self.requests = requests
        self.drivers = drivers
        self.updates: list[tuple[str, RideStatus, str | None]] = []

    async def get_pending_requests(self):
        return self.requests, len(self.requests)

    async def get_available_drivers(self):
        return self.drivers

    async def update_request(
        self,
        request_id: str,
        status: RideStatus,
        driver_id: str | None = None,
    ):
        self.updates.append((request_id, status, driver_id))

    async def get_rides_ready_for_retry(self):
        return []

    @staticmethod
    def _calculate_retry_delay(retry_count: int) -> timedelta:
        return timedelta(seconds=min(5 * (2 ** retry_count), 300))


def test_haversine_distance_zero():
	assert haversine_distance((40.7128, -74.0060), (40.7128, -74.0060)) == pytest.approx(0.0)


def test_haversine_distance_known_value():
	ny = (40.7128, -74.0060)
	la = (34.0522, -118.2437)
	km = haversine_distance(ny, la)
	assert km == pytest.approx(3935, rel=0.02)


def test_calculate_score_prioritizes_higher_priority():
	qm = FakeQueueManager([], [])
	engine = MatchingEngine(qm)
	driver = FakeDriver("d1", 40.7128, -74.0060)

	low = FakeRequest("r-low", 40.7130, -74.0062, 40.7140, -74.0050, RidePriority.LOW)
	high = FakeRequest("r-high", 40.7130, -74.0062, 40.7140, -74.0050, RidePriority.HIGH)

	assert engine.calculate_score(driver, high) > engine.calculate_score(driver, low)


@pytest.mark.asyncio
async def test_match_single_request_chooses_best_driver():
	request = FakeRequest("r1", 40.7128, -74.0060, 40.7150, -74.0020, RidePriority.NORMAL)
	close_driver = FakeDriver("d-close", 40.7130, -74.0061)
	far_driver = FakeDriver("d-far", 40.7528, -74.1060)

	qm = FakeQueueManager([request], [far_driver, close_driver])
	engine = MatchingEngine(qm)

	matches = await engine.match_rides()

	assert matches == [("r1", "d-close")]
	assert ("r1", RideStatus.ASSIGNED, "d-close") in qm.updates


@pytest.mark.asyncio
async def test_distance_threshold_excludes_far_driver_and_retries():
	request = FakeRequest("r2", 40.7128, -74.0060, 40.7150, -74.0020, RidePriority.NORMAL)
	far_driver = FakeDriver("d-far", 41.7128, -75.0060)

	qm = FakeQueueManager([request], [far_driver])
	engine = MatchingEngine(qm)

	matches = await engine.match_rides()

	assert matches == []
	assert ("r2", RideStatus.RETRYING, None) in qm.updates


@pytest.mark.asyncio
async def test_retry_limit_enforcement_marks_failed():
	request = FakeRequest(
		"r3",
		40.7128,
		-74.0060,
		40.7150,
		-74.0020,
		RidePriority.NORMAL,
		retry_count=3,
		max_retries=3,
	)
	qm = FakeQueueManager([request], [])
	engine = MatchingEngine(qm)

	matches = await engine.match_rides()

	assert matches == []
	assert ("r3", RideStatus.FAILED, None) in qm.updates
