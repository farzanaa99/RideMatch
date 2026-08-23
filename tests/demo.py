"""
demo.py — watch RideMatch's dispatch engine run, live, over time.

Simulates several matching cycles against a real (in-memory) database using
the actual MatchingEngine, QueueManager, and state machine -- no mocks.
Drivers get busy, rides that can't be matched immediately wait and retry,
and a driver freeing up gets picked up on a later cycle -- the real
behavior of the system, not a single instant snapshot.

Usage:
    python demo.py
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

logging.disable(logging.CRITICAL)  # keep the demo output clean

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.database import Base
from app.models.driver import Driver
from app.models.ride_request import RideRequest
from app.models.enums import RidePriority, RideStatus
from app.repositories.ride_request_repository import RideRequestRepository
from app.repositories.driver_repository import DriverRepository
from app.engine.queue_manager import QueueManager
from app.engine.matching_engine import MatchingEngine


PAUSE = 1.1


def divider():
    print("─" * 62)


async def pause(seconds=PAUSE):
    await asyncio.sleep(seconds)


async def show_fleet(drivers):
    for d in drivers:
        busy = d.active_ride_count >= d.max_capacity
        icon = "🔴 busy" if busy else "🟢 free"
        print(f"      {icon}   {d.driver_name} ({d.rating}★)")


async def main():
    print("\n🚕  RideMatch — live dispatch simulation\n")
    divider()

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        alice = Driver(driver_name="Alice", rating=4.9, lat=40.758, lng=-73.985, max_capacity=1)
        marcus = Driver(driver_name="Marcus", rating=4.6, lat=40.706, lng=-74.009, max_capacity=1)
        session.add_all([alice, marcus])
        await session.commit()

        ride_repo = RideRequestRepository(session)
        driver_repo = DriverRepository(session)
        queue_manager = QueueManager(session, ride_repo, driver_repo)
        matching_engine = MatchingEngine(queue_manager)

        # Re-fetch through the repository so `rides` is eager-loaded (avoids the
        # exact async lazy-load crash Phase 1 fixed in the real matching path)
        drivers = await driver_repo.get_available_drivers()
        alice = next(d for d in drivers if d.driver_name == "Alice")
        marcus = next(d for d in drivers if d.driver_name == "Marcus")

        print("🚗 Fleet online:")
        await show_fleet(drivers)
        await pause()

        # ---- Cycle 1: Jordan requests a ride, one driver is free ----
        divider()
        print("⏱  Cycle 1")
        print("🙋 Jordan requests a ride  [HIGH priority]")
        jordan = RideRequest(rider_id="Jordan", pickup_lat=40.760, pickup_lng=-73.984,
                              dropoff_lat=40.645, dropoff_lng=-73.779, priority=RidePriority.HIGH)
        session.add(jordan)
        await session.commit()
        await pause()

        matches = await matching_engine.match_rides()
        for req_id, drv_id in matches:
            drv = next(d for d in drivers if d.id == drv_id)
            print(f"   🎯 Matched with {drv.driver_name} — dispatch engine scored every "
                  f"free driver and picked the best fit")
        await pause()

        # ---- Cycle 2: Sam requests, only one driver still free ----
        divider()
        print("⏱  Cycle 2")
        print("🙋 Sam requests a ride  [NORMAL priority]")
        sam = RideRequest(rider_id="Sam", pickup_lat=40.708, pickup_lng=-74.011,
                           dropoff_lat=40.749, dropoff_lng=-73.968, priority=RidePriority.NORMAL)
        session.add(sam)
        await session.commit()
        await pause()

        print("   🚗 Fleet status:")
        await show_fleet(drivers)
        await pause()

        matches = await matching_engine.match_rides()
        for req_id, drv_id in matches:
            drv = next(d for d in drivers if d.id == drv_id)
            print(f"   🎯 Matched with {drv.driver_name} — last free driver in the fleet")
        await pause()

        # ---- Cycle 3: Riley requests, but NO drivers are free ----
        divider()
        print("⏱  Cycle 3")
        print("🙋 Riley requests a ride  [LOW priority]")
        riley = RideRequest(rider_id="Riley", pickup_lat=40.731, pickup_lng=-73.999,
                             dropoff_lat=40.723, dropoff_lng=-73.996, priority=RidePriority.LOW)
        session.add(riley)
        await session.commit()
        await pause()

        print("   🚗 Fleet status:")
        await show_fleet(drivers)
        await pause()

        await matching_engine.match_rides()
        await session.refresh(riley)
        print(f"   ⏳ No drivers available — Riley's request is {riley.status.value}, "
              f"will retry automatically with backoff")
        await pause()

        # ---- Alice completes her ride and becomes free again ----
        divider()
        print("⏱  Meanwhile: Alice finishes Jordan's ride")
        await queue_manager.update_request(request_id=jordan.request_id, status=RideStatus.EN_ROUTE)
        await queue_manager.update_request(request_id=jordan.request_id, status=RideStatus.IN_PROGRESS)
        await queue_manager.update_request(request_id=jordan.request_id, status=RideStatus.COMPLETED)
        print(f"   ✅ Jordan's ride: EN_ROUTE → IN_PROGRESS → COMPLETED")
        await pause()

        print("   🚗 Fleet status:")
        await show_fleet(drivers)
        await pause()

        # ---- Cycle 4: force Riley's backoff to have elapsed, then retry ----
        divider()
        print("⏱  Cycle 4 — retry window elapses")
        await session.refresh(riley)
        riley.failed_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        await session.commit()

        requeued = await matching_engine.process_retries()
        print(f"   🔁 {requeued} ride re-queued for another matching attempt")
        await pause()

        await matching_engine.match_rides()
        await session.refresh(riley)
        icon = "✅" if riley.status == RideStatus.ASSIGNED else "⏳"
        print(f"   {icon} Riley: {riley.status.value}")

        divider()
        print("\n📋 Final status:")
        for r in [jordan, sam, riley]:
            await session.refresh(r)
            icon = {"COMPLETED": "✅", "ASSIGNED": "✅"}.get(r.status.value, "⏳")
            print(f"   {icon} {r.rider_id}: {r.status.value}")

    divider()
    print("\nRun again to see slightly different timing and outcomes.\n")


if __name__ == "__main__":
    asyncio.run(main())