import math
from dataclasses import dataclass
from datetime import datetime, timezone
from app.models.enums import RideStatus, RidePriority
import heapq
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class MatchingConfig:

    name: str = "balanced"
    distance_weight: float = 0.4
    priority_weight: float = 0.3
    workload_weight: float = 0.2
    dropoff_weight: float = 0.1
    max_driver_distance: float = 50.0

    def validate(self):
        """Validate that weights sum to 1.0 and are all non-negative."""
        total_weight = (
            self.distance_weight + self.priority_weight + 
            self.workload_weight + self.dropoff_weight
        )
        if not (0.99 <= total_weight <= 1.01):  # Allow small floating-point error
            raise ValueError(
                f"Weights must sum to 1.0, got {total_weight}. "
                f"({self.distance_weight} + {self.priority_weight} + "
                f"{self.workload_weight} + {self.dropoff_weight})"
            )
        
        if any(w < 0 for w in [
            self.distance_weight, self.priority_weight,
            self.workload_weight, self.dropoff_weight
        ]):
            raise ValueError("All weights must be non-negative")
        
        if self.max_driver_distance <= 0:
            raise ValueError("max_driver_distance must be positive")


# Preset configs for different matching strategies
BALANCED_CONFIG = MatchingConfig(
    name="balanced",
    distance_weight=0.4,
    priority_weight=0.3,
    workload_weight=0.2,
    dropoff_weight=0.1,
    max_driver_distance=50.0
)

SPEED_FOCUSED_CONFIG = MatchingConfig(
    name="speed_focused",
    distance_weight=0.6,  # Prioritize closeness
    priority_weight=0.2,
    workload_weight=0.1,
    dropoff_weight=0.1,
    max_driver_distance=30.0  # Stricter distance
)

QUALITY_FOCUSED_CONFIG = MatchingConfig(
    name="quality_focused",
    distance_weight=0.3,
    priority_weight=0.4,  # Prioritize urgent rides
    workload_weight=0.2,
    dropoff_weight=0.1,
    max_driver_distance=60.0  # More lenient distance
)

def haversine_distance(loc1, loc2):
    R = 6371  # Earth radius in km
    lat1, lng1 = math.radians(loc1[0]), math.radians(loc1[1])
    lat2, lng2 = math.radians(loc2[0]), math.radians(loc2[1])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))

class MatchingEngine:

    def __init__(self, queue_manager, config: MatchingConfig = None):
        self.queue_manager = queue_manager
        self.config = config or BALANCED_CONFIG
        self.config.validate()

    def calculate_score(self, driver, ride_request):

        # Calculate proximity (distance to pickup)
        pickup_dist = haversine_distance(
            driver.current_location,
            (ride_request.pickup_lat, ride_request.pickup_lng)
        )
        proximity = 1 / (1 + pickup_dist)
        
        # Normalize priority from enum (LOW=1, NORMAL=2, HIGH=3) to 0-1 range
        priority_value = ride_request.priority.value if hasattr(ride_request.priority, 'value') else ride_request.priority
        priority_normalized = priority_value / 3.0  # Normalize to 0-1 range
        
        # Calculate workload (driver capacity usage)
        workload = 1 / (1 + driver.active_ride_count)
        
        # Calculate dropoff alignment
        dropoff_dist = haversine_distance(
            driver.current_location,
            (ride_request.dropoff_lat, ride_request.dropoff_lng)
        )
        dropoff_align = 1 / (1 + dropoff_dist)
 
        # Weighted score
        score = (
            proximity            * self.config.distance_weight +
            priority_normalized  * self.config.priority_weight +
            workload             * self.config.workload_weight +
            dropoff_align        * self.config.dropoff_weight
        )

        logger.debug(
            "Score for driver %s on request %s: %.3f "
            "(proximity=%.3f, priority_norm=%.3f, workload=%.3f, dropoff=%.3f) "
            "using config '%s'",
            driver.driver_id, ride_request.request_id,
            score, proximity, priority_normalized, workload, dropoff_align,
            self.config.name
        )

        return score

    async def match_rides(self):
        try:
            # Fetch pending requests and available drivers
            ride_requests, total_count = await self.queue_manager.get_pending_requests()
            available_drivers = await self.queue_manager.get_available_drivers()
            
            matches = []
            
            # Try to match each request with a driver
            for request in ride_requests:
                heap = []
                
                # Score all eligible drivers for this request
                for driver in available_drivers:
                    if not driver.is_assignable:
                        continue
                    
                    pickup_dist = haversine_distance(
                        driver.current_location,
                        (request.pickup_lat, request.pickup_lng)
                    )
                    
                    if pickup_dist > self.config.max_driver_distance:
                        logger.debug(
                            "Driver %s skipped — %.1f km exceeds threshold.",
                            driver.driver_id, pickup_dist,
                        )
                        continue
                    
                    score = self.calculate_score(driver, request)
                    heapq.heappush(heap, (-score, driver))
                
                # No eligible drivers found — schedule retry or permanently fail
                if not heap:
                    if request.can_retry():
                        # Increment retry count and calculate backoff delay
                        request.retry_count += 1
                        delay = self.queue_manager._calculate_retry_delay(request.retry_count)
                        request.retry_scheduled_at = datetime.now(timezone.utc) + delay

                        await self.queue_manager.update_request(
                            request_id=request.request_id,
                            status=RideStatus.RETRYING,
                        )
                        logger.info(
                            "No driver for request %s — retry %d/%d scheduled in %.0fs.",
                            request.request_id,
                            request.retry_count,
                            request.max_retries,
                            delay.total_seconds(),
                        )
                    else:
                        # Retries exhausted — permanently fail
                        await self.queue_manager.update_request(
                            request_id=request.request_id,
                            status=RideStatus.FAILED,
                        )
                        logger.warning(
                            "Request %s permanently failed after %d retries.",
                            request.request_id,
                            request.retry_count,
                        )
                    continue
                
                # Get best-scoring driver
                best_score, best_driver = heapq.heappop(heap)
                
                logger.info(
                    "Matched request %s → driver %s (score %.3f).",
                    request.request_id, best_driver.driver_id, -best_score,
                )
                
                # Update in-memory state
                best_driver.assign_ride(request)
                
                # Persist to database
                await self.queue_manager.update_request(
                    request_id=request.request_id,
                    status=RideStatus.ASSIGNED,
                    driver_id=best_driver.driver_id
                )
                
                matches.append((request.request_id, best_driver.driver_id))
            
            logger.info("Batch complete: %d matches made.", len(matches))
            return matches
        
        except Exception as e:
            logger.exception("match_rides: error during matching — %s", str(e))
            raise

    async def process_retries(self) -> int:
        try:
            ready = await self.queue_manager.get_rides_ready_for_retry()

            for ride in ready:
                await self.queue_manager.update_request(
                    request_id=ride.request_id,
                    status=RideStatus.PENDING,
                )
                logger.info(
                    "Re-queued request %s for retry %d/%d.",
                    ride.request_id,
                    ride.retry_count,
                    ride.max_retries,
                )

            if ready:
                logger.info("process_retries: re-queued %d rides.", len(ready))

            return len(ready)

        except Exception:
            logger.exception("process_retries: error during retry processing")
            raise