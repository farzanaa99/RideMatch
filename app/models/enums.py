from enum import Enum


class RideStatus(Enum):
    PENDING = "PENDING"
    QUEUED = "QUEUED"
    ASSIGNED = "ASSIGNED"
    EN_ROUTE = "EN_ROUTE"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRYING = "RETRYING"


class RidePriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3

class DriverStatus(Enum):
    AVAILABLE = "AVAILABLE"
    EN_ROUTE = "EN_ROUTE"
    ON_RIDE = "ON_RIDE"

class QueueSortStrategy(Enum):
    FIFO = "fifo"              # Oldest first (fairness)
    PRIORITY = "priority"      # Highest priority first (urgency)
    HYBRID = "hybrid"          # Priority weight + age (best of both)
