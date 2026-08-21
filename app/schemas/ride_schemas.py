"""Pydantic schemas for ride requests, responses, and matching results."""
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
from datetime import datetime
from app.models.enums import RideStatus, RidePriority


class RideRequestBase(BaseModel):
    """Base ride request schema."""
    rider_id: str
    pickup_lat: float
    pickup_lng: float
    dropoff_lat: float
    dropoff_lng: float
    pickup_address: Optional[str] = None
    dropoff_address: Optional[str] = None
    priority: RidePriority = RidePriority.NORMAL


class RideRequestCreate(RideRequestBase):
    """Schema for creating a ride request."""
    max_retries: int = Field(default=3, ge=1, le=10)


class RideRequestUpdate(BaseModel):
    """Schema for updating a ride request."""
    status: Optional[RideStatus] = None
    priority: Optional[RidePriority] = None
    assigned_driver_id: Optional[str] = None


class RideRequestResponse(RideRequestBase):
    """Schema for ride request response."""
    id: str
    status: RideStatus
    assigned_driver_id: Optional[str] = None
    retry_count: int
    max_retries: int
    assignment_latency_ms: Optional[int] = None
    created_at: datetime
    assigned_at: Optional[datetime] = None
    picked_up_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    failed_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class MatchResult(BaseModel):
    """Schema for a single match result."""
    request_id: str
    driver_id: str
    driver_name: str
    rating: float
    score: float = Field(ge=0.0, le=1.0)


class MatchingBatchResponse(BaseModel):
    """Schema for batch matching response."""
    total_requests: int
    total_matches: int
    unmatched_count: int
    matches: list[MatchResult]
    execution_time_ms: float
