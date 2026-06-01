from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import driver_routes, ride_routes
from app.events import EventBus, EventHandlerRegistry, register_handlers
from app.dependencies import set_event_bus
import logging

logger = logging.getLogger(__name__)

app = FastAPI(
    title="RideMatch API",
    description="A ride-matching platform powered by advanced algorithms",
    version="0.1.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize event bus
event_registry = EventHandlerRegistry()
event_bus = EventBus(event_registry)

# Register all handlers
register_handlers(event_registry)

# Make event bus available to dependencies
set_event_bus(event_bus)

# Include routers
app.include_router(driver_routes.router)
app.include_router(ride_routes.router)


@app.on_event("startup")
async def startup_event():
    """Start event bus on application startup."""
    await event_bus.start()
    logger.info("Application startup complete")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop event bus on application shutdown."""
    await event_bus.stop()
    logger.info("Application shutdown complete")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "RideMatch API is Running!",
        "version": "0.1.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/api/v1/events/metrics")
async def get_event_metrics():
    """Get event bus metrics."""
    return {
        "metrics": event_bus.get_metrics(),
        "queue_size": event_bus.queue_size(),
        "is_running": event_bus.is_running,
    }