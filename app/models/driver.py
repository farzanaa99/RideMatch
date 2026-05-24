import time

from app.models.enums import RideStatus

class Driver:

    def __init__(self, driver_id, current_location, max_capacity=1):
        self.driver_id = driver_id
        self.current_location = current_location
        self.max_capacity = max_capacity

        self.current_rides = {}

    def can_accept_ride(self):
        return len(self.current_rides) < self.max_capacity
        
    def assign_ride(self, ride_request):
        if not self.is_available():
            return False

        if ride_request.request_id in self.current_rides:
            return False
                
        self.current_rides[ride_request.request_id] = ride_request
        ride_request.assigned_driver_id = self.driver_id
        ride_request.status = RideStatus.ASSIGNED
        ride_request.assigned_at = time.time()
        return True

        
    def complete_ride(self, request_id):
        if request_id in self.current_rides:
            ride = self.current_rides[request_id]
            ride.status = RideStatus.COMPLETED
            del self.current_rides[request_id]
            return True
        return False
    