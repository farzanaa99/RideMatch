"""Service layer for driver operations."""

from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.driver import Driver
from app.models.enums import DriverStatus
from app.repositories.driver_repository import DriverRepository
from app.exceptions import DriverNotFound, DriverNotAvailable
from app.schemas import DriverCreate, DriverUpdate, DriverResponse


class DriverService:
    """Service for driver business logic."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = DriverRepository(session)

    async def create_driver(self, driver_in: DriverCreate) -> DriverResponse:
        """Create a new driver."""
        driver_data = driver_in.model_dump()
        driver = await self.repo.create(driver_data)
        await self.repo.commit()
        return DriverResponse.from_orm(driver)

    async def get_driver(self, driver_id: str) -> DriverResponse:
        """Get a driver by ID."""
        driver = await self.repo.get_by_id(driver_id)
        if not driver:
            raise DriverNotFound(f"Driver {driver_id} not found")
        return DriverResponse.from_orm(driver)

    async def get_all_drivers(self, skip: int = 0, limit: int = 100) -> List[DriverResponse]:
        """Get all drivers."""
        drivers = await self.repo.get_all(skip, limit)
        return [DriverResponse.from_orm(d) for d in drivers]

    async def get_available_drivers(self) -> List[DriverResponse]:
        """Get all available drivers."""
        drivers = await self.repo.get_available_drivers()
        return [DriverResponse.from_orm(d) for d in drivers]

    async def update_driver(self, driver_id: str, driver_in: DriverUpdate) -> DriverResponse:
        """Update a driver."""
        driver = await self.repo.get_by_id(driver_id)
        if not driver:
            raise DriverNotFound(f"Driver {driver_id} not found")
        
        driver_data = driver_in.model_dump(exclude_unset=True)
        updated_driver = await self.repo.update(driver_id, driver_data)
        await self.repo.commit()
        return DriverResponse.from_orm(updated_driver)

    async def delete_driver(self, driver_id: str) -> bool:
        """Delete a driver."""
        driver = await self.repo.get_by_id(driver_id)
        if not driver:
            raise DriverNotFound(f"Driver {driver_id} not found")
        
        success = await self.repo.delete(driver_id)
        await self.repo.commit()
        return success

    async def set_driver_status(self, driver_id: str, status: DriverStatus) -> DriverResponse:
        """Update driver status."""
        driver = await self.repo.get_by_id(driver_id)
        if not driver:
            raise DriverNotFound(f"Driver {driver_id} not found")
        
        driver.status = status
        await self.repo.commit()
        return DriverResponse.from_orm(driver)

    async def get_drivers_near_location(
        self,
        lat: float,
        lng: float,
        radius_km: float = 10.0
    ) -> List[DriverResponse]:
        """Get drivers near a location."""
        drivers = await self.repo.get_drivers_near_location(lat, lng, radius_km)
        return [DriverResponse.from_orm(d) for d in drivers]

    async def get_high_rated_drivers(self, min_rating: float = 4.5) -> List[DriverResponse]:
        """Get high-rated drivers."""
        drivers = await self.repo.get_high_rated_drivers(min_rating)
        return [DriverResponse.from_orm(d) for d in drivers]
