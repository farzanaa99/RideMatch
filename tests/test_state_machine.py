import pytest

from app.engine.state_machine import RideStateMachine
from app.exceptions import InvalidStatusTransition
from app.models.enums import RideStatus


def test_invalid_transition_raises():
    with pytest.raises(InvalidStatusTransition):
        RideStateMachine.validate_transition(
            current=RideStatus.PENDING,
            next=RideStatus.COMPLETED,
            actor="test",
        )


def test_valid_happy_path_transitions():
    RideStateMachine.validate_transition(RideStatus.PENDING, RideStatus.QUEUED, "test")
    RideStateMachine.validate_transition(RideStatus.QUEUED, RideStatus.ASSIGNED, "test")
    RideStateMachine.validate_transition(RideStatus.ASSIGNED, RideStatus.EN_ROUTE, "test")
    RideStateMachine.validate_transition(RideStatus.EN_ROUTE, RideStatus.IN_PROGRESS, "test")
    RideStateMachine.validate_transition(RideStatus.IN_PROGRESS, RideStatus.COMPLETED, "test")
