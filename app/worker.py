"""Background worker process for matching and retry loops."""

import asyncio
import logging
import os

from app.database import AsyncSessionLocal, close_db, init_db
from app.engine.matching_engine import MatchingEngine
from app.engine.queue_manager import QueueManager
from app.engine.state_machine import RideStateMachine
from app.events import EventBus, EventHandlerRegistry, register_handlers
from app.metrics import MetricsCollector
from app.repositories.driver_repository import DriverRepository
from app.repositories.ride_request_repository import RideRequestRepository
from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

async def run_worker_cycle(
    session: AsyncSession, event_bus: EventBus | None = None
) -> tuple[list, int]:
    """Run one matching + retry cycle against the given session. Extracted from
    run_worker() so it can be tested directly against a real DB session without
    running the infinite loop."""
    queue_manager = QueueManager(
        session=session,
        ride_repo=RideRequestRepository(session),
        driver_repo=DriverRepository(session),
        state_machine=RideStateMachine(),
        event_bus=event_bus,
    )
    engine = MatchingEngine(queue_manager)

    matches = await engine.match_rides()
    retries = await engine.process_retries()
    return matches, retries


async def run_worker() -> None:
    """Run matching and retry loops on a configurable schedule."""
    poll_seconds = float(os.getenv("WORKER_POLL_SECONDS", "2"))

    # Worker has its own local event bus for side effects/logging.
    registry = EventHandlerRegistry()
    metrics = MetricsCollector()
    event_bus = EventBus(registry, metrics_collector=metrics)
    register_handlers(registry, metrics_collector=metrics)

    await init_db()
    await event_bus.start()
    logger.info("Worker started (poll interval=%ss)", poll_seconds)

    try:
        while True:
            async with AsyncSessionLocal() as session:
                matches, retries = await run_worker_cycle(session, event_bus)

                if matches or retries:
                    logger.info(
                        "Worker cycle: matches=%d retries_requeued=%d",
                        len(matches),
                        retries,
                    )

            await asyncio.sleep(poll_seconds)
    except asyncio.CancelledError:
        logger.info("Worker received cancellation")
        raise
    except KeyboardInterrupt:
        logger.info("Worker interrupted")
    finally:
        await event_bus.stop()
        await close_db()
        logger.info("Worker stopped")


if __name__ == "__main__":
    asyncio.run(run_worker())
