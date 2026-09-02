"""Redis-backed job queue for ride matching and retry workflows."""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class RedisQueue:
    """Thin wrapper around Redis for dispatch jobs.

    Uses a standard list/stream pattern for immediate jobs and a sorted set for
    delayed retry scheduling. The database remains the source of truth for ride
    state; Redis is used solely for operational job transport and scheduling.
    """

    def __init__(self, redis_url: str | None = None):
        self.redis_url = redis_url or os.getenv(
            "REDIS_URL",
            "redis://localhost:6379/0",
        )
        self.enabled = os.getenv("REDIS_ENABLED", "true").lower() not in {
            "0",
            "false",
            "no",
        }
        self.client = None
        self._memory_keys: set[str] = set()
        self._memory_queues: dict[str, list[str]] = {}
        self._memory_zsets: dict[str, dict[str, float]] = {}

        try:
            self.client = redis.from_url(self.redis_url, decode_responses=True)
        except Exception as exc:  # pragma: no cover - depends on external service
            self.enabled = False
            logger.warning(
                "Redis unavailable at startup; falling back to in-memory queue mode: %s",
                exc,
            )

    @staticmethod
    def _make_job_id(queue_name: str, payload: dict[str, Any]) -> str:
        return f"{queue_name}:{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"

    async def _call_redis(self, action: str, callback, default=None):
        try:
            return await callback()
        except Exception as exc:  # pragma: no cover - depends on external service
            if self.enabled:
                logger.warning("Redis unavailable during %s; falling back to in-memory queue mode: %s", action, exc)
            self.enabled = False
            return default

    async def ping(self) -> bool:
        if not self.enabled:
            return False
        return bool(await self._call_redis("ping", self.client.ping, False))

    async def add_idempotency_key(self, key: str, ttl_seconds: int = 3600) -> bool:
        if not self.enabled:
            if key in self._memory_keys:
                return False
            self._memory_keys.add(key)
            return True
        result = await self._call_redis(
            "idempotency key set",
            lambda: self.client.set(key, "1", ex=ttl_seconds, nx=True),
            False,
        )
        return bool(result)

    async def enqueue(
        self,
        queue_name: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        ttl_seconds: int = 3600,
    ) -> bool:
        if idempotency_key:
            lock_name = f"queue:{queue_name}:{idempotency_key}"
            if not await self.add_idempotency_key(lock_name, ttl_seconds=ttl_seconds):
                return False

        if not self.enabled:
            self._memory_queues.setdefault(queue_name, []).append(
                json.dumps(payload, sort_keys=True)
            )
            return True

        await self._call_redis(
            "enqueue",
            lambda: self.client.rpush(queue_name, json.dumps(payload, sort_keys=True)),
            0,
        )
        return True

    async def enqueue_once(
        self,
        queue_name: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        ttl_seconds: int = 3600,
    ) -> bool:
        return await self.enqueue(
            queue_name=queue_name,
            payload=payload,
            idempotency_key=idempotency_key or self._make_job_id(queue_name, payload),
            ttl_seconds=ttl_seconds,
        )

    async def enqueue_with_delay(
        self,
        queue_name: str,
        payload: dict[str, Any],
        delay_seconds: int,
        idempotency_key: str | None = None,
        ttl_seconds: int = 3600,
    ) -> bool:
        if idempotency_key is None:
            idempotency_key = self._make_job_id(queue_name, payload)

        lock_name = f"delay:{queue_name}:{idempotency_key}"
        if not await self.add_idempotency_key(lock_name, ttl_seconds=ttl_seconds):
            return False

        run_at = datetime.now(timezone.utc).timestamp() + delay_seconds
        entry = {
            "job_id": idempotency_key,
            "payload": payload,
        }

        if not self.enabled:
            target = self._memory_zsets.setdefault(queue_name, {})
            target[json.dumps(entry, sort_keys=True)] = run_at
            return True

        await self._call_redis(
            "enqueue_with_delay",
            lambda: self.client.zadd(queue_name, {json.dumps(entry, sort_keys=True): run_at}),
            0,
        )
        return True

    async def enqueue_with_delay_once(
        self,
        queue_name: str,
        payload: dict[str, Any],
        delay_seconds: int,
        idempotency_key: str | None = None,
        ttl_seconds: int = 3600,
    ) -> bool:
        return await self.enqueue_with_delay(
            queue_name=queue_name,
            payload=payload,
            delay_seconds=delay_seconds,
            idempotency_key=idempotency_key or self._make_job_id(queue_name, payload),
            ttl_seconds=ttl_seconds,
        )

    async def dequeue(self, queue_name: str) -> dict[str, Any] | None:
        if not self.enabled:
            items = self._memory_queues.get(queue_name, [])
            if not items:
                return None
            raw = items.pop(0)
            return json.loads(raw)

        raw = await self._call_redis("dequeue", lambda: self.client.lpop(queue_name), None)
        if raw is None:
            return None
        return json.loads(raw)

    async def dequeue_delayed(self, queue_name: str) -> dict[str, Any] | None:
        if not self.enabled:
            now = datetime.now(timezone.utc).timestamp()
            items = self._memory_zsets.get(queue_name, {})
            ready = [
                (member, score)
                for member, score in sorted(items.items(), key=lambda item: item[1])
                if score <= now
            ]
            if not ready:
                return None
            member, _ = ready[0]
            del items[member]
            payload = json.loads(member)
            if isinstance(payload, dict) and "payload" in payload:
                return payload["payload"]
            return payload

        now = datetime.now(timezone.utc).timestamp()
        raw = await self._call_redis(
            "dequeue delayed",
            lambda: self.client.zrangebyscore(queue_name, 0, now, start=0, num=1),
            [],
        )
        if not raw:
            return None
        item = raw[0]
        await self._call_redis("remove delayed item", lambda: self.client.zrem(queue_name, item), 0)
        payload = json.loads(item)
        if isinstance(payload, dict) and "payload" in payload:
            return payload["payload"]
        return payload

    async def dead_letter(
        self,
        queue_name: str,
        payload: dict[str, Any],
        error: str,
        ttl_seconds: int = 86400,
    ) -> bool:
        entry = {
            "payload": payload,
            "error": error,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if not self.enabled:
            self._memory_queues.setdefault(queue_name, []).append(json.dumps(entry, sort_keys=True))
            return True
        await self._call_redis(
            "dead_letter",
            lambda: self.client.rpush(queue_name, json.dumps(entry, sort_keys=True)),
            0,
        )
        if ttl_seconds:
            await self._call_redis("dead_letter ttl", lambda: self.client.expire(queue_name, ttl_seconds), 0)
        return True

    async def dequeue_dead_letter(self, queue_name: str) -> dict[str, Any] | None:
        if not self.enabled:
            items = self._memory_queues.get(queue_name, [])
            if not items:
                return None
            raw = items.pop(0)
            return json.loads(raw)

        raw = await self._call_redis("dequeue dead letter", lambda: self.client.lpop(queue_name), None)
        if raw is None:
            return None
        return json.loads(raw)

    async def queue_size(self, queue_name: str) -> int:
        if not self.enabled:
            return len(self._memory_queues.get(queue_name, []))
        return int(await self._call_redis("queue size", lambda: self.client.llen(queue_name), 0))

    async def delayed_queue_size(self, queue_name: str) -> int:
        if not self.enabled:
            return len(self._memory_zsets.get(queue_name, {}))
        return int(await self._call_redis("delayed queue size", lambda: self.client.zcard(queue_name), 0))

    async def get_metrics(self) -> dict[str, Any]:
        return {
            "redis_enabled": self.enabled,
            "queue_depth": await self.queue_size("ride-match-jobs"),
            "delayed_queue_depth": await self.delayed_queue_size("ride-retry-jobs"),
            "dead_letter_depth": await self.queue_size("ride-dead-letter-jobs"),
        }

    async def close(self) -> None:
        if self.enabled:
            await self._call_redis("close", self.client.aclose, None)
