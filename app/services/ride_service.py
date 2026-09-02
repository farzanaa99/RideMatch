"""Service layer for ride request operations."""

import os
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.events import DomainEvent, EventBus, EventType
from app.exceptions import (
    CannotRetryRide,
    InvalidRideStatus,
    RideAlreadyAssigned,
    RideRequestNotFound,
)
from app.models.enums import RideStatus
from app.models.ride_request import RideRequest
from app.queue.redis_queue import RedisQueue
from app.repositories.ride_request_repository import RideRequestRepository
from app.schemas import RideRequestCreate, RideRequestResponse, RideRequestUpdate


class RideRequestService:
    """Service for ride request business logic."""

    def __init__(self, session: AsyncSession, event_bus: Optional[EventBus] = None):
        self.session = session
        self.repo = RideRequestRepository(session)
        self.event_bus = event_bus
        self.redis_queue = RedisQueue(os.getenv("REDIS_URL", "redis://localhost:6379/0"))

    @staticmethod
    def _to_response(request: RideRequest) -> RideRequestResponse:
        """Convert ORM model to response schema."""
        assignment_latency = None
        if request.assigned_at and request.created_at:
            latency_ms = (request.assigned_at - request.created_at).total_seconds() * 1000
            assignment_latency = int(latency_ms)
        
        return RideRequestResponse(
            id=request.id,
            rider_id=request.rider_id,
            pickup_lat=request.pickup_lat,
            pickup_lng=request.pickup_lng,
            dropoff_lat=request.dropoff_lat,
            dropoff_lng=request.dropoff_lng,
            pickup_address=request.pickup_address,
            dropoff_address=request.dropoff_address,
            priority=request.priority,
            status=request.status,
            assigned_driver_id=request.assigned_driver_id,
            retry_count=request.retry_count,
            max_retries=request.max_retries,
            assignment_latency_ms=assignment_latency,
            created_at=request.created_at,
            assigned_at=request.assigned_at,
            picked_up_at=request.picked_up_at,
            completed_at=request.completed_at,
            failed_at=request.failed_at,
        )

    async def create_ride_request(self, request_in: RideRequestCreate) -> RideRequestResponse:
        """Create a new ride request."""
        request_data = request_in.model_dump()
        request = await self.repo.create(request_data)
        await self.repo.commit()
        
        # Emit event
        if self.event_bus:
            await self.event_bus.publish(
                DomainEvent(
                    event_type=EventType.RIDE_CREATED,
                    data={
                        "request_id": request.id,
                        "rider_id": request.rider_id,
                        "priority": request.priority.name,
                        "pickup_lat": request.pickup_lat,
                        "pickup_lng": request.pickup_lng,
                    },
                )
            )

        await self.redis_queue.enqueue_once(
            "ride-match-jobs",
            {"ride_id": request.id, "queue": "match"},
            idempotency_key=f"ride:{request.id}:match",
        )

        return self._to_response(request)

    async def get_ride_request(self, request_id: str) -> RideRequestResponse:
        """Get a ride request by ID."""
        request = await self.repo.get_by_id(request_id)
        if not request:
            raise RideRequestNotFound(f"Ride request {request_id} not found")
        return self._to_response(request)

    async def get_all_requests(self, skip: int = 0, limit: int = 100) -> List[RideRequestResponse]:
        """Get all ride requests."""
        requests = await self.repo.get_all(skip, limit)
        return [self._to_response(r) for r in requests]

    async def get_pending_requests(self) -> List[RideRequestResponse]:
        """Get all pending requests."""
        requests = await self.repo.get_pending_requests()
        return [self._to_response(r) for r in requests]

    async def get_requests_by_rider(self, rider_id: str) -> List[RideRequestResponse]:
        """Get all requests for a rider."""
        requests = await self.repo.get_requests_by_rider(rider_id)
        return [self._to_response(r) for r in requests]

    async def get_requests_by_driver(self, driver_id: str) -> List[RideRequestResponse]:
        """Get all requests assigned to a driver."""
        requests = await self.repo.get_requests_by_driver(driver_id)
        return [self._to_response(r) for r in requests]

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
        return self._to_response(updated_request)

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
        request.assigned_at = datetime.now(timezone.utc).replace(tzinfo=None)
        request.transition_to(RideStatus.ASSIGNED, actor="ride_request_service")
        await self.repo.commit()
        return self._to_response(request)

    async def mark_picked_up(self, request_id: str) -> RideRequestResponse:
        """Mark a ride as picked up."""
        request = await self.repo.get_by_id(request_id)
        if not request:
            raise RideRequestNotFound(f"Ride request {request_id} not found")
        
        if request.status != RideStatus.ASSIGNED:
            raise InvalidRideStatus(
                f"Can only pick up ASSIGNED rides, current status: {request.status}"
            )
        
        request.picked_up_at = datetime.now(timezone.utc).replace(tzinfo=None)
        request.transition_to(RideStatus.IN_PROGRESS, actor="ride_request_service")
        await self.repo.commit()
        return self._to_response(request)

    async def mark_completed(self, request_id: str) -> RideRequestResponse:
        """Mark a ride as completed."""
        request = await self.repo.get_by_id(request_id)
        if not request:
            raise RideRequestNotFound(f"Ride request {request_id} not found")
        
        if request.status != RideStatus.IN_PROGRESS:
            raise InvalidRideStatus(
                f"Can only complete IN_PROGRESS rides, current status: {request.status}"
            )
        
        request.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        request.transition_to(RideStatus.COMPLETED, actor="ride_request_service")
        await self.repo.commit()
        return self._to_response(request)

    async def mark_failed(self, request_id: str) -> RideRequestResponse:
        """Mark a ride as failed."""
        request = await self.repo.get_by_id(request_id)
        if not request:
            raise RideRequestNotFound(f"Ride request {request_id} not found")
        
        request.failed_at = datetime.now(timezone.utc).replace(tzinfo=None)
        request.transition_to(RideStatus.FAILED, actor="ride_request_service")
        await self.repo.commit()
        return self._to_response(request)

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
        request.assigned_driver_id = None
        request.assigned_at = None
        request.transition_to(RideStatus.RETRYING, actor="ride_request_service")
        await self.repo.commit()

        await self.redis_queue.enqueue_with_delay_once(
            "ride-retry-jobs",
            {"ride_id": request.id, "queue": "retry"},
            delay_seconds=5,
            idempotency_key=f"ride:{request.id}:retry",
        )

        return self._to_response(request)
