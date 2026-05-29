from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import driver_routes, ride_routes

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