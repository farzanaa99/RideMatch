import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base
from app.engine.state_machine import RideStateMachine
from app.models.enums import RidePriority, RideStatus


class RideRequest(Base):
    __tablename__ = "ride_requests"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    rider_id = Column(String(255), nullable=False, index=True)
    pickup_lat = Column(Float, nullable=False)
    pickup_lng = Column(Float, nullable=False)
    dropoff_lat = Column(Float, nullable=False)
    dropoff_lng = Column(Float, nullable=False)
    pickup_address = Column(String(255), nullable=True)
    dropoff_address = Column(String(255), nullable=True)
    
    priority = Column(Enum(RidePriority), nullable=False, default=RidePriority.NORMAL)
    status = Column(Enum(RideStatus), nullable=False, default=RideStatus.PENDING, index=True)
    
    # Retry logic
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)
    
    # Assignment
    assigned_driver_id = Column(String(36), ForeignKey("drivers.id"), nullable=True)
    
    # Lifecycle timestamps
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    queued_at = Column(DateTime, nullable=True)
    assigned_at = Column(DateTime, nullable=True)
    picked_up_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    failed_at = Column(DateTime, nullable=True)
    
    # Relationships
    driver = relationship("Driver", back_populates="rides")

    @property
    def request_id(self):
        return self.id

    def is_assignable(self):
        assignable_statuses = {RideStatus.PENDING, RideStatus.QUEUED, RideStatus.RETRYING}
        return self.status in assignable_statuses

    def can_retry(self):
        return self.retry_count < self.max_retries

    def transition_to(self, next_status: RideStatus, actor: str = "ride_request") -> "RideRequest":
        """Apply a validated state transition for this ride request.

        The state machine remains the single source of truth for all lifecycle
        validation, while the domain object owns the mutation itself.
        """
        RideStateMachine.validate_transition(
            current=self.status,
            next=next_status,
            actor=actor,
        )
        self.status = next_status
        return self

    @property
    def assignment_latency_ms(self):
        if self.assigned_at is None:
            return None
        delta = self.assigned_at - self.created_at
        return int(delta.total_seconds() * 1000)