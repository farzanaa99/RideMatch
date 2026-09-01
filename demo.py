"""
demo.py — a live, randomized dispatch simulation, not a scripted test.

Every run generates a different fleet size, different driver locations, and
a randomized stream of ride requests arriving over simulated time. The
terminal redraws in place each tick, like a real ops dashboard, using the
actual MatchingEngine, QueueManager, and state machine against a real
in-memory database -- no mocks, nothing scripted or hardcoded.

Usage:
    python demo.py
"""

import asyncio
import logging
import random
import sys
from datetime import timedelta

logging.disable(logging.CRITICAL)

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base
from app.engine.matching_engine import MatchingEngine
from app.engine.queue_manager import QueueManager
from app.models.driver import Driver
from app.models.enums import RidePriority, RideStatus
from app.models.ride_request import RideRequest
from app.repositories.driver_repository import DriverRepository
from app.repositories.ride_request_repository import RideRequestRepository

DRIVER_NAMES = [
    "Alice",
    "Marcus",
    "Priya",
    "Devon",
    "Nina",
    "Kai",
    "Sofia",
    "Owen",
]
RIDER_NAMES = [
    "Jordan",
    "Sam",
    "Riley",
    "Taylor",
    "Morgan",
    "Casey",
    "Avery",
    "Quinn",
    "Reese",
    "Blake",
    "Harper",
    "Emerson",
]

CITY_LAT, CITY_LNG = 40.73, -73.99   # roughly Manhattan
SPREAD = 0.06
TICKS = 16
TICK_DELAY = 0.9
RETRY_COMPRESSION = timedelta(seconds=45)  # collapses the 5-40s real backoff into this demo's runtime


def rand_point():
    return (CITY_LAT + random.uniform(-SPREAD, SPREAD),
            CITY_LNG + random.uniform(-SPREAD, SPREAD))


def clear_and_home():
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()


def fmt_clock(tick):
    total_seconds = tick * 47
    return f"{total_seconds // 60:02d}:{total_seconds % 60:02d}"


async def draw(tick, drivers, rides_by_id, events, stats):
    clear_and_home()
    lines = []
    lines.append(f"RideMatch -- live dispatch simulation   [t={fmt_clock(tick)}]")
    lines.append("=" * 64)
    lines.append("FLEET")
    for d in drivers:
        busy_ride = next(
            (
                r
                for r in rides_by_id.values()
                if r.assigned_driver_id == d.id
                and r.status
                in (
                    RideStatus.ASSIGNED,
                    RideStatus.EN_ROUTE,
                    RideStatus.IN_PROGRESS,
                )
            ),
            None,
        )
        if busy_ride:
            lines.append(
                f"  {d.driver_name:<8} {d.rating:.1f}*   busy -> {busy_ride.rider_id}"
            )
        else:
            lines.append(f"  {d.driver_name:<8} {d.rating:.1f}*   free")

    pending = sum(1 for r in rides_by_id.values() if r.status == RideStatus.PENDING)
    queued = sum(1 for r in rides_by_id.values() if r.status == RideStatus.QUEUED)
    retrying = sum(1 for r in rides_by_id.values() if r.status == RideStatus.RETRYING)

    lines.append("")
    lines.append("QUEUE")
    lines.append(f"  pending: {pending}   queued: {queued}   retrying: {retrying}   "
                  f"matched: {stats['matched']}   completed: {stats['completed']}")
    lines.append("")
    lines.append("RECENT EVENTS")
    for e in events[-7:]:
        lines.append(f"  [{e[0]}] {e[1]}")
    lines.append("=" * 64)

    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()


async def main():
    random.seed()  # different every run

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        ride_repo = RideRequestRepository(session)
        driver_repo = DriverRepository(session)
        queue_manager = QueueManager(session, ride_repo, driver_repo)
        matching_engine = MatchingEngine(queue_manager)

        # Randomized fleet size and starting positions -- different every run
        fleet_size = random.randint(3, 5)
        names = random.sample(DRIVER_NAMES, fleet_size)
        for name in names:
            lat, lng = rand_point()
            session.add(
                Driver(
                    driver_name=name,
                    rating=round(random.uniform(4.3, 5.0), 1),
                    lat=lat,
                    lng=lng,
                    max_capacity=1,
                )
            )
        await session.commit()

        drivers = await driver_repo.get_available_drivers()

        rides_by_id = {}
        events = []
        stats = {"matched": 0, "completed": 0}
        rider_pool = random.sample(RIDER_NAMES, min(len(RIDER_NAMES), TICKS))
        rider_i = 0
        # rides already RETRYING before this tick
        previously_retrying_ids = set()

        for tick in range(TICKS):
            # Randomized arrivals: 0-2 new ride requests this tick
            for _ in range(random.choice([0, 0, 1, 1, 2])):
                if rider_i >= len(rider_pool):
                    break
                name = rider_pool[rider_i]
                rider_i += 1
                plat, plng = rand_point()
                dlat, dlng = rand_point()
                priority = random.choices(
                    [RidePriority.LOW, RidePriority.NORMAL, RidePriority.HIGH],
                    weights=[0.3, 0.5, 0.2],
                )[0]
                ride = RideRequest(
                    rider_id=name,
                    pickup_lat=plat,
                    pickup_lng=plng,
                    dropoff_lat=dlat,
                    dropoff_lng=dlng,
                    priority=priority,
                )
                session.add(ride)
                await session.commit()
                rides_by_id[ride.request_id] = ride
                events.append(
                    (fmt_clock(tick), f"{name} requested a ride [{priority.name}]")
                )

            # Randomly complete one busy driver's ride this tick (simulates a trip finishing)
            in_flight = [
                r
                for r in rides_by_id.values()
                if r.status
                in (RideStatus.ASSIGNED, RideStatus.EN_ROUTE, RideStatus.IN_PROGRESS)
            ]
            if in_flight and random.random() < 0.5:
                ride = random.choice(in_flight)
                await queue_manager.update_request(
                    request_id=ride.request_id,
                    status=RideStatus.EN_ROUTE,
                )
                await queue_manager.update_request(
                    request_id=ride.request_id,
                    status=RideStatus.IN_PROGRESS,
                )
                await queue_manager.update_request(
                    request_id=ride.request_id,
                    status=RideStatus.COMPLETED,
                )
                await session.refresh(ride)
                stats["completed"] += 1
                events.append(
                    (
                        fmt_clock(tick),
                        f"{ride.rider_id}'s ride completed, driver freed up",
                    )
                )

            # Run the real matching engine
            matches = await matching_engine.match_rides()
            for req_id, drv_id in matches:
                ride = rides_by_id[req_id]
                await session.refresh(ride)
                drv = next(d for d in drivers if d.id == drv_id)
                stats["matched"] += 1
                events.append(
                    (fmt_clock(tick), f"{ride.rider_id} matched with {drv.driver_name}")
                )

            # Process retries -- but only ones that were ALREADY retrying before
            # this tick's match attempt, so a newly-retrying ride is actually
            # visible in the dashboard for a full tick before it gets picked
            # back up, instead of resolving invisibly within the same tick.
            for rid in previously_retrying_ids:
                r = rides_by_id.get(rid)
                if r:
                    await session.refresh(r)
                    if r.status == RideStatus.RETRYING:
                        r.failed_at = r.failed_at - RETRY_COMPRESSION
            await session.commit()
            await matching_engine.process_retries()

            for r in rides_by_id.values():
                await session.refresh(r)

            previously_retrying_ids = {rid for rid, r in rides_by_id.items()
                                        if r.status == RideStatus.RETRYING}

            await draw(tick, drivers, rides_by_id, events, stats)
            await asyncio.sleep(TICK_DELAY)

        print("\nFinal status:")
        for r in rides_by_id.values():
            print(f"  {r.rider_id:<8} {r.status.value}")
        print(f"\n{stats['matched']} matched, {stats['completed']} completed, "
              f"out of {len(rides_by_id)} total requests this run.")
        print("Run again for a different fleet size, arrival pattern, and outcome.\n")


if __name__ == "__main__":
    asyncio.run(main())