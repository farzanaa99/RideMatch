"""Repository for Driver model."""

from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.driver import Driver
from app.models.enums import DriverStatus
from app.repositories.base import BaseRepository


class DriverRepository(BaseRepository[Driver]):

    def __init__(self, session: AsyncSession):
        super().__init__(session, Driver)

    async def get_available_drivers(self) -> List[Driver]:
        result = await self.session.execute(
            select(Driver).where(Driver.status == DriverStatus.AVAILABLE)
        )
        return result.scalars().all()

    async def get_drivers_by_status(self, status: DriverStatus) -> List[Driver]:
        result = await self.session.execute(
            select(Driver).where(Driver.status == status)
        )
        return result.scalars().all()

    async def get_high_rated_drivers(self, min_rating: float = 4.5) -> List[Driver]:
        result = await self.session.execute(
            select(Driver).where(Driver.rating >= min_rating)
        )
        return result.scalars().all()

    async def get_drivers_near_location(
        self, 
        lat: float, 
        lng: float, 
        radius_km: float = 10.0
    ) -> List[Driver]:

        # Simple bounding box (not perfect but sufficient for MVP)
        # 1 degree ≈ 111 km
        lat_offset = radius_km / 111.0
        lng_offset = radius_km / 111.0
        
        result = await self.session.execute(
            select(Driver).where(
                (Driver.lat >= lat - lat_offset) &
                (Driver.lat <= lat + lat_offset) &
                (Driver.lng >= lng - lng_offset) &
                (Driver.lng <= lng + lng_offset)
            )
        )
        return result.scalars().all()
