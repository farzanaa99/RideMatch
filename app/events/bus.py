"""Event bus implementation."""

import asyncio
import logging
import time
from collections import OrderedDict
from typing import Optional

from app.events.models import DomainEvent
from app.events.registry import EventHandlerRegistry
from app.metrics import MetricsCollector

logger = logging.getLogger(__name__)


class EventBus:
    """Pub/Sub event bus using asyncio.Queue."""

    def __init__(
        self,
        registry: EventHandlerRegistry,
        metrics_collector: Optional[MetricsCollector] = None,
        max_seen_events: int = 10_000,
        idempotency_ttl_seconds: float = 3600.0,
    ):
        self.registry = registry
        self.metrics_collector = metrics_collector
        self.queue: asyncio.Queue[DomainEvent] = asyncio.Queue()
        self.is_running = False
        self.processor_task: Optional[asyncio.Task] = None
        self.max_seen_events = max_seen_events
        self.idempotency_ttl_seconds = idempotency_ttl_seconds
        self.seen_event_ids: set[str] = set()
        self._seen_event_timestamps: OrderedDict[str, float] = OrderedDict()
        self.dead_letter_queue: list[tuple[DomainEvent, Exception, str]] = []
        self.metrics = {
            "events_published": 0,
            "events_processed": 0,
            "events_failed": 0,
            "events_duplicate_skipped": 0,
            "events_dead_lettered": 0,
        }

    def _prune_seen_event_ids(self) -> None:
        """Remove expired or over-capacity event IDs to keep idempotency bounded."""
        now = time.monotonic()
        expired_ids = [
            event_id
            for event_id, timestamp in self._seen_event_timestamps.items()
            if now - timestamp > self.idempotency_ttl_seconds
        ]
        for event_id in expired_ids:
            self._seen_event_timestamps.pop(event_id, None)
            self.seen_event_ids.discard(event_id)

        while len(self._seen_event_timestamps) > self.max_seen_events:
            oldest_event_id, _ = self._seen_event_timestamps.popitem(last=False)
            self.seen_event_ids.discard(oldest_event_id)

    def dead_letter_count(self) -> int:
        """Return the number of events currently in the dead-letter queue."""
        return len(self.dead_letter_queue)

    async def publish(self, event: DomainEvent) -> None:
        """Publish an event to the bus while enforcing idempotency."""
        self._prune_seen_event_ids()
        if event.event_id in self.seen_event_ids:
            self.metrics["events_duplicate_skipped"] += 1
            logger.info(
                "Duplicate event dropped: %s (%s)",
                event.event_type.value,
                event.event_id,
            )
            return

        self.seen_event_ids.add(event.event_id)
        self._seen_event_timestamps[event.event_id] = time.monotonic()
        await self.queue.put(event)
        self.metrics["events_published"] += 1
        logger.debug("Published event: %s (%s)", event.event_type.value, event.event_id)

    async def start(self) -> None:
        """Start processing events."""
        if self.is_running:
            logger.warning("Event bus already running")
            return

        self.is_running = True
        self.processor_task = asyncio.create_task(self._process_events())
        logger.info("Event bus started")

    async def stop(self) -> None:
        """Stop processing events gracefully."""
        self.is_running = False
        if self.processor_task and not self.processor_task.done():
            self.processor_task.cancel()
            try:
                await self.processor_task
            except asyncio.CancelledError:
                pass
        logger.info("Event bus stopped")

    async def _process_events(self) -> None:
        """Process events from the queue."""
        while self.is_running:
            try:
                event = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            try:
                handlers = self.registry.get_handlers(event.event_type)
                if not handlers:
                    logger.debug("No handlers for event: %s", event.event_type.value)
                    self.queue.task_done()
                    continue

                results = await asyncio.gather(
                    *[handler(event) for handler in handlers],
                    return_exceptions=True,
                )

                for handler, result in zip(handlers, results):
                    if isinstance(result, Exception):
                        handler_name = getattr(
                            handler,
                            "__name__",
                            handler.__class__.__name__,
                        )
                        logger.error(
                            "Handler %s failed for %s: %s",
                            handler_name,
                            event.event_type.value,
                            result,
                        )
                        self.dead_letter_queue.append((event, result, handler_name))
                        self.metrics["events_failed"] += 1
                        self.metrics["events_dead_lettered"] = len(
                            self.dead_letter_queue
                        )

                self.metrics["events_processed"] += 1
                logger.debug(
                    "Processed event: %s (%s)",
                    event.event_type.value,
                    event.event_id,
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover - sanity guard
                self.metrics["events_failed"] += 1
                self.dead_letter_queue.append((event, exc, "event_bus"))
                self.metrics["events_dead_lettered"] = len(self.dead_letter_queue)
                logger.exception(
                    "Error processing event %s: %s",
                    event.event_type.value,
                    exc,
                )
            finally:
                self.queue.task_done()

    def get_metrics(self) -> dict:
        """Get event bus metrics."""
        metrics = self.metrics.copy()
        metrics["queue_depth"] = self.queue.qsize()
        metrics["dead_letter_count"] = self.dead_letter_count()
        if self.metrics_collector:
            self.metrics_collector.set_queue_depth(self.queue.qsize())
        return metrics

    def queue_size(self) -> int:
        """Get current queue size."""
        return self.queue.qsize()
