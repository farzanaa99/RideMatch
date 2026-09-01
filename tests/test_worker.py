import pytest

from app.models.driver import Driver
from app.models.enums import RideStatus
from app.models.ride_request import RideRequest
from app.worker import run_worker_cycle


@pytest.mark.asyncio
async def test_run_worker_cycle_assigns_real_driver(db_session):
    driver = Driver(driver_name="D1", rating=5.0, lat=40.71, lng=-74.0, max_capacity=1)
    ride = RideRequest(
        rider_id="r1",
        pickup_lat=40.71, pickup_lng=-74.0,
        dropoff_lat=40.75, dropoff_lng=-73.98,
    )
    db_session.add_all([driver, ride])
    await db_session.commit()

    matches, retries = await run_worker_cycle(db_session, event_bus=None)

    await db_session.refresh(ride)
    assert ride.status == RideStatus.ASSIGNED
    assert len(matches) == 1


@pytest.mark.asyncio
async def test_run_worker_cycle_no_drivers(db_session):
    ride = RideRequest(
        rider_id="r1",
        pickup_lat=40.71, pickup_lng=-74.0,
        dropoff_lat=40.75, dropoff_lng=-73.98,
    )
    db_session.add(ride)
    await db_session.commit()

    matches, retries = await run_worker_cycle(db_session, event_bus=None)

    await db_session.refresh(ride)
    assert matches == []
    assert ride.status == RideStatus.RETRYING