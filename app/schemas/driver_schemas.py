"""Pydantic schemas for driver data and responses."""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from app.models.enums import DriverStatus


class DriverBase(BaseModel):
    """Base driver schema."""
    driver_name: str
    rating: float = Field(ge=1.0, le=5.0)
    lat: float
    lng: float
    max_capacity: int = Field(ge=1, le=10, default=1)


class DriverCreate(DriverBase):
    """Schema for creating a driver."""
    pass


class DriverUpdate(BaseModel):
    """Schema for updating a driver."""
    driver_name: Optional[str] = None
    rating: Optional[float] = Field(None, ge=1.0, le=5.0)
    lat: Optional[float] = None
    lng: Optional[float] = None
    status: Optional[DriverStatus] = None
    max_capacity: Optional[int] = Field(None, ge=1, le=10)


class DriverResponse(DriverBase):
    """Schema for driver response."""
    id: str
    status: DriverStatus
    active_ride_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True
        populate_by_name = True
