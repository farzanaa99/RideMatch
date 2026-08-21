from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import driver_routes, ride_routes
from app.events import EventBus, EventHandlerRegistry, register_handlers
from app.metrics import MetricsCollector
from app.dependencies import set_event_bus
from app.database import init_db, close_db
import logging
logger = logging.getLogger(__name__)
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await event_bus.start()
    logger.info("Application startup complete")
    yield
    await event_bus.stop()
    await close_db()
    logger.info("Application shutdown complete")


app = FastAPI(
    title="RideMatch API",
    description="A ride-matching platform powered by advanced algorithms",
    version="0.1.0",
    lifespan=lifespan,
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
metrics_collector = MetricsCollector()
event_bus = EventBus(event_registry, metrics_collector=metrics_collector)

# Register all handlers
register_handlers(event_registry, metrics_collector=metrics_collector)

# Make event bus available to dependencies
set_event_bus(event_bus)

# Include routers
app.include_router(driver_routes.router)
app.include_router(ride_routes.router)


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
    metrics_collector.set_queue_depth(event_bus.queue_size())
    return {
        "metrics": event_bus.get_metrics(),
        "queue_size": event_bus.queue_size(),
        "is_running": event_bus.is_running,
    }


@app.get("/metrics")
async def get_advanced_metrics():
    """Get advanced operational metrics."""
    metrics_collector.set_queue_depth(event_bus.queue_size())
    return {
        "event_bus": event_bus.get_metrics(),
        "matching": metrics_collector.get_all_metrics(),
        "is_running": event_bus.is_running,
    }