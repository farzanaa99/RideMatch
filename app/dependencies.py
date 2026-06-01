"""Dependency injection utilities for FastAPI."""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.engine.queue_manager import QueueManager
from app.engine.state_machine import RideStateMachine
from app.repositories.ride_request_repository import RideRequestRepository
from app.repositories.driver_repository import DriverRepository
from app.services.driver_service import DriverService
from app.services.ride_service import RideRequestService
from app.events import EventBus
from fastapi import Depends

# Will be set by main.py
_event_bus: EventBus | None = None


def set_event_bus(event_bus: EventBus) -> None:
    """Set the event bus instance (called from main.py)."""
    global _event_bus
    _event_bus = event_bus


def get_event_bus() -> EventBus:
    """Get the event bus instance."""
    if _event_bus is None:
        raise RuntimeError("Event bus not initialized")
    return _event_bus


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_driver_service(session: AsyncSession = Depends(get_db)) -> DriverService:
    """Get driver service."""
    return DriverService(session)


async def get_ride_service(
    session: AsyncSession = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus)
) -> RideRequestService:
    """Get ride service with event bus."""
    return RideRequestService(session, event_bus)

async def get_queue_manager(
    session: AsyncSession = Depends(get_db),
    event_bus: EventBus = Depends(get_event_bus)
) -> QueueManager:
    """Get queue manager with repositories, state machine, and event bus."""
    ride_repo = RideRequestRepository(session)
    driver_repo = DriverRepository(session)
    state_machine = RideStateMachine()
    return QueueManager(
        session=session,
        ride_repo=ride_repo,
        driver_repo=driver_repo,
        state_machine=state_machine,
        event_bus=event_bus,
    )
