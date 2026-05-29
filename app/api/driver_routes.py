"""API routes for driver operations."""

from fastapi import APIRouter, Depends, HTTPException, status
from app.services.driver_service import DriverService
from app.schemas import DriverCreate, DriverUpdate, DriverResponse
from app.exceptions import DriverNotFound, RideMatchException
from app.dependencies import get_driver_service

router = APIRouter(prefix="/api/v1/drivers", tags=["drivers"])


@router.post("/", response_model=DriverResponse, status_code=status.HTTP_201_CREATED)
async def create_driver(
    driver_in: DriverCreate,
    service: DriverService = Depends(get_driver_service)
):
    """Create a new driver."""
    try:
        return await service.create_driver(driver_in)
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{driver_id}", response_model=DriverResponse)
async def get_driver(
    driver_id: str,
    service: DriverService = Depends(get_driver_service)
):
    """Get a driver by ID."""
    try:
        return await service.get_driver(driver_id)
    except DriverNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=list[DriverResponse])
async def list_drivers(
    skip: int = 0,
    limit: int = 100,
    service: DriverService = Depends(get_driver_service)
):
    """List all drivers with pagination."""
    try:
        return await service.get_all_drivers(skip, limit)
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/available/", response_model=list[DriverResponse])
async def get_available_drivers(
    service: DriverService = Depends(get_driver_service)
):
    """Get all available drivers."""
    try:
        return await service.get_available_drivers()
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{driver_id}", response_model=DriverResponse)
async def update_driver(
    driver_id: str,
    driver_in: DriverUpdate,
    service: DriverService = Depends(get_driver_service)
):
    """Update a driver."""
    try:
        return await service.update_driver(driver_id, driver_in)
    except DriverNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{driver_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_driver(
    driver_id: str,
    service: DriverService = Depends(get_driver_service)
):
    """Delete a driver."""
    try:
        await service.delete_driver(driver_id)
    except DriverNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/nearby/", response_model=list[DriverResponse])
async def get_nearby_drivers(
    lat: float,
    lng: float,
    radius_km: float = 10.0,
    service: DriverService = Depends(get_driver_service)
):
    """Get drivers near a location."""
    try:
        return await service.get_drivers_near_location(lat, lng, radius_km)
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
