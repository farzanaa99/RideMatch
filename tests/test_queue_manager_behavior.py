from datetime import datetime, timedelta, timezone

import pytest

from app.engine.queue_manager import QueueManager
from app.engine.state_machine import RideStateMachine
from app.exceptions import InvalidStatusTransition, RideRequestNotFound
from app.models.driver import Driver
from app.models.enums import DriverStatus, QueueSortStrategy, RidePriority, RideStatus
from app.models.ride_request import RideRequest
from app.repositories.driver_repository import DriverRepository
from app.repositories.ride_request_repository import RideRequestRepository


class StubEventBus:
    def __init__(self):
        self.events = []

    async def publish(self, event):
        self.events.append(event)


def make_queue_manager(db_session, event_bus=None, strategy=QueueSortStrategy.HYBRID) -> QueueManager:
    return QueueManager(
        session=db_session,
        ride_repo=RideRequestRepository(db_session),
        driver_repo=DriverRepository(db_session),
        strategy=strategy,
        state_machine=RideStateMachine(),
        event_bus=event_bus,
    )


@pytest.mark.asyncio
async def test_get_pending_requests_rejects_negative_inputs(db_session):
    qm = make_queue_manager(db_session)
    with pytest.raises(ValueError):
        await qm.get_pending_requests(limit=-1)
    with pytest.raises(ValueError):
        await qm.get_pending_requests(offset=-1)


@pytest.mark.asyncio
async def test_get_available_drivers_limit_and_validation(db_session):
    db_session.add_all(
        [
            Driver(driver_name="d1", rating=4.6, lat=40.7, lng=-74.0, max_capacity=2, status=DriverStatus.AVAILABLE),
            Driver(driver_name="d2", rating=4.8, lat=40.8, lng=-74.1, max_capacity=2, status=DriverStatus.AVAILABLE),
            Driver(driver_name="d3", rating=4.9, lat=40.9, lng=-74.2, max_capacity=2, status=DriverStatus.ON_RIDE),
        ]
    )
    await db_session.commit()

    qm = make_queue_manager(db_session)
    drivers = await qm.get_available_drivers(limit=1)
    assert len(drivers) == 1

    with pytest.raises(ValueError):
        await qm.get_available_drivers(limit=-5)


@pytest.mark.asyncio
async def test_get_rides_ready_for_retry_filters_by_backoff(db_session):
    now = datetime.now(timezone.utc)
    ready = RideRequest(
        rider_id="ready",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.NORMAL,
        status=RideStatus.RETRYING,
        retry_count=1,
        failed_at=now - timedelta(seconds=30),
    )
    not_ready = RideRequest(
        rider_id="not_ready",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.NORMAL,
        status=RideStatus.RETRYING,
        retry_count=4,
        failed_at=now,
    )
    no_failed_at = RideRequest(
        rider_id="no_failed_at",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.NORMAL,
        status=RideStatus.RETRYING,
        retry_count=0,
        failed_at=None,
    )
    db_session.add_all([ready, not_ready, no_failed_at])
    await db_session.commit()

    qm = make_queue_manager(db_session)
    rows = await qm.get_rides_ready_for_retry(limit=10)
    rider_ids = {r.rider_id for r in rows}

    assert "ready" in rider_ids
    assert "no_failed_at" in rider_ids
    assert "not_ready" not in rider_ids


@pytest.mark.asyncio
async def test_update_request_not_found_raises(db_session):
    qm = make_queue_manager(db_session)
    with pytest.raises(RideRequestNotFound):
        await qm.update_request("missing-id", status=RideStatus.QUEUED)


@pytest.mark.asyncio
async def test_update_request_invalid_transition_raises(db_session):
    req = RideRequest(
        rider_id="bad_transition",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.NORMAL,
        status=RideStatus.PENDING,
    )
    db_session.add(req)
    await db_session.commit()

    qm = make_queue_manager(db_session)
    with pytest.raises(InvalidStatusTransition):
        await qm.update_request(req.id, status=RideStatus.COMPLETED)


@pytest.mark.asyncio
async def test_update_request_assignment_publishes_event_and_latency(db_session):
    event_bus = StubEventBus()
    req = RideRequest(
        rider_id="assign",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.NORMAL,
        status=RideStatus.QUEUED,
        created_at=datetime.now(timezone.utc) - timedelta(seconds=25),
    )
    driver = Driver(
        driver_name="assign-driver",
        rating=4.9,
        lat=40.71,
        lng=-74.00,
        max_capacity=2,
        status=DriverStatus.AVAILABLE,
    )
    db_session.add_all([req, driver])
    await db_session.commit()

    qm = make_queue_manager(db_session, event_bus=event_bus)
    await qm.update_request(req.id, status=RideStatus.ASSIGNED, driver_id=driver.id)

    refreshed = await RideRequestRepository(db_session).get_by_id(req.id)
    assert refreshed.status == RideStatus.ASSIGNED
    assert refreshed.assigned_driver_id == driver.id
    assert len(event_bus.events) == 1
    event = event_bus.events[0]
    assert event.data["driver_id"] == driver.id
    assert event.data["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_update_request_retrying_increments_retry_and_backoff_metadata(db_session):
    event_bus = StubEventBus()
    req = RideRequest(
        rider_id="retry",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.NORMAL,
        status=RideStatus.FAILED,
        retry_count=1,
        max_retries=3,
    )
    db_session.add(req)
    await db_session.commit()

    qm = make_queue_manager(db_session, event_bus=event_bus)
    await qm.update_request(req.id, status=RideStatus.RETRYING)

    refreshed = await RideRequestRepository(db_session).get_by_id(req.id)
    assert refreshed.status == RideStatus.RETRYING
    assert refreshed.retry_count == 2
    assert refreshed.failed_at is not None
    assert len(event_bus.events) == 1
    event = event_bus.events[0]
    assert event.data["retry_count"] == 2
    assert event.data["retry_backoff_seconds"] >= 20
    assert event.data["next_retry_at"] is not None


@pytest.mark.asyncio
async def test_mark_stale_requests_as_failed(db_session):
    now = datetime.now(timezone.utc)
    stale = RideRequest(
        rider_id="stale",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.NORMAL,
        status=RideStatus.PENDING,
        created_at=now - timedelta(minutes=40),
    )
    fresh = RideRequest(
        rider_id="fresh",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.NORMAL,
        status=RideStatus.PENDING,
        created_at=now - timedelta(minutes=5),
    )
    db_session.add_all([stale, fresh])
    await db_session.commit()

    qm = make_queue_manager(db_session)
    count = await qm.mark_stale_requests_as_failed()
    assert count == 1

    stale_row = await RideRequestRepository(db_session).get_by_id(stale.id)
    fresh_row = await RideRequestRepository(db_session).get_by_id(fresh.id)
    assert stale_row.status == RideStatus.FAILED
    assert fresh_row.status == RideStatus.PENDING


@pytest.mark.asyncio
async def test_get_queue_stats_returns_pending_and_oldest_age(db_session):
    now = datetime.now(timezone.utc)
    r1 = RideRequest(
        rider_id="s1",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.NORMAL,
        status=RideStatus.PENDING,
        created_at=now - timedelta(minutes=15),
    )
    r2 = RideRequest(
        rider_id="s2",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.HIGH,
        status=RideStatus.PENDING,
        created_at=now - timedelta(minutes=3),
    )
    done = RideRequest(
        rider_id="done",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.NORMAL,
        status=RideStatus.COMPLETED,
    )
    db_session.add_all([r1, r2, done])
    await db_session.commit()

    qm = make_queue_manager(db_session)
    stats = await qm.get_queue_stats()

    assert stats["pending_count"] == 2
    assert stats["oldest_request"] is not None
    assert stats["oldest_age_min"] is not None
    assert stats["oldest_age_min"] >= 10
