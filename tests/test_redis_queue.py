import pytest
import redis.asyncio as redis

from app.queue.redis_queue import RedisQueue


class FakeRedis:
    def __init__(self):
        self.lists = {}
        self.zsets = {}
        self.keys = {}

    async def ping(self):
        return True

    async def rpush(self, name, value):
        self.lists.setdefault(name, []).append(value)
        return len(self.lists[name])

    async def lpop(self, name):
        items = self.lists.setdefault(name, [])
        if not items:
            return None
        return items.pop(0)

    async def zadd(self, name, mapping):
        target = self.zsets.setdefault(name, {})
        for member, score in mapping.items():
            target[member] = float(score)
        return len(target)

    async def zrangebyscore(self, name, min_score, max_score, start=0, num=-1):
        items = self.zsets.setdefault(name, {})
        ordered = [
            member
            for member, score in sorted(items.items(), key=lambda pair: pair[1])
            if min_score <= score <= max_score
        ]
        if num < 0:
            return ordered[start:]
        return ordered[start : start + num]

    async def zrem(self, name, member):
        target = self.zsets.setdefault(name, {})
        if member in target:
            del target[member]
            return 1
        return 0

    async def zcard(self, name):
        return len(self.zsets.setdefault(name, {}))

    async def llen(self, name):
        return len(self.lists.setdefault(name, []))

    async def expire(self, name, seconds):
        return True

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.keys:
            return None
        self.keys[key] = {"value": value, "ex": ex}
        return True

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_redis_queue_enforces_idempotent_enqueue(monkeypatch):
    fake_client = FakeRedis()
    monkeypatch.setattr(redis, "from_url", lambda *args, **kwargs: fake_client)

    queue = RedisQueue("redis://example.test")

    first = await queue.enqueue_once("ride-match-jobs", {"ride_id": 1}, "ride:1:match")
    second = await queue.enqueue_once("ride-match-jobs", {"ride_id": 1}, "ride:1:match")

    assert first is True
    assert second is False
    assert await queue.queue_size("ride-match-jobs") == 1


@pytest.mark.asyncio
async def test_redis_queue_supports_delayed_jobs_and_dead_letter(monkeypatch):
    fake_client = FakeRedis()
    monkeypatch.setattr(redis, "from_url", lambda *args, **kwargs: fake_client)

    queue = RedisQueue("redis://example.test")
    job = {"ride_id": 99, "queue": "retry"}

    await queue.enqueue_with_delay("ride-retry-jobs", job, 0)
    delayed = await queue.dequeue_delayed("ride-retry-jobs")
    assert delayed == job

    await queue.dead_letter("ride-dead-letter-jobs", job, "boom")
    dead = await queue.dequeue_dead_letter("ride-dead-letter-jobs")
    assert dead["payload"] == job
    assert dead["error"] == "boom"


@pytest.mark.asyncio
async def test_redis_queue_falls_back_to_in_memory_when_server_unavailable(monkeypatch):
    monkeypatch.setattr(
        redis,
        "from_url",
        lambda *args, **kwargs: (_ for _ in ()).throw(ConnectionError("offline")),
    )

    queue = RedisQueue("redis://localhost:6379/0")
    queued = await queue.enqueue_once("ride-match-jobs", {"ride_id": 42}, "ride:42:match")
    duplicate = await queue.enqueue_once("ride-match-jobs", {"ride_id": 42}, "ride:42:match")
    job = await queue.dequeue("ride-match-jobs")

    assert queued is True
    assert duplicate is False
    assert job == {"ride_id": 42}
    assert await queue.queue_size("ride-match-jobs") == 0
