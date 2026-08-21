"""
Standalone verification script for RideMatch Phase 1 fixes.

Runs the REAL MatchingEngine + QueueManager + Driver/RideRequest models against
a real (in-memory) async database session — no mocks, no fakes. This is the
exact kind of check your existing unit tests skip (they mock the DB layer
entirely), which is why the original bugs shipped past 23 passing tests.

Run this BEFORE making any fixes to confirm the bugs are real, then again
AFTER each fix to confirm it's resolved.

Usage:
    python verify_phase1.py
"""

import asyncio
import sys

sys.path.insert(0, ".")  # run this from the project root (same folder as app/)

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database import Base
from app.models.driver import Driver
from app.models.ride_request import RideRequest
from app.models.enums import RidePriority, RideStatus
from app.repositories.ride_request_repository import RideRequestRepository
from app.repositories.driver_repository import DriverRepository
from app.engine.queue_manager import QueueManager
from app.engine.matching_engine import MatchingEngine


async def main():
    # Use an isolated in-memory SQLite DB — doesn't touch your real ridematch.db
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        driver = Driver(
            driver_name="Test Driver",
            rating=5.0,
            lat=40.71,
            lng=-74.0,
            max_capacity=1,
        )
        ride = RideRequest(
            rider_id="test-rider",
            pickup_lat=40.71,
            pickup_lng=-74.0,
            dropoff_lat=40.75,
            dropoff_lng=-73.98,
            priority=RidePriority.NORMAL,
        )
        session.add_all([driver, ride])
        await session.commit()

        ride_repo = RideRequestRepository(session)
        driver_repo = DriverRepository(session)
        queue_manager = QueueManager(session, ride_repo, driver_repo)
        matching_engine = MatchingEngine(queue_manager)

        print("Running MatchingEngine.match_rides() against a real DB session...\n")

        try:
            matches = await matching_engine.match_rides()
        except Exception as e:
            print(f"❌ FAILED — match_rides() raised {type(e).__name__}: {e}")
            print("\nIf you haven't applied the Phase 1 fixes yet, this is expected.")
            return

        await session.refresh(ride)

        print(f"matches returned: {matches}")
        print(f"ride.status after matching: {ride.status}")
        print(f"ride.assigned_driver_id: {ride.assigned_driver_id}")

        if ride.status == RideStatus.ASSIGNED and ride.assigned_driver_id == driver.id:
            print("\n✅ PASSED — ride was correctly matched and assigned to the driver.")
        else:
            print("\n❌ FAILED — match_rides() ran without error, but the ride was not "
                  "correctly assigned. Check items 3a/3b (state transition logic).")


if __name__ == "__main__":
    asyncio.run(main())