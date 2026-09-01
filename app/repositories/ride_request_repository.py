"""Repository for RideRequest model."""

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import RideStatus
from app.models.ride_request import RideRequest
from app.repositories.base import BaseRepository


class RideRequestRepository(BaseRepository[RideRequest]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, RideRequest)

    async def get_pending_requests(self) -> List[RideRequest]:
        result = await self.session.execute(
            select(RideRequest).where(RideRequest.status == RideStatus.PENDING)
        )
        return result.scalars().all()

    async def get_requests_by_status(self, status: RideStatus) -> List[RideRequest]:
        result = await self.session.execute(
            select(RideRequest).where(RideRequest.status == status)
        )
        return result.scalars().all()

    async def get_requests_by_rider(self, rider_id: str) -> List[RideRequest]:
        result = await self.session.execute(
            select(RideRequest).where(RideRequest.rider_id == rider_id)
        )
        return result.scalars().all()

    async def get_requests_by_driver(self, driver_id: str) -> List[RideRequest]:
        result = await self.session.execute(
            select(RideRequest).where(RideRequest.assigned_driver_id == driver_id)
        )
        return result.scalars().all()

    async def get_active_requests_for_driver(self, driver_id: str) -> List[RideRequest]:
        active_statuses = {
            RideStatus.ASSIGNED,
            RideStatus.EN_ROUTE,
            RideStatus.IN_PROGRESS
        }
        result = await self.session.execute(
            select(RideRequest).where(
                (RideRequest.assigned_driver_id == driver_id) &
                (RideRequest.status.in_(active_statuses))
            )
        )
        return result.scalars().all()

    async def get_requests_for_retry(self) -> List[RideRequest]:
        result = await self.session.execute(
            select(RideRequest).where(
                (RideRequest.status == RideStatus.FAILED) &
                (RideRequest.retry_count < RideRequest.max_retries)
            )
        )
        return result.scalars().all()

    async def update_status(self, request_id: str, status: RideStatus) -> Optional[RideRequest]:
        """Update ride request status.
        
        Args:
            request_id: ID of the ride request to update.
            status: New status to set.
        
        Returns:
            Updated RideRequest or None if not found.
        """
        request = await self.get_by_id(request_id)
        if request:
            request.status = status
            await self.session.flush()
        return request
