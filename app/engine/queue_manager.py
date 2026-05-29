from typing import List, Optional, Tuple
from sqlalchemy import select, update, func
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import RideRequest, Driver
from app.models.enums import QueueSortStrategy, RideStatus, DriverStatus
import logging
from app.exceptions import RideRequestNotFound, InvalidStatusTransition


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VALID_TRANSITIONS: dict[RideStatus, set[RideStatus]] = {
    RideStatus.PENDING:   {RideStatus.QUEUED, RideStatus.ASSIGNED, RideStatus.FAILED},
    RideStatus.QUEUED:    {RideStatus.ASSIGNED, RideStatus.FAILED},
    RideStatus.ASSIGNED:  {RideStatus.PICKED_UP, RideStatus.FAILED},
    RideStatus.PICKED_UP: {RideStatus.COMPLETED, RideStatus.FAILED},
    RideStatus.COMPLETED: set(),   # terminal
    RideStatus.FAILED:    set(),   # terminal
    RideStatus.IN_PROGRESS: {RideStatus.COMPLETED, RideStatus.FAILED},
    RideStatus.RETRYING: {RideStatus.QUEUED, RideStatus.FAILED},
}
 
STALE_THRESHOLD_MINUTES = 30

class QueueManager:
    """Manages queues of ride requests and available drivers, ensuring efficient matching and processing.
    """
    def __init__(self, session: AsyncSession, strategy = QueueSortStrategy.HYBRID):
        self.session = session
        self.strategy = strategy

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
            if self.strategy == QueueSortStrategy.FIFO:
                order_clause = [RideRequest.created_at.asc()]
            elif self.strategy == QueueSortStrategy.PRIORITY:
                order_clause = [RideRequest.priority.desc()]
            else:  # HYBRID (default)
                order_clause = [
                    RideRequest.priority.desc(),
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
            stmt = (
                select(Driver)
                .where(Driver.status == DriverStatus.AVAILABLE)
                .order_by(Driver.rating.desc())
                .limit(limit)
            )
            result = await self.session.execute(stmt)
            drivers = list(result.scalars().all())
 
            logger.info(
                "get_available_drivers: fetched=%d (limit=%d)",
                len(drivers),
                limit,
            )
            return drivers
 
        except Exception:
            logger.exception("get_available_drivers: database error")
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
            values["assigned_at"] = datetime.now(timezone.utc)
 
        if not values:
            logger.warning("update_request: called with no values for id=%s", request_id)
            return
 
        try:
            # ---- verify request exists ----
            fetch_stmt = select(RideRequest).where(RideRequest.id == request_id)
            row = (await self.session.execute(fetch_stmt)).scalar_one_or_none()
 
            if row is None:
                raise RideRequestNotFound(
                    f"RideRequest id={request_id!r} not found"
                )
 
            # ---- validate state machine transition ----
            if status is not None:
                current_status: RideStatus = row.status
                allowed = VALID_TRANSITIONS.get(current_status, set())
                if status not in allowed:
                    raise InvalidStatusTransition(
                        f"Cannot transition request {request_id!r}: "
                        f"{current_status} → {status}  "
                        f"(allowed: {allowed or 'none — terminal state'})"
                    )
 
            # ---- apply update ----
            stmt = (
                update(RideRequest)
                .where(RideRequest.id == request_id)
                .values(**values)
            )
            await self.session.execute(stmt)
            await self.session.commit()
 
            if status is not None:
                logger.info(
                    "update_request: id=%s  %s → %s",
                    request_id,
                    row.status,
                    status,
                )
            if driver_id is not None:
                logger.info(
                    "update_request: id=%s assigned driver=%s",
                    request_id,
                    driver_id,
                )
 
        except (RideRequestNotFound, InvalidStatusTransition):
            raise  # re-raise domain exceptions without rollback
        except Exception:
            await self.session.rollback()
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
