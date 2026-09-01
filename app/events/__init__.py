"""Event bus and event handling."""

from app.events.bus import EventBus
from app.events.handlers import register_handlers
from app.events.models import DomainEvent, EventType
from app.events.registry import EventHandlerRegistry

__all__ = [
    "DomainEvent",
    "EventType",
    "EventHandlerRegistry",
    "EventBus",
    "register_handlers",
]
