"""Metrics collector for ride matching system."""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List

logger = logging.getLogger(__name__)


@dataclass
class DriverMetrics:
    """Per-driver metrics."""
    driver_id: str
    active_rides: int = 0
    completed_rides: int = 0
    failed_rides: int = 0
    total_assignments: int = 0


class MetricsCollector:
    """Collects and aggregates system metrics."""

    def __init__(self):
        self.assignment_latencies: List[float] = []  # Latencies in ms
        self.total_rides: int = 0
        self.total_assignments: int = 0
        self.failed_rides: int = 0
        self.completed_rides: int = 0
        self.queue_depth: int = 0
        self.driver_metrics: Dict[str, DriverMetrics] = {}

    def record_assignment(self, driver_id: str, latency_ms: float) -> None:
        """Record a successful assignment with latency."""
        self.assignment_latencies.append(latency_ms)
        self.total_rides += 1
        self.total_assignments += 1

        if driver_id not in self.driver_metrics:
            self.driver_metrics[driver_id] = DriverMetrics(driver_id=driver_id)

        self.driver_metrics[driver_id].active_rides += 1
        self.driver_metrics[driver_id].total_assignments += 1
        logger.debug("Recorded assignment: %s latency=%sms", driver_id, latency_ms)

    def record_completion(self, driver_id: str) -> None:
        """Record a ride completion."""
        self.completed_rides += 1

        if driver_id in self.driver_metrics:
            self.driver_metrics[driver_id].active_rides = max(
                0,
                self.driver_metrics[driver_id].active_rides - 1,
            )
            self.driver_metrics[driver_id].completed_rides += 1
        logger.debug("Recorded completion: %s", driver_id)

    def record_failure(self, driver_id: str = None) -> None:
        """Record a ride failure."""
        self.failed_rides += 1
        
        if driver_id and driver_id in self.driver_metrics:
            self.driver_metrics[driver_id].failed_rides += 1
        logger.debug(f"Recorded failure: {driver_id}")

    def get_average_latency(self) -> float:
        """Get average assignment latency in ms."""
        if not self.assignment_latencies:
            return 0.0
        return sum(self.assignment_latencies) / len(self.assignment_latencies)

    def get_failure_rate(self) -> float:
        """Get failure rate as percentage."""
        if self.total_rides == 0:
            return 0.0
        return (self.failed_rides / self.total_rides) * 100

    def get_driver_utilization(self, driver_id: str) -> Dict:
        """Get utilization stats for a specific driver."""
        if driver_id not in self.driver_metrics:
            return {
                "driver_id": driver_id,
                "active_rides": 0,
                "completed_rides": 0,
                "failed_rides": 0,
                "total_assignments": 0,
            }
        
        metrics = self.driver_metrics[driver_id]
        return {
            "driver_id": driver_id,
            "active_rides": metrics.active_rides,
            "completed_rides": metrics.completed_rides,
            "failed_rides": metrics.failed_rides,
            "total_assignments": metrics.total_assignments,
        }

    def get_all_metrics(self) -> Dict:
        """Get comprehensive metrics."""
        driver_utilization = [
            self.get_driver_utilization(driver_id)
            for driver_id in self.driver_metrics.keys()
        ]
        
        return {
            "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
            "total_rides": self.total_rides,
            "total_assignments": self.total_assignments,
            "completed_rides": self.completed_rides,
            "failed_rides": self.failed_rides,
            "queue_depth": self.queue_depth,
            "average_assignment_latency_ms": self.get_average_latency(),
            "failure_rate_percent": self.get_failure_rate(),
            "assignment_samples": len(self.assignment_latencies),
            "driver_utilization": driver_utilization,
        }

    def set_queue_depth(self, depth: int) -> None:
        """Set current queue depth value."""
        self.queue_depth = max(0, depth)

    def reset(self) -> None:
        """Reset all metrics."""
        self.assignment_latencies.clear()
        self.total_rides = 0
        self.total_assignments = 0
        self.failed_rides = 0
        self.completed_rides = 0
        self.queue_depth = 0
        self.driver_metrics.clear()
        logger.info("Metrics reset")
