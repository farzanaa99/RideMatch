import time
from app.models.enums import RideStatus

class RideRequest:

    def __init__(self, request_id, rider_id, pickup_lat, pickup_lng, dropoff_lat, dropoff_lng, priority=1):
        self.request_id = request_id
        self.rider_id = rider_id
        self.pickup_lat = pickup_lat
        self.pickup_lng = pickup_lng
        self.dropoff_lat = dropoff_lat
        self.dropoff_lng = dropoff_lng
        self.priority = priority
        self.status = RideStatus.PENDING
        self.created_at = time.time()
        self.assigned_driver_id = None
        self.assigned_at = None
        self.started_at = None
        self.completed_at = None