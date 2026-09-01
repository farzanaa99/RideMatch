"""Event handler registry."""

import logging
from typing import Awaitable, Callable

from app.events.models import DomainEvent, EventType

logger = logging.getLogger(__name__)

EventHandler = Callable[[DomainEvent], Awaitable[None]]


class EventHandlerRegistry:
    """Registry for event handlers."""

    def __init__(self):
        self.handlers: dict[EventType, list[EventHandler]] = {}

    def register(self, event_type: EventType):
        """Decorator to register a handler for an event type."""
        def decorator(func: EventHandler) -> EventHandler:
            if event_type not in self.handlers:
                self.handlers[event_type] = []
            self.handlers[event_type].append(func)
            logger.debug(f"Registered handler {func.__name__} for {event_type.value}")
            return func
        return decorator

    def get_handlers(self, event_type: EventType) -> list[EventHandler]:
        """Get all handlers for an event type."""
        return self.handlers.get(event_type, [])

    def get_all_handlers(self) -> dict[EventType, list[EventHandler]]:
        """Get all registered handlers."""
        return self.handlers.copy()
