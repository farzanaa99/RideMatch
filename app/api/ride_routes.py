"""API routes for ride request operations."""

from fastapi import APIRouter, Depends, HTTPException, status
from app.services.ride_service import RideRequestService
from app.schemas import RideRequestCreate, RideRequestUpdate, RideRequestResponse
from app.exceptions import RideRequestNotFound, RideMatchException
from app.dependencies import get_ride_service

router = APIRouter(prefix="/api/v1/rides", tags=["rides"])


@router.post("/", response_model=RideRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_ride_request(
    request_in: RideRequestCreate,
    service: RideRequestService = Depends(get_ride_service)
):
    """Create a new ride request."""
    try:
        return await service.create_ride_request(request_in)
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{request_id}", response_model=RideRequestResponse)
async def get_ride_request(
    request_id: str,
    service: RideRequestService = Depends(get_ride_service)
):
    """Get a ride request by ID."""
    try:
        return await service.get_ride_request(request_id)
    except RideRequestNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/", response_model=list[RideRequestResponse])
async def list_ride_requests(
    skip: int = 0,
    limit: int = 100,
    service: RideRequestService = Depends(get_ride_service)
):
    """List all ride requests with pagination."""
    try:
        return await service.get_all_requests(skip, limit)
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/pending/", response_model=list[RideRequestResponse])
async def get_pending_requests(
    service: RideRequestService = Depends(get_ride_service)
):
    """Get all pending ride requests."""
    try:
        return await service.get_pending_requests()
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/rider/{rider_id}", response_model=list[RideRequestResponse])
async def get_rider_requests(
    rider_id: str,
    service: RideRequestService = Depends(get_ride_service)
):
    """Get all requests for a specific rider."""
    try:
        return await service.get_requests_by_rider(rider_id)
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/driver/{driver_id}", response_model=list[RideRequestResponse])
async def get_driver_requests(
    driver_id: str,
    service: RideRequestService = Depends(get_ride_service)
):
    """Get all requests assigned to a driver."""
    try:
        return await service.get_requests_by_driver(driver_id)
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{request_id}", response_model=RideRequestResponse)
async def update_ride_request(
    request_id: str,
    request_in: RideRequestUpdate,
    service: RideRequestService = Depends(get_ride_service)
):
    """Update a ride request."""
    try:
        return await service.update_ride_request(request_id, request_in)
    except RideRequestNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{request_id}/assign/{driver_id}", response_model=RideRequestResponse)
async def assign_ride(
    request_id: str,
    driver_id: str,
    service: RideRequestService = Depends(get_ride_service)
):
    """Assign a ride to a driver."""
    try:
        return await service.assign_ride(request_id, driver_id)
    except RideRequestNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{request_id}/pickup", response_model=RideRequestResponse)
async def mark_pickup(
    request_id: str,
    service: RideRequestService = Depends(get_ride_service)
):
    """Mark a ride as picked up."""
    try:
        return await service.mark_picked_up(request_id)
    except RideRequestNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{request_id}/complete", response_model=RideRequestResponse)
async def mark_complete(
    request_id: str,
    service: RideRequestService = Depends(get_ride_service)
):
    """Mark a ride as completed."""
    try:
        return await service.mark_completed(request_id)
    except RideRequestNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{request_id}/fail", response_model=RideRequestResponse)
async def mark_fail(
    request_id: str,
    service: RideRequestService = Depends(get_ride_service)
):
    """Mark a ride as failed."""
    try:
        return await service.mark_failed(request_id)
    except RideRequestNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{request_id}/retry", response_model=RideRequestResponse)
async def retry_ride(
    request_id: str,
    service: RideRequestService = Depends(get_ride_service)
):
    """Retry a failed ride request."""
    try:
        return await service.retry_request(request_id)
    except RideRequestNotFound as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except RideMatchException as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
