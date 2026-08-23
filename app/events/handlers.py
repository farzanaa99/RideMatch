"""Event handlers for ride events."""

import logging
from typing import Optional
from app.events.models import DomainEvent, EventType
from app.events.registry import EventHandlerRegistry
from app.metrics import MetricsCollector

logger = logging.getLogger(__name__)


def register_handlers(
    registry: EventHandlerRegistry,
    metrics_collector: Optional[MetricsCollector] = None,
) -> None:
    """Register all event handlers."""

    @registry.register(EventType.RIDE_CREATED)
    async def on_ride_created(event: DomainEvent):
        """Handle ride created event."""
        request_id = event.data.get("request_id")
        priority = event.data.get("priority")
        logger.info(f"RIDE_CREATED: {request_id} (priority: {priority})")

    @registry.register(EventType.RIDE_QUEUED)
    async def on_ride_queued(event: DomainEvent):
        """Handle ride queued event."""
        request_id = event.data.get("request_id")
        logger.info(f"RIDE_QUEUED: {request_id}")

    @registry.register(EventType.RIDE_ASSIGNED)
    async def on_ride_assigned(event: DomainEvent):
        """Handle ride assigned event."""
        request_id = event.data.get("request_id")
        driver_id = event.data.get("driver_id")
        latency_ms = event.data.get("latency_ms", 0)
        if metrics_collector and driver_id:
            metrics_collector.record_assignment(driver_id, float(latency_ms or 0))
        logger.info(
            f"RIDE_ASSIGNED: {request_id} → {driver_id} "
            f"(latency: {latency_ms:.0f}ms)"
        )

    @registry.register(EventType.RIDE_PICKED_UP)
    async def on_ride_picked_up(event: DomainEvent):
        """Handle ride picked up event."""
        request_id = event.data.get("request_id")
        logger.info(f"RIDE_PICKED_UP: {request_id}")

    @registry.register(EventType.RIDE_IN_PROGRESS)
    async def on_ride_in_progress(event: DomainEvent):
        """Handle ride in progress event."""
        request_id = event.data.get("request_id")
        logger.info(f"RIDE_IN_PROGRESS: {request_id}")

    @registry.register(EventType.RIDE_COMPLETED)
    async def on_ride_completed(event: DomainEvent):
        """Handle ride completed event."""
        request_id = event.data.get("request_id")
        driver_id = event.data.get("driver_id")
        if metrics_collector and driver_id:
            metrics_collector.record_completion(driver_id)
        logger.info(f"RIDE_COMPLETED: {request_id}")

    @registry.register(EventType.RIDE_FAILED)
    async def on_ride_failed(event: DomainEvent):
        """Handle ride failed event."""
        request_id = event.data.get("request_id")
        driver_id = event.data.get("driver_id")
        retry_count = event.data.get("retry_count", 0)
        max_retries = event.data.get("max_retries", 0)
        if metrics_collector:
            metrics_collector.record_failure(driver_id)
        
        if retry_count < max_retries:
            logger.warning(
                f"RIDE_FAILED: {request_id} "
                f"(retry {retry_count}/{max_retries})"
            )
        else:
            logger.error(
                f"RIDE_FAILED: {request_id} "
                f"(max retries exceeded)"
            )

    @registry.register(EventType.RIDE_RETRYING)
    async def on_ride_retrying(event: DomainEvent):
        """Handle ride retrying event."""
        request_id = event.data.get("request_id")
        retry_count = event.data.get("retry_count", 0)
        logger.info(f"RIDE_RETRYING: {request_id} (attempt {retry_count})")

    @registry.register(EventType.RIDE_TIMEOUT)
    async def on_ride_timeout(event: DomainEvent):
        """Handle ride timeout event."""
        request_id = event.data.get("request_id")
        reason = event.data.get("reason", "unknown")
        logger.error(f"RIDE_TIMEOUT: {request_id} ({reason})")

    @registry.register(EventType.DRIVER_AVAILABLE)
    async def on_driver_available(event: DomainEvent):
        """Handle driver available event."""
        driver_id = event.data.get("driver_id")
        logger.debug(f"DRIVER_AVAILABLE: {driver_id}")

    @registry.register(EventType.DRIVER_UNAVAILABLE)
    async def on_driver_unavailable(event: DomainEvent):
        """Handle driver unavailable event."""
        driver_id = event.data.get("driver_id")
        logger.debug(f"DRIVER_UNAVAILABLE: {driver_id}")
