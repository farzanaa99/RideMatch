import pytest

from app.engine.matching_engine import MatchingEngine
from app.engine.queue_manager import QueueManager
from app.models.driver import Driver
from app.models.enums import RideStatus
from app.models.ride_request import RideRequest
from app.repositories.driver_repository import DriverRepository
from app.repositories.ride_request_repository import RideRequestRepository


@pytest.mark.asyncio
async def test_match_rides_assigns_real_driver(db_session):
    driver = Driver(driver_name="D1", rating=5.0, lat=40.71, lng=-74.0, max_capacity=1)
    ride = RideRequest(
        rider_id="r1",
        pickup_lat=40.71, pickup_lng=-74.0,
        dropoff_lat=40.75, dropoff_lng=-73.98,
    )
    db_session.add_all([driver, ride])
    await db_session.commit()

    ride_repo = RideRequestRepository(db_session)
    driver_repo = DriverRepository(db_session)
    queue_manager = QueueManager(db_session, ride_repo, driver_repo)
    engine = MatchingEngine(queue_manager)

    matches = await engine.match_rides()

    await db_session.refresh(ride)
    assert ride.status == RideStatus.ASSIGNED
    assert ride.assigned_driver_id == driver.id
    assert len(matches) == 1


@pytest.mark.asyncio
async def test_match_rides_no_drivers_retries_or_fails(db_session):
    ride = RideRequest(
        rider_id="r1",
        pickup_lat=40.71, pickup_lng=-74.0,
        dropoff_lat=40.75, dropoff_lng=-73.98,
    )
    db_session.add(ride)
    await db_session.commit()

    ride_repo = RideRequestRepository(db_session)
    driver_repo = DriverRepository(db_session)
    queue_manager = QueueManager(db_session, ride_repo, driver_repo)
    engine = MatchingEngine(queue_manager)

    matches = await engine.match_rides()

    await db_session.refresh(ride)
    assert matches == []
    assert ride.status in (RideStatus.RETRYING, RideStatus.FAILED)