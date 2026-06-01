"""Custom application exceptions."""


class RideMatchException(Exception):
    """Base exception for the application."""
    pass


class DriverNotFound(RideMatchException):
    """Raised when a driver is not found."""
    pass


class RideRequestNotFound(RideMatchException):
    """Raised when a ride request is not found."""
    pass


class DriverNotAvailable(RideMatchException):
    """Raised when trying to assign a ride to an unavailable driver."""
    pass


class RideAlreadyAssigned(RideMatchException):
    """Raised when trying to assign an already assigned ride."""
    pass


class CannotRetryRide(RideMatchException):
    """Raised when ride cannot be retried due to max retries exceeded."""
    pass


class InvalidRideStatus(RideMatchException):
    """Raised when performing an invalid operation on a ride with current status."""
    pass


class InvalidStatusTransition(RideMatchException):
    """Raised when an invalid status transition is attempted."""
    pass