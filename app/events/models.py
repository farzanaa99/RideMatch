"""Event models and types."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class EventType(Enum):
    """Types of domain events."""
    RIDE_CREATED = "ride.created"
    RIDE_QUEUED = "ride.queued"
    RIDE_ASSIGNED = "ride.assigned"
    RIDE_PICKED_UP = "ride.picked_up"
    RIDE_IN_PROGRESS = "ride.in_progress"
    RIDE_COMPLETED = "ride.completed"
    RIDE_FAILED = "ride.failed"
    RIDE_RETRYING = "ride.retrying"
    RIDE_TIMEOUT = "ride.timeout"
    DRIVER_AVAILABLE = "driver.available"
    DRIVER_UNAVAILABLE = "driver.unavailable"


@dataclass
class DomainEvent:
    """Base domain event.

    Every emitted domain event gets a stable identifier so the bus can enforce
    idempotent processing and record per-event failures in a dead-letter queue.
    """
    event_type: EventType
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __repr__(self) -> str:
        return f"Event({self.event_type.value}, {self.data})"
