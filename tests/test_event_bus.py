import asyncio

import pytest

from app.events.bus import EventBus
from app.events.models import DomainEvent, EventType
from app.events.registry import EventHandlerRegistry


@pytest.mark.asyncio
async def test_event_bus_skips_duplicate_event_ids():
    registry = EventHandlerRegistry()
    bus = EventBus(registry)
    calls = 0

    @registry.register(EventType.RIDE_CREATED)
    async def handler(event: DomainEvent):
        nonlocal calls
        calls += 1

    await bus.start()
    event = DomainEvent(event_type=EventType.RIDE_CREATED, event_id="dup-1", data={"request_id": "r-1"})
    await bus.publish(event)
    await bus.publish(event)
    await asyncio.sleep(0.05)
    await bus.stop()

    assert calls == 1


@pytest.mark.asyncio
async def test_event_bus_reuses_idempotency_cache_only_for_bounded_window():
    registry = EventHandlerRegistry()
    bus = EventBus(registry, max_seen_events=1, idempotency_ttl_seconds=0.01)
    calls = 0

    @registry.register(EventType.RIDE_CREATED)
    async def handler(event: DomainEvent):
        nonlocal calls
        calls += 1

    await bus.start()
    await bus.publish(DomainEvent(event_type=EventType.RIDE_CREATED, event_id="e-1", data={"request_id": "r-1"}))
    await bus.publish(DomainEvent(event_type=EventType.RIDE_CREATED, event_id="e-2", data={"request_id": "r-2"}))
    await asyncio.sleep(0.02)
    await bus.publish(DomainEvent(event_type=EventType.RIDE_CREATED, event_id="e-1", data={"request_id": "r-1"}))
    await asyncio.sleep(0.05)
    await bus.stop()

    assert calls == 3


@pytest.mark.asyncio
async def test_event_bus_accumulates_dead_letter_queue():
    registry = EventHandlerRegistry()
    bus = EventBus(registry)

    @registry.register(EventType.RIDE_FAILED)
    async def handler(event: DomainEvent):
        raise RuntimeError("simulated handler failure")

    await bus.start()
    await bus.publish(DomainEvent(event_type=EventType.RIDE_FAILED, event_id="dlq-1", data={"request_id": "r-2"}))
    await asyncio.sleep(0.05)
    await bus.stop()

    assert bus.dead_letter_count() == 1
    assert bus.dead_letter_queue[0][0].event_id == "dlq-1"
