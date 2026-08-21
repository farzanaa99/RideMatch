from datetime import datetime, timedelta, timezone

import pytest

from app.engine.queue_manager import QueueManager
from app.engine.state_machine import RideStateMachine
from app.models.driver import Driver
from app.models.enums import QueueSortStrategy, RidePriority, RideStatus
from app.models.ride_request import RideRequest
from app.repositories.driver_repository import DriverRepository
from app.repositories.ride_request_repository import RideRequestRepository


@pytest.mark.asyncio
async def test_fifo_orders_by_oldest_first(db_session):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    older = RideRequest(
        rider_id="r1",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.NORMAL,
        status=RideStatus.PENDING,
        created_at=now - timedelta(minutes=10),
    )
    newer = RideRequest(
        rider_id="r2",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.NORMAL,
        status=RideStatus.PENDING,
        created_at=now - timedelta(minutes=1),
    )
    db_session.add_all([older, newer])
    await db_session.commit()

    qm = QueueManager(
        session=db_session,
        ride_repo=RideRequestRepository(db_session),
        driver_repo=DriverRepository(db_session),
        strategy=QueueSortStrategy.FIFO,
        state_machine=RideStateMachine(),
    )
    rows, _ = await qm.get_pending_requests()
    assert [r.rider_id for r in rows] == ["r1", "r2"]


@pytest.mark.asyncio
async def test_priority_orders_by_highest_priority_first(db_session):
    low = RideRequest(
        rider_id="low",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.LOW,
        status=RideStatus.PENDING,
    )
    high = RideRequest(
        rider_id="high",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.HIGH,
        status=RideStatus.PENDING,
    )
    db_session.add_all([low, high])
    await db_session.commit()

    qm = QueueManager(
        session=db_session,
        ride_repo=RideRequestRepository(db_session),
        driver_repo=DriverRepository(db_session),
        strategy=QueueSortStrategy.PRIORITY,
        state_machine=RideStateMachine(),
    )
    rows, _ = await qm.get_pending_requests()
    assert [r.rider_id for r in rows] == ["high", "low"]


@pytest.mark.asyncio
async def test_hybrid_orders_by_priority_then_age(db_session):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    high_newer = RideRequest(
        rider_id="high_newer",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.HIGH,
        status=RideStatus.PENDING,
        created_at=now - timedelta(minutes=2),
    )
    high_older = RideRequest(
        rider_id="high_older",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.HIGH,
        status=RideStatus.PENDING,
        created_at=now - timedelta(minutes=6),
    )
    normal_oldest = RideRequest(
        rider_id="normal_oldest",
        pickup_lat=40.71,
        pickup_lng=-74.00,
        dropoff_lat=40.72,
        dropoff_lng=-74.01,
        priority=RidePriority.NORMAL,
        status=RideStatus.PENDING,
        created_at=now - timedelta(minutes=10),
    )

    db_session.add_all([high_newer, high_older, normal_oldest])
    await db_session.commit()

    qm = QueueManager(
        session=db_session,
        ride_repo=RideRequestRepository(db_session),
        driver_repo=DriverRepository(db_session),
        strategy=QueueSortStrategy.HYBRID,
        state_machine=RideStateMachine(),
    )
    rows, _ = await qm.get_pending_requests()
    assert [r.rider_id for r in rows] == ["high_older", "high_newer", "normal_oldest"]
