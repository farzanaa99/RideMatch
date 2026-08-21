import argparse
import asyncio
import random
import time
import uuid

import httpx


def build_payload(lat_center: float, lng_center: float, spread_km: float, max_retries: int) -> dict:
    # Rough conversion where 1 degree lat/lng ~ 111km for simulator-scale jitter.
    spread_deg = spread_km / 111.0
    pickup_lat = lat_center + random.uniform(-spread_deg, spread_deg)
    pickup_lng = lng_center + random.uniform(-spread_deg, spread_deg)
    dropoff_lat = lat_center + random.uniform(-spread_deg, spread_deg)
    dropoff_lng = lng_center + random.uniform(-spread_deg, spread_deg)

    return {
        "rider_id": str(uuid.uuid4()),
        "pickup_lat": round(pickup_lat, 6),
        "pickup_lng": round(pickup_lng, 6),
        "dropoff_lat": round(dropoff_lat, 6),
        "dropoff_lng": round(dropoff_lng, 6),
        "priority": random.choice([1, 2, 3]),
        "max_retries": max_retries,
    }


async def post_ride(client: httpx.AsyncClient, base_url: str, payload: dict) -> tuple[int, float]:
    started = time.perf_counter()
    response = await client.post(f"{base_url}/api/v1/rides/", json=payload)
    elapsed_ms = (time.perf_counter() - started) * 1000
    return response.status_code, elapsed_ms


async def run_simulation(args):
    created = 0
    failed = 0
    latencies_ms: list[float] = []

    async with httpx.AsyncClient(timeout=args.timeout_seconds) as client:
        for i in range(args.count):
            if args.burst_every > 0 and i > 0 and i % args.burst_every == 0:
                burst_payloads = [
                    build_payload(args.lat_center, args.lng_center, args.spread_km, args.max_retries)
                    for _ in range(args.burst_size)
                ]
                tasks = [post_ride(client, args.base_url, payload) for payload in burst_payloads]
                results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in results:
                    if isinstance(result, Exception):
                        failed += 1
                        continue
                    status_code, elapsed_ms = result
                    latencies_ms.append(elapsed_ms)
                    if status_code == 201:
                        created += 1
                    else:
                        failed += 1

                await asyncio.sleep(args.burst_interval_seconds)
                continue

            payload = build_payload(args.lat_center, args.lng_center, args.spread_km, args.max_retries)
            try:
                status_code, elapsed_ms = await post_ride(client, args.base_url, payload)
                latencies_ms.append(elapsed_ms)
                if status_code == 201:
                    created += 1
                else:
                    failed += 1
            except Exception:
                failed += 1

            # Jittered inter-arrival delays.
            await asyncio.sleep(random.uniform(args.min_interval_seconds, args.max_interval_seconds))

    total = created + failed
    avg_ms = (sum(latencies_ms) / len(latencies_ms)) if latencies_ms else 0.0
    print("\\nRide Request Simulator Summary")
    print("=" * 40)
    print(f"Base URL: {args.base_url}")
    print(f"Total attempted: {total}")
    print(f"Created (201): {created}")
    print(f"Failed: {failed}")
    print(f"Average request latency: {avg_ms:.2f}ms")


def parse_args():
    parser = argparse.ArgumentParser(description="Async ride request load simulator")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--count", type=int, default=200, help="Total requests to send")
    parser.add_argument("--min-interval-seconds", type=float, default=0.05, help="Minimum inter-arrival time")
    parser.add_argument("--max-interval-seconds", type=float, default=0.25, help="Maximum inter-arrival time")
    parser.add_argument("--burst-every", type=int, default=0, help="Emit a burst every N requests (0 disables burst mode)")
    parser.add_argument("--burst-size", type=int, default=20, help="Requests in each burst")
    parser.add_argument("--burst-interval-seconds", type=float, default=2.0, help="Sleep between bursts")
    parser.add_argument("--lat-center", type=float, default=40.7128, help="Center latitude")
    parser.add_argument("--lng-center", type=float, default=-74.0060, help="Center longitude")
    parser.add_argument("--spread-km", type=float, default=8.0, help="Coordinate jitter radius")
    parser.add_argument("--max-retries", type=int, default=3, help="max_retries field in generated rides")
    parser.add_argument("--timeout-seconds", type=float, default=10.0, help="HTTP timeout")
    return parser.parse_args()


if __name__ == "__main__":
    asyncio.run(run_simulation(parse_args()))
