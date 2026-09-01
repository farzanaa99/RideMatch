
"""Finite state machine for ride request lifecycle.

Validates state transitions and logs all changes.
Terminal states: COMPLETED, FAILED (when retry_count exceeded).
"""

import logging

from app.exceptions import InvalidStatusTransition
from app.models.enums import RideStatus

logger = logging.getLogger(__name__)


class RideStateMachine:
    """Validates and logs ride status transitions.
    
    Enforces the following state machine:
    
    Happy path:
        PENDING → QUEUED → ASSIGNED → EN_ROUTE → IN_PROGRESS → COMPLETED
    
    Failure paths:
        Any state → FAILED → RETRYING → ASSIGNED (retry loop)
        or FAILED (permanent if retries exhausted)
    """

    VALID_TRANSITIONS = {
        RideStatus.PENDING: {RideStatus.QUEUED, RideStatus.FAILED},
        RideStatus.QUEUED: {RideStatus.ASSIGNED, RideStatus.FAILED},
        RideStatus.ASSIGNED: {
            RideStatus.EN_ROUTE,
            RideStatus.IN_PROGRESS,
            RideStatus.FAILED,
            RideStatus.RETRYING,
        },
        RideStatus.EN_ROUTE: {RideStatus.IN_PROGRESS, RideStatus.FAILED},
        RideStatus.IN_PROGRESS: {RideStatus.COMPLETED, RideStatus.FAILED},
        RideStatus.COMPLETED: set(),  # Terminal state
        RideStatus.FAILED: {RideStatus.RETRYING},  # Only option from FAILED
        RideStatus.RETRYING: {
            RideStatus.ASSIGNED,
            RideStatus.FAILED,
            RideStatus.PENDING,
        },
    }

    @staticmethod
    def validate_transition(current: RideStatus, next: RideStatus, actor: str) -> None:
        """Validate a state transition.

        Args:
            current: Current ride status
            next: Requested new status
            actor: Who/what is requesting the transition
                   (e.g., "matching_engine", "driver", "system")

        Raises:
            InvalidStatusTransition: If transition is not allowed
        """
        allowed_transitions = RideStateMachine.VALID_TRANSITIONS.get(current, set())

        if next not in allowed_transitions:
            raise InvalidStatusTransition(
                f"{actor} cannot transition {current.value} → {next.value}. "
                f"Allowed: {[s.value for s in allowed_transitions]}"
            )

        logger.info(f"Transition [{actor}]: {current.value} → {next.value}")