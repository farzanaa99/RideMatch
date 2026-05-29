"""Service layer for ride request operations."""

from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.ride_request import RideRequest
from app.models.enums import RideStatus, RidePriority
from app.repositories.ride_request_repository import RideRequestRepository
from app.exceptions import (
    RideRequestNotFound,
    RideAlreadyAssigned,
    CannotRetryRide,
    InvalidRideStatus
)
from app.schemas import (
    RideRequestCreate,
    RideRequestUpdate,
    RideRequestResponse
)


class RideRequestService:
    """Service for ride request business logic."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = RideRequestRepository(session)

    async def create_ride_request(self, request_in: RideRequestCreate) -> RideRequestResponse:
        """Create a new ride request."""
        request_data = request_in.model_dump()
        request = await self.repo.create(request_data)
        await self.repo.commit()
        return RideRequestResponse.from_orm(request)

    async def get_ride_request(self, request_id: str) -> RideRequestResponse:
        """Get a ride request by ID."""
        request = await self.repo.get_by_id(request_id)
        if not request:
            raise RideRequestNotFound(f"Ride request {request_id} not found")
        return RideRequestResponse.from_orm(request)

    async def get_all_requests(self, skip: int = 0, limit: int = 100) -> List[RideRequestResponse]:
        """Get all ride requests."""
        requests = await self.repo.get_all(skip, limit)
        return [RideRequestResponse.from_orm(r) for r in requests]

    async def get_pending_requests(self) -> List[RideRequestResponse]:
        """Get all pending requests."""
        requests = await self.repo.get_pending_requests()
        return [RideRequestResponse.from_orm(r) for r in requests]

    async def get_requests_by_rider(self, rider_id: str) -> List[RideRequestResponse]:
        """Get all requests for a rider."""
        requests = await self.repo.get_requests_by_rider(rider_id)
        return [RideRequestResponse.from_orm(r) for r in requests]

    async def get_requests_by_driver(self, driver_id: str) -> List[RideRequestResponse]:
        """Get all requests assigned to a driver."""
        requests = await self.repo.get_requests_by_driver(driver_id)
        return [RideRequestResponse.from_orm(r) for r in requests]

    async def update_ride_request(
        self,
        request_id: str,
        request_in: RideRequestUpdate
    ) -> RideRequestResponse:
        """Update a ride request."""
        request = await self.repo.get_by_id(request_id)
        if not request:
            raise RideRequestNotFound(f"Ride request {request_id} not found")
        
        request_data = request_in.model_dump(exclude_unset=True)
        updated_request = await self.repo.update(request_id, request_data)
        await self.repo.commit()
        return RideRequestResponse.from_orm(updated_request)

    async def assign_ride(self, request_id: str, driver_id: str) -> RideRequestResponse:
        """Assign a ride to a driver."""
        request = await self.repo.get_by_id(request_id)
        if not request:
            raise RideRequestNotFound(f"Ride request {request_id} not found")
        
        if request.assigned_driver_id:
            raise RideAlreadyAssigned(f"Ride {request_id} is already assigned")
        
        if not request.is_assignable():
            raise InvalidRideStatus(
                f"Ride {request_id} cannot be assigned with status {request.status}"
            )
        
        request.assigned_driver_id = driver_id
        request.status = RideStatus.ASSIGNED
        request.assigned_at = datetime.utcnow()
        await self.repo.commit()
        return RideRequestResponse.from_orm(request)

    async def mark_picked_up(self, request_id: str) -> RideRequestResponse:
        """Mark a ride as picked up."""
        request = await self.repo.get_by_id(request_id)
        if not request:
            raise RideRequestNotFound(f"Ride request {request_id} not found")
        
        if request.status != RideStatus.ASSIGNED:
            raise InvalidRideStatus(
                f"Can only pick up ASSIGNED rides, current status: {request.status}"
            )
        
        request.status = RideStatus.IN_PROGRESS
        request.picked_up_at = datetime.utcnow()
        await self.repo.commit()
        return RideRequestResponse.from_orm(request)

    async def mark_completed(self, request_id: str) -> RideRequestResponse:
        """Mark a ride as completed."""
        request = await self.repo.get_by_id(request_id)
        if not request:
            raise RideRequestNotFound(f"Ride request {request_id} not found")
        
        if request.status != RideStatus.IN_PROGRESS:
            raise InvalidRideStatus(
                f"Can only complete IN_PROGRESS rides, current status: {request.status}"
            )
        
        request.status = RideStatus.COMPLETED
        request.completed_at = datetime.utcnow()
        await self.repo.commit()
        return RideRequestResponse.from_orm(request)

    async def mark_failed(self, request_id: str) -> RideRequestResponse:
        """Mark a ride as failed."""
        request = await self.repo.get_by_id(request_id)
        if not request:
            raise RideRequestNotFound(f"Ride request {request_id} not found")
        
        request.status = RideStatus.FAILED
        request.failed_at = datetime.utcnow()
        await self.repo.commit()
        return RideRequestResponse.from_orm(request)

    async def retry_request(self, request_id: str) -> RideRequestResponse:
        """Retry a failed request."""
        request = await self.repo.get_by_id(request_id)
        if not request:
            raise RideRequestNotFound(f"Ride request {request_id} not found")
        
        if request.status != RideStatus.FAILED:
            raise InvalidRideStatus(
                f"Can only retry FAILED rides, current status: {request.status}"
            )
        
        if not request.can_retry():
            raise CannotRetryRide(
                f"Ride {request_id} has exceeded max retries ({request.max_retries})"
            )
        
        request.retry_count += 1
        request.status = RideStatus.RETRYING
        request.assigned_driver_id = None
        request.assigned_at = None
        await self.repo.commit()
        return RideRequestResponse.from_orm(request)
