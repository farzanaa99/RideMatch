"""Dependency injection utilities for FastAPI."""

from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import AsyncSessionLocal
from app.engine.queue_manager import QueueManager
from app.services.driver_service import DriverService
from app.services.ride_service import RideRequestService
from fastapi import Depends


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


async def get_ride_service(session: AsyncSession = Depends(get_db)) -> RideRequestService:
    """Get ride service."""
    return RideRequestService(session)

async def get_queue_manager(session: AsyncSession = Depends(get_db)) -> QueueManager:
    """Get queue manager."""
    return QueueManager(session)
