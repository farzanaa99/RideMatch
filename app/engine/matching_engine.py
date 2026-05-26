import math
from app.models.enums import RideStatus
import heapq
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


MAX_DRIVER_DISTANCE = 50.0
WEIGHT_PROXIMITY = 0.4   # How close the driver is to the pickup point
WEIGHT_PRIORITY  = 0.3   # How urgent the ride request is
WEIGHT_WORKLOAD  = 0.2   # How free the driver currently is
WEIGHT_DROPOFF   = 0.1   # How well the dropoff suits the driver's position

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
    def __init__ (self, queue_manager):
        self.queue_manager = queue_manager

    def calculate_score(self, driver, ride_request):
        pickup_dist = haversine_distance(
            driver.current_location,
            (ride_request.pickup_lat, ride_request.pickup_lng)
        )
        proximity = 1 / (1 + pickup_dist)
        priority = ride_request.priority
        workload = 1 / (1 + len(driver.current_rides))
        dropoff_dist = haversine_distance(
            driver.current_location,
            (ride_request.dropoff_lat, ride_request.dropoff_lng)
        )
        dropoff_align = 1 / (1 + dropoff_dist)
 
        score = (
            proximity     * WEIGHT_PROXIMITY +
            priority      * WEIGHT_PRIORITY  +
            workload      * WEIGHT_WORKLOAD  +
            dropoff_align * WEIGHT_DROPOFF
        )

        logger.debug(
            "Score for driver %s on request %s: %.3f "
            "(proximity=%.3f, priority=%.3f, workload=%.3f, dropoff=%.3f)",
            driver.driver_id, ride_request.request_id,
            score, proximity, priority, workload, dropoff_align,
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
        
        driver_pool = set(available_drivers)
        matches = []

        try:
            ride_requests = sorted(ride_requests, key=lambda r: r.created_at)
        except AttributeError:
            logger.warning("Ride requests have no 'created_at'; skipping age sort.")
 

        for request in ride_requests:
            heap = []
            best_driver = None

            for driver in available_drivers:
                if not driver.can_accept_ride():
                    continue

                pickup_dist = haversine_distance(
                    driver.current_location,
                    (request.pickup_lat, request.pickup_lng)
                )
 
                if pickup_dist > MAX_DRIVER_DISTANCE:
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
            if not best_driver.can_accept_ride():
                driver_pool.discard(best_driver)
                logger.debug("Driver %s is now full; removed from pool.", best_driver.driver_id)
 
            matches.append((request.request_id, best_driver.driver_id))
 
        logger.info("Batch complete: %d matches made.", len(matches))
        
        return matches
 
    

                     

