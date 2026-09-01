import argparse
import asyncio
import logging
import math
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import timedelta

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.engine.matching_engine import MatchingEngine  # noqa: E402
from app.models.enums import RidePriority, RideStatus  # noqa: E402

logging.getLogger("app.engine.matching_engine").setLevel(logging.WARNING)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    rank = (len(values) - 1) * p
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return values[low]
    return values[low] + (values[high] - values[low]) * (rank - low)


@dataclass
class BenchRequest:
    request_id: str
    pickup_lat: float
    pickup_lng: float
    dropoff_lat: float
    dropoff_lng: float
    priority: RidePriority
    retry_count: int = 0
    max_retries: int = 3

    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries


@dataclass
class BenchDriver:
    driver_id: str
    lat: float
    lng: float
    max_capacity: int = 2
    rides: list[BenchRequest] = field(default_factory=list)

    @property
    def current_location(self):
        return (self.lat, self.lng)

    @property
    def active_ride_count(self):
        return len(self.rides)

    @property
    def is_assignable(self):
        return self.active_ride_count < self.max_capacity

    def assign_ride(self, req: BenchRequest):
        if not self.is_assignable:
            return False
        self.rides.append(req)
        return True

    def __lt__(self, other: "BenchDriver") -> bool:
        return self.driver_id < other.driver_id


class BenchQueueManager:
    def __init__(self, requests: list[BenchRequest], drivers: list[BenchDriver]):
        self.requests = requests
        self.drivers = drivers
        self.updates: list[tuple[str, RideStatus, str | None]] = []

    async def get_pending_requests(self):
        return self.requests, len(self.requests)

    async def get_available_drivers(self):
        return self.drivers

    async def update_request(
        self,
        request_id: str,
        status: RideStatus,
        driver_id: str | None = None,
    ):
        self.updates.append((request_id, status, driver_id))

    async def get_rides_ready_for_retry(self):
        return []

    @staticmethod
    def _calculate_retry_delay(retry_count: int) -> timedelta:
        return timedelta(seconds=min(5 * (2 ** retry_count), 300))


def build_dataset(requests: int, drivers: int):
    driver_list = [
        BenchDriver(
            driver_id=f"d-{i}",
            lat=40.7128 + (i % 20) * 0.001,
            lng=-74.0060 + (i % 20) * 0.001,
            max_capacity=2,
        )
        for i in range(drivers)
    ]
    request_list = [
        BenchRequest(
            request_id=f"r-{i}",
            pickup_lat=40.7128 + (i % 30) * 0.001,
            pickup_lng=-74.0060 + (i % 30) * 0.001,
            dropoff_lat=40.7428 + (i % 25) * 0.001,
            dropoff_lng=-73.9860 + (i % 25) * 0.001,
            priority=RidePriority((i % 3) + 1),
        )
        for i in range(requests)
    ]
    return request_list, driver_list


async def benchmark_matching_engine(iterations: int, requests: int, drivers: int):
    latencies_ms: list[float] = []
    total_assignments = 0

    for _ in range(iterations):
        reqs, drs = build_dataset(requests, drivers)
        qm = BenchQueueManager(reqs, drs)
        engine = MatchingEngine(qm)

        started = time.perf_counter()
        matches = await engine.match_rides()
        elapsed_ms = (time.perf_counter() - started) * 1000
        latencies_ms.append(elapsed_ms)
        total_assignments += len(matches)

    total_time_s = sum(latencies_ms) / 1000.0
    assignments_per_sec = (total_assignments / total_time_s) if total_time_s else 0.0
    return {
        "latencies_ms": sorted(latencies_ms),
        "assignments": total_assignments,
        "assignments_per_sec": assignments_per_sec,
        "queue_drain_time_ms": max(latencies_ms) if latencies_ms else 0.0,
    }


async def benchmark_db_io(rounds: int):
    db_name = f"perf_bench_{uuid.uuid4().hex}.db"
    db_path = os.path.join(os.getcwd(), db_name)
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    started = time.perf_counter()
    async with session_factory() as session:
        for _ in range(rounds):
            await session.execute(text("SELECT 1"))
        await session.commit()
    elapsed_ms = (time.perf_counter() - started) * 1000

    await engine.dispose()
    if os.path.exists(db_path):
        os.remove(db_path)
    return elapsed_ms


async def benchmark_queue_contention(items: int, workers: int):
    q: asyncio.Queue[int] = asyncio.Queue()

    async def producer():
        for i in range(items):
            await q.put(i)

    async def consumer():
        processed = 0
        while processed < items // workers:
            await q.get()
            processed += 1
            q.task_done()

    started = time.perf_counter()
    await producer()
    tasks = [asyncio.create_task(consumer()) for _ in range(workers)]
    await q.join()
    for task in tasks:
        task.cancel()
    elapsed_ms = (time.perf_counter() - started) * 1000
    return elapsed_ms


def render_report(path: str, summary: dict):
    p50 = summary["p50"]
    p95 = summary["p95"]
    p99 = summary["p99"]
    aps = summary["assignments_per_sec"]
    qdt = summary["queue_drain_time_ms"]
    db_ms = summary["db_io_ms"]
    queue_ms = summary["queue_contention_ms"]

    bottlenecks = sorted(
        [
            ("Database I/O", db_ms),
            ("Scoring loop / matching", p95),
            ("Queue contention", queue_ms),
        ],
        key=lambda x: x[1],
        reverse=True,
    )

    lines = [
        "# Performance Profile Report",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Assignments/sec | {aps:.2f} |",
        f"| p50 batch latency (ms) | {p50:.2f} |",
        f"| p95 batch latency (ms) | {p95:.2f} |",
        f"| p99 batch latency (ms) | {p99:.2f} |",
        f"| Queue drain time (ms) | {qdt:.2f} |",
        f"| DB I/O micro-benchmark (ms) | {db_ms:.2f} |",
        f"| Queue contention micro-benchmark (ms) | {queue_ms:.2f} |",
        "",
        "## Bottleneck Ranking",
    ]
    for name, value in bottlenecks:
        lines.append(f"- {name}: {value:.2f}ms")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


async def main(args):
    match = await benchmark_matching_engine(
        iterations=args.iterations,
        requests=args.requests,
        drivers=args.drivers,
    )
    db_io_ms = await benchmark_db_io(args.db_rounds)
    queue_ms = await benchmark_queue_contention(args.queue_items, args.queue_workers)

    latencies = match["latencies_ms"]
    summary = {
        "assignments_per_sec": match["assignments_per_sec"],
        "p50": percentile(latencies, 0.50),
        "p95": percentile(latencies, 0.95),
        "p99": percentile(latencies, 0.99),
        "queue_drain_time_ms": match["queue_drain_time_ms"],
        "db_io_ms": db_io_ms,
        "queue_contention_ms": queue_ms,
    }

    print("\nPerformance Summary")
    print("=" * 50)
    for key, value in summary.items():
        if "sec" in key:
            print(f"{key}: {value:.2f}")
        else:
            print(f"{key}: {value:.2f}ms")

    render_report(args.report_path, summary)
    print(f"\nReport written to: {args.report_path}")


def parse_args():
    parser = argparse.ArgumentParser(description="RideMatch performance profiling")
    parser.add_argument("--iterations", type=int, default=20)
    parser.add_argument("--requests", type=int, default=200)
    parser.add_argument("--drivers", type=int, default=120)
    parser.add_argument("--db-rounds", type=int, default=500)
    parser.add_argument("--queue-items", type=int, default=10000)
    parser.add_argument("--queue-workers", type=int, default=4)
    parser.add_argument("--report-path", default="scripts/perf_report_latest.md")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(main(parse_args()))
