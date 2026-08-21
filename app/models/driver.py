import uuid
from sqlalchemy import Column, String, Float, Integer, Enum, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.database import Base
from app.models.enums import DriverStatus, RideStatus


class Driver(Base):
    __tablename__ = "drivers"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    driver_name = Column(String(255), nullable=False)
    rating = Column(Float, nullable=False, default=5.0)
    lat = Column(Float, nullable=False)
    lng = Column(Float, nullable=False)
    max_capacity = Column(Integer, nullable=False, default=1)
    status = Column(Enum(DriverStatus), nullable=False, default=DriverStatus.AVAILABLE, index=True)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    
    # Relationships
    rides = relationship("RideRequest", back_populates="driver")

    @property
    def driver_id(self):
        return self.id

    @property
    def current_location(self):
        return (self.lat, self.lng)

    @property
    def active_ride_count(self):
        return len([r for r in self.rides if r.status in (RideStatus.ASSIGNED, RideStatus.EN_ROUTE, RideStatus.IN_PROGRESS)])

    @property
    def is_assignable(self):
        return self.active_ride_count < self.max_capacity and self.status == DriverStatus.AVAILABLE

    def assign_ride(self, ride_request):
        if not self.is_assignable:
            return False

        if any(r.id == ride_request.id for r in self.rides):
            return False

        self.rides.append(ride_request)
        return True

        
    def complete_ride(self, request_id):
        ride = next((r for r in self.rides if r.id == request_id), None)
        if ride:
            ride.status = RideStatus.COMPLETED
            self.rides.remove(ride)
            return True
        return False
    