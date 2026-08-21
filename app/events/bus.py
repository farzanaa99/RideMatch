"""Event bus implementation."""

import asyncio
import logging
from typing import Optional

from app.events.models import DomainEvent, EventType
from app.events.registry import EventHandlerRegistry
from app.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class EventBus:
    """Pub/Sub event bus using asyncio.Queue."""

    def __init__(
        self,
        registry: EventHandlerRegistry,
        metrics_collector: Optional[MetricsCollector] = None,
    ):
        self.registry = registry
        self.metrics_collector = metrics_collector
        self.queue: asyncio.Queue[DomainEvent] = asyncio.Queue()
        self.is_running = False
        self.processor_task: Optional[asyncio.Task] = None
        self.metrics = {
            "events_published": 0,
            "events_processed": 0,
            "events_failed": 0,
        }

    async def publish(self, event: DomainEvent) -> None:
        """Publish an event to the bus."""
        await self.queue.put(event)
        self.metrics["events_published"] += 1
        logger.debug(f"Published event: {event.event_type.value}")

    async def start(self) -> None:
        """Start processing events."""
        if self.is_running:
            logger.warning("Event bus already running")
            return

        self.is_running = True
        self.processor_task = asyncio.create_task(self._process_events())
        logger.info("Event bus started")

    async def stop(self) -> None:
        """Stop processing events."""
        self.is_running = False
        if self.processor_task:
            try:
                await self.processor_task
            except asyncio.CancelledError:
                pass
        logger.info("Event bus stopped")

    async def _process_events(self) -> None:
        """Process events from the queue."""
        while self.is_running:
            try:
                # Get event from queue with timeout to allow graceful shutdown
                event = await asyncio.wait_for(self.queue.get(), timeout=1.0)

                # Get all handlers for this event type
                handlers = self.registry.get_handlers(event.event_type)

                if not handlers:
                    logger.debug(f"No handlers for event: {event.event_type.value}")
                    continue

                # Execute all handlers concurrently
                try:
                    results = await asyncio.gather(
                        *[handler(event) for handler in handlers],
                        return_exceptions=True
                    )
                    
                    # Check for exceptions
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            logger.error(
                                f"Handler {handlers[i].__name__} failed for "
                                f"{event.event_type.value}: {result}"
                            )
                            self.metrics["events_failed"] += 1
                    
                    self.metrics["events_processed"] += 1
                    logger.debug(f"Processed event: {event.event_type.value}")

                except Exception as e:
                    self.metrics["events_failed"] += 1
                    logger.exception(
                        f"Error processing event {event.event_type.value}: {e}"
                    )

            except asyncio.TimeoutError:
                # Queue timeout, continue loop to check if bus should stop
                continue
            except Exception as e:
                logger.exception(f"Unexpected error in event processor: {e}")

    def get_metrics(self) -> dict:
        """Get event bus metrics."""
        metrics = self.metrics.copy()
        metrics["queue_depth"] = self.queue.qsize()
        if self.metrics_collector:
            self.metrics_collector.set_queue_depth(self.queue.qsize())
        return metrics

    def queue_size(self) -> int:
        """Get current queue size."""
        return self.queue.qsize()
