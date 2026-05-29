import math
from dataclasses import dataclass
from app.models.enums import RideStatus, RidePriority
import heapq
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class MatchingConfig:
    """Configuration for ride-driver matching strategies.
    
    Attributes:
        name: Strategy identifier (e.g., "balanced", "speed_focused", "quality_focused")
        distance_weight: Weight for proximity to pickup (0.0-1.0)
        priority_weight: Weight for ride urgency (0.0-1.0)
        workload_weight: Weight for driver availability (0.0-1.0)
        dropoff_weight: Weight for dropoff location alignment (0.0-1.0)
        max_driver_distance: Maximum distance (km) driver can be from pickup
    
    Note: distance_weight + priority_weight + workload_weight + dropoff_weight should sum to 1.0
    """
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
    """
    Straight-line distance between two (lat, lng) pairs.
    WHY: The original used a flat Pythagorean formula which is fine for small
         areas but misbehaves over larger distances on a sphere.
         Haversine gives the actual great-circle distance in km.
    """
    R = 6371  # Earth radius in km
    lat1, lng1 = math.radians(loc1[0]), math.radians(loc1[1])
    lat2, lng2 = math.radians(loc2[0]), math.radians(loc2[1])
    dlat = lat2 - lat1
    dlng = lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))

class MatchingEngine:
    """Core matching algorithm with configurable scoring strategy."""

    def __init__(self, queue_manager, config: MatchingConfig = None):
        """Initialize matching engine with optional config.
        
        Args:
            queue_manager: Manager for pending requests and available drivers
            config: MatchingConfig instance. Defaults to BALANCED_CONFIG if not provided.
        
        Raises:
            ValueError: If config validation fails
        """
        self.queue_manager = queue_manager
        self.config = config or BALANCED_CONFIG
        self.config.validate()

    def calculate_score(self, driver, ride_request):
        """Calculate match score between driver and ride request.
        
        Score is weighted combination of:
        - Proximity: how close driver is to pickup (0-1, normalized)
        - Priority: how urgent the request is (0-1, normalized from enum)
        - Workload: how available the driver is (0-1, normalized)
        - Dropoff: how well dropoff aligns with driver position (0-1, normalized)
        
        Args:
            driver: Driver ORM model
            ride_request: RideRequest ORM model
        
        Returns:
            float: Final score (0.0-1.0, higher is better)
        """
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
            proximity       * self.config.distance_weight +
            priority_normalized * self.config.priority_weight +
            workload        * self.config.workload_weight +
            dropoff_align   * self.config.dropoff_weight
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
    
    def match_rides(self):
        ride_requests = self.queue_manager.get_pending_requests()
        available_drivers = self.queue_manager.get_available_drivers()

        if not isinstance(ride_requests, (list, tuple)):
            logger.error("get_pending_requests() did not return a list.")
            return []
        if not isinstance(available_drivers, (list, tuple)):
            logger.error("get_available_drivers() did not return a list.")
            return []
        
        matches = []

        try:
            ride_requests = sorted(ride_requests, key=lambda r: r.created_at)
        except AttributeError:
            logger.warning("Ride requests have no 'created_at'; skipping age sort.")
 

        for request in ride_requests:
            heap = []
            best_driver = None

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
            
            if not heap:
                logger.warning("No suitable driver found for request %s.", request.request_id)
                continue
                
            best_score, best_driver = heapq.heappop(heap)

            logger.info(
            "Matched request %s → driver %s (score %.3f).",
            request.request_id, best_driver.driver_id, -best_score,
            )
                
            best_driver.assign_ride(request)
            self.queue_manager.update_request(request)
            matches.append((request.request_id, best_driver.driver_id))
 
        logger.info("Batch complete: %d matches made.", len(matches))
        
        return matches
 
    

                     

