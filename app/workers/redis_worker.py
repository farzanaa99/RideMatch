"""Redis-backed worker for ride matching and retry processing."""

import asyncio
import logging
import os
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal, close_db, init_db
from app.engine.matching_engine import MatchingEngine
from app.engine.queue_manager import QueueManager
from app.engine.state_machine import RideStateMachine
from app.events import EventBus, EventHandlerRegistry, register_handlers
from app.events.models import DomainEvent, EventType
from app.metrics import MetricsCollector
from app.queue.redis_queue import RedisQueue
from app.repositories.driver_repository import DriverRepository
from app.repositories.ride_request_repository import RideRequestRepository

logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

MATCH_QUEUE = "ride-match-jobs"
RETRY_QUEUE = "ride-retry-jobs"
DLQ_QUEUE = "ride-dead-letter-jobs"


async def process_match_job(
    session: AsyncSession,
    payload: dict[str, Any],
    event_bus: EventBus | None = None,
) -> None:
    """Run one match cycle for a ride request."""
    ride_id = payload.get("ride_id")
    if not ride_id:
        logger.warning("Skipping match job with missing ride_id: %s", payload)
        return

    ride_repo = RideRequestRepository(session)
    driver_repo = DriverRepository(session)
    queue_manager = QueueManager(
        session=session,
        ride_repo=ride_repo,
        driver_repo=driver_repo,
        state_machine=RideStateMachine(),
    )
    engine = MatchingEngine(queue_manager)
    await engine.match_rides()

    if event_bus:
        await event_bus.publish(
            DomainEvent(
                event_type=EventType.RIDE_QUEUED,
                data={"request_id": ride_id, "queue": MATCH_QUEUE},
            )
        )


async def process_retry_job(
    session: AsyncSession,
    payload: dict[str, Any],
    event_bus: EventBus | None = None,
) -> None:
    """Run retry handling for a ride request."""
    ride_id = payload.get("ride_id")
    if not ride_id:
        logger.warning("Skipping retry job with missing ride_id: %s", payload)
        return

    ride_repo = RideRequestRepository(session)
    driver_repo = DriverRepository(session)
    queue_manager = QueueManager(
        session=session,
        ride_repo=ride_repo,
        driver_repo=driver_repo,
        state_machine=RideStateMachine(),
    )
    engine = MatchingEngine(queue_manager)
    await engine.process_retries()

    if event_bus:
        await event_bus.publish(
            DomainEvent(
                event_type=EventType.RIDE_RETRYING,
                data={"request_id": ride_id, "queue": RETRY_QUEUE},
            )
        )


async def run_redis_worker() -> None:
    """Long-running worker that consumes jobs from Redis."""
    await init_db()
    queue = RedisQueue()

    registry = EventHandlerRegistry()
    metrics = MetricsCollector()
    event_bus = EventBus(registry, metrics_collector=metrics)
    register_handlers(registry, metrics_collector=metrics)
    await event_bus.start()

    logger.info("Redis worker started")
    try:
        while True:
            async with AsyncSessionLocal() as session:
                job = await queue.dequeue(MATCH_QUEUE)
                if job:
                    logger.info("Processing match job: %s", job)
                    try:
                        await process_match_job(session, job, event_bus=event_bus)
                    except Exception as exc:
                        logger.exception("Match job failed: %s", job)
                        await queue.dead_letter(DLQ_QUEUE, job, str(exc))

                retry_job = await queue.dequeue_delayed(RETRY_QUEUE)
                if retry_job:
                    logger.info("Processing delayed retry job: %s", retry_job)
                    try:
                        await process_retry_job(session, retry_job, event_bus=event_bus)
                    except Exception as exc:
                        logger.exception("Retry job failed: %s", retry_job)
                        await queue.dead_letter(DLQ_QUEUE, retry_job, str(exc))

            await asyncio.sleep(2)
    except asyncio.CancelledError:
        logger.info("Redis worker cancelled")
        raise
    finally:
        await event_bus.stop()
        await queue.close()
        await close_db()
        logger.info("Redis worker stopped")


if __name__ == "__main__":
    asyncio.run(run_redis_worker())
