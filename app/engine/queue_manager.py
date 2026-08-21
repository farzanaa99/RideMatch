from typing import List, Optional, Tuple
from sqlalchemy import select, update, func, case
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import RideRequest, Driver
from app.models.enums import QueueSortStrategy, RideStatus, DriverStatus, RidePriority
import logging
from app.exceptions import RideRequestNotFound, InvalidStatusTransition
from app.engine.state_machine import RideStateMachine
from app.repositories.ride_request_repository import RideRequestRepository
from app.repositories.driver_repository import DriverRepository
from app.events import EventBus, DomainEvent, EventType


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STALE_THRESHOLD_MINUTES = 30
RETRY_BASE_DELAY_SECONDS = 5  # First retry after 5 seconds
RETRY_MAX_DELAY_SECONDS = 300  # Cap at 5 minutes

class QueueManager:
    """Manages queues of ride requests and available drivers, ensuring efficient matching and processing.
    
    Uses repositories for entity operations and session for complex queries (pagination, aggregation, bulk ops).
    Publishes events for state transitions via EventBus.
    """
    def __init__(
        self,
        session: AsyncSession,
        ride_repo: RideRequestRepository,
        driver_repo: DriverRepository,
        strategy: QueueSortStrategy = QueueSortStrategy.HYBRID,
        state_machine: RideStateMachine | None = None,
        event_bus: EventBus | None = None,
    ):
        self.session = session
        self.ride_repo = ride_repo
        self.driver_repo = driver_repo
        self.strategy = strategy
        self.state_machine = state_machine or RideStateMachine()
        self.event_bus = event_bus

    @staticmethod
    def _calculate_retry_delay(retry_count: int) -> timedelta:
        """Calculate exponential backoff delay.
        
        Formula: base_delay * (2 ^ retry_count), capped at max_delay.
        Example:
            retry 0: 5s
            retry 1: 10s
            retry 2: 20s
            retry 3+: 300s (5 min cap)
        """
        delay_seconds = min(
            RETRY_BASE_DELAY_SECONDS * (2 ** retry_count),
            RETRY_MAX_DELAY_SECONDS
        )
        return timedelta(seconds=delay_seconds)

    async def get_pending_requests(
        self,
        limit: int = 100,
        offset: int = 0,
        exclude_stale: bool = False,
    ) -> Tuple[List[RideRequest], int]:
        """Return a paginated list of PENDING requests and the total count.
 
        Args:
            limit:         Maximum rows to return (pagination).
            offset:        Number of rows to skip (pagination).
            exclude_stale: When True, requests older than STALE_THRESHOLD_MINUTES
                           are excluded from results.
 
        Returns:
            A tuple of (requests, total_count).
 
        Raises:
            ValueError: If limit or offset are negative.
        """
        if limit < 0:
            raise ValueError(f"limit must be non-negative, got {limit}")
        if offset < 0:
            raise ValueError(f"offset must be non-negative, got {offset}")
 
        try:
            base_filter = RideRequest.status == RideStatus.PENDING
 
            if exclude_stale:
                stale_cutoff = datetime.now(timezone.utc) - timedelta(
                    minutes=STALE_THRESHOLD_MINUTES
                )
                base_filter = base_filter & (RideRequest.created_at >= stale_cutoff)
 
            # ---- apply sorting strategy ----
            priority_rank = case(
                (RideRequest.priority == RidePriority.HIGH, 3),
                (RideRequest.priority == RidePriority.NORMAL, 2),
                (RideRequest.priority == RidePriority.LOW, 1),
                else_=0,
            )

            if self.strategy == QueueSortStrategy.FIFO:
                order_clause = [RideRequest.created_at.asc()]
            elif self.strategy == QueueSortStrategy.PRIORITY:
                order_clause = [priority_rank.desc(), RideRequest.created_at.asc()]
            else:  # HYBRID (default)
                order_clause = [
                    priority_rank.desc(),
                    RideRequest.created_at.asc(),
                ]
 
            # ---- total count (for pagination UI) ----
            count_stmt = select(func.count()).select_from(RideRequest).where(base_filter)
            total_count: int = (await self.session.execute(count_stmt)).scalar_one()
 
            # ---- paginated data ----
            data_stmt = (
                select(RideRequest)
                .where(base_filter)
                .order_by(*order_clause)
                .limit(limit)
                .offset(offset)
            )
            result = await self.session.execute(data_stmt)
            requests = list(result.scalars().all())
 
            logger.info(
                "get_pending_requests: strategy=%s exclude_stale=%s "
                "fetched=%d total=%d limit=%d offset=%d",
                self.strategy,
                exclude_stale,
                len(requests),
                total_count,
                limit,
                offset,
            )
            return requests, total_count
 
        except Exception:
            logger.exception("get_pending_requests: database error")
            raise
    
    async def get_available_drivers(self, limit: int = 100) -> List[Driver]:
        """Return available drivers ordered by rating (highest first).
 
        Args:
            limit: Maximum number of drivers to return.
 
        Raises:
            ValueError: If limit is negative.
        """
        if limit < 0:
            raise ValueError(f"limit must be non-negative, got {limit}")
 
        try:
            # Use repository for simple entity query
            drivers = await self.driver_repo.get_available_drivers_for_update()   # CHANGED
            drivers = drivers[:limit]

            logger.info(
                "get_available_drivers: fetched=%d (limit=%d)",
                len(drivers),
                limit,
            )
            return drivers
 
        except Exception:
            logger.exception("get_available_drivers: database error")
            raise
    
    async def get_rides_ready_for_retry(self, limit: int = 100) -> List[RideRequest]:
        """Get RETRYING rides whose exponential backoff delay has elapsed.
        
        Args:
            limit: Maximum number of rides to return.
        
        Returns:
            List of rides ready to be re-queued.
        """
        if limit < 0:
            raise ValueError(f"limit must be non-negative, got {limit}")
        
        try:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            stmt = (
                select(RideRequest)
                .where(RideRequest.status == RideStatus.RETRYING)
                .order_by(RideRequest.failed_at.asc().nullsfirst())
                .limit(limit * 3)
            )
            result = await self.session.execute(stmt)
            candidates = list(result.scalars().all())

            rides: List[RideRequest] = []
            for ride in candidates:
                # If missing failed_at, treat as ready to avoid dead-lettering rows.
                if ride.failed_at is None:
                    rides.append(ride)
                    if len(rides) >= limit:
                        break
                    continue

                failed_at = ride.failed_at
                if failed_at.tzinfo is not None:
                    failed_at = failed_at.replace(tzinfo=None)

                retry_delay = self._calculate_retry_delay(ride.retry_count)
                retry_ready_at = failed_at + retry_delay
                if retry_ready_at <= now:
                    rides.append(ride)
                    if len(rides) >= limit:
                        break
            
            logger.info(
                "get_rides_ready_for_retry: found=%d ready to retry",
                len(rides),
            )
            return rides
        
        except Exception:
            logger.exception("get_rides_ready_for_retry: database error")
            raise
    
    async def update_request(
        self,
        request_id: str,
        status: Optional[RideStatus] = None,
        driver_id: Optional[str] = None,
    ) -> None:
        """Update status and/or assigned driver for a ride request.
 
        Args:
            request_id: ID of the RideRequest to update.
            status:     New status (validated against the state machine).
            driver_id:  Driver to assign; sets assigned_driver_id + assigned_at.
 
        Raises:
            RideRequestNotFound:    If no request with request_id exists.
            InvalidStatusTransition: If the status transition is not allowed.
        """
        values: dict = {}
 
        if status is not None:
            values["status"] = status
        if driver_id is not None:
            values["assigned_driver_id"] = driver_id
            values["assigned_at"] = datetime.now(timezone.utc).replace(tzinfo=None)

 
        if not values:
            logger.warning("update_request: called with no values for id=%s", request_id)
            return
 
        try:
            # ---- verify request exists using repository ----
            row = await self.ride_repo.get_by_id(request_id)
            if row is None:
                raise RideRequestNotFound(
                    f"RideRequest id={request_id!r} not found"
                )
 
            # ---- validate state machine transition ----
            if status is not None:
                current_status: RideStatus = row.status
                self.state_machine.validate_transition(
                    current=current_status,
                    next=status,
                    actor="queue_manager"
                )

                if status == RideStatus.RETRYING:
                    now = datetime.now(timezone.utc).replace(tzinfo=None)
                    row.retry_count += 1
                    row.assigned_driver_id = None
                    row.assigned_at = None
                    row.failed_at = now
 
            # ---- apply update using repository ----
            # For status + driver_id updates, update the in-memory object and flush
            for key, value in values.items():
                setattr(row, key, value)
            await self.ride_repo.commit()
 
            # ---- emit events ----
            if status is not None:
                logger.info(
                    "update_request: id=%s  %s → %s",
                    request_id,
                    row.status,
                    status,
                )
                # Emit status-specific events
                if self.event_bus:
                    event_type_map = {
                        RideStatus.QUEUED: EventType.RIDE_QUEUED,
                        RideStatus.ASSIGNED: EventType.RIDE_ASSIGNED,
                        RideStatus.EN_ROUTE: EventType.RIDE_PICKED_UP,
                        RideStatus.IN_PROGRESS: EventType.RIDE_IN_PROGRESS,
                        RideStatus.COMPLETED: EventType.RIDE_COMPLETED,
                        RideStatus.FAILED: EventType.RIDE_FAILED,
                        RideStatus.RETRYING: EventType.RIDE_RETRYING,
                    }
                    if status in event_type_map:
                        event_data = {"request_id": request_id}
                        
                        # Add context-specific data
                        if status == RideStatus.ASSIGNED and driver_id:
                            event_data["driver_id"] = driver_id
                            if row.assigned_at and row.created_at:
                                assigned_at = row.assigned_at
                                created_at = row.created_at

                                if assigned_at.tzinfo is not None:
                                    assigned_at = assigned_at.replace(tzinfo=None)

                                if created_at.tzinfo is not None:
                                    created_at = created_at.replace(tzinfo=None)

                                latency_ms = (assigned_at - created_at).total_seconds() * 1000
                                event_data["latency_ms"] = latency_ms
                        elif status == RideStatus.FAILED:
                            if row.assigned_driver_id:
                                event_data["driver_id"] = row.assigned_driver_id
                            event_data["retry_count"] = row.retry_count
                            event_data["max_retries"] = row.max_retries
                        elif status == RideStatus.RETRYING:
                            retry_delay = self._calculate_retry_delay(row.retry_count)
                            event_data["retry_count"] = row.retry_count
                            event_data["retry_backoff_seconds"] = int(retry_delay.total_seconds())
                            event_data["next_retry_at"] = (
                                row.failed_at + retry_delay
                            ).isoformat() if row.failed_at else None
                        elif status == RideStatus.COMPLETED and row.assigned_driver_id:
                            event_data["driver_id"] = row.assigned_driver_id
                        
                        await self.event_bus.publish(DomainEvent(
                            event_type=event_type_map[status],
                            data=event_data
                        ))
 
            if driver_id is not None:
                logger.info(
                    "update_request: id=%s assigned driver=%s",
                    request_id,
                    driver_id,
                )
 
        except (RideRequestNotFound, InvalidStatusTransition):
            raise  # re-raise domain exceptions without rollback
        except Exception:
            await self.ride_repo.rollback()
            logger.exception("update_request: database error for id=%s — rolled back", request_id)
            raise
 
    # ------------------------------------------------------------------
    # mark_stale_requests_as_failed  (NEW)
    # ------------------------------------------------------------------
    async def mark_stale_requests_as_failed(self) -> int:
        """Auto-expire PENDING requests older than STALE_THRESHOLD_MINUTES.
 
        Returns:
            Number of requests that were marked FAILED.
        """
        stale_cutoff = datetime.now(timezone.utc) - timedelta(
            minutes=STALE_THRESHOLD_MINUTES
        )
 
        try:
            stmt = (
                update(RideRequest)
                .where(
                    RideRequest.status == RideStatus.PENDING,
                    RideRequest.created_at < stale_cutoff,
                )
                .values(status=RideStatus.FAILED)
                .execution_options(synchronize_session="fetch")
            )
            result = await self.session.execute(stmt)
            await self.session.commit()
 
            affected: int = result.rowcount
            logger.info(
                "mark_stale_requests_as_failed: marked %d requests as FAILED "
                "(threshold=%d min, cutoff=%s)",
                affected,
                STALE_THRESHOLD_MINUTES,
                stale_cutoff.isoformat(),
            )
            return affected
 
        except Exception:
            await self.session.rollback()
            logger.exception("mark_stale_requests_as_failed: database error — rolled back")
            raise
 
    # ------------------------------------------------------------------
    # get_queue_stats  (NEW)
    # ------------------------------------------------------------------
    async def get_queue_stats(self) -> dict:
        """Return monitoring metrics for the pending queue.
 
        Returns:
            A dict with keys:
                pending_count   – total PENDING requests
                oldest_request  – datetime of the oldest PENDING request (or None)
                oldest_age_min  – age of that request in minutes (or None)
        """
        try:
            stats_stmt = select(
                func.count().label("pending_count"),
                func.min(RideRequest.created_at).label("oldest_created_at"),
            ).where(RideRequest.status == RideStatus.PENDING)
 
            row = (await self.session.execute(stats_stmt)).one()
 
            pending_count: int = row.pending_count
            oldest_created_at: Optional[datetime] = row.oldest_created_at
 
            oldest_age_min: Optional[float] = None
            if oldest_created_at is not None:
                # Ensure tz-aware arithmetic
                if oldest_created_at.tzinfo is None:
                    oldest_created_at = oldest_created_at.replace(tzinfo=timezone.utc)
                oldest_age_min = round(
                    (datetime.now(timezone.utc) - oldest_created_at).total_seconds() / 60,
                    2,
                )
 
            stats = {
                "pending_count": pending_count,
                "oldest_request": oldest_created_at,
                "oldest_age_min": oldest_age_min,
            }
 
            logger.info(
                "get_queue_stats: pending=%d oldest_age_min=%s",
                pending_count,
                oldest_age_min,
            )
            return stats
 
        except Exception:
            logger.exception("get_queue_stats: database error")
            raise
