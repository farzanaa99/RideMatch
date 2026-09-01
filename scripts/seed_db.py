"""Seed script to populate the database with initial driver and test data."""

import asyncio
import random
import sys
from pathlib import Path

# Add parent directory to path so we can import app module
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.database import AsyncSessionLocal, init_db
from app.models.driver import Driver
from app.models.enums import RidePriority
from app.models.ride_request import RideRequest

# Sample driver names
DRIVER_NAMES = [
    "John Smith", "Maria Garcia", "Ahmed Hassan", "Lisa Chen", "Carlos Rodriguez",
    "Fatima Al-Rashid", "James Wilson", "Priya Patel", "Michael O'Connor", "Sofia Rossi",
    "David Kim", "Amira Mohamed", "Robert Thompson", "Yuki Tanaka", "Paul Mueller",
    "Elena Volkov", "Marcus Johnson", "Jasmine Patel", "Francisco Morales", "Nina Bergman",
    "Kevin Zhang", "Leila Amin", "Daniel Costa", "Isabelle Dubois", "Hassan Ibrahim",
]

# Sample cities/areas with coordinates
AREAS = [
    {"name": "Downtown", "lat": 40.7128, "lng": -74.0060},
    {"name": "Uptown", "lat": 40.7282, "lng": -73.9942},
    {"name": "Midtown", "lat": 40.7505, "lng": -73.9972},
    {"name": "Brooklyn", "lat": 40.6782, "lng": -73.9442},
    {"name": "Queens", "lat": 40.7282, "lng": -73.7949},
    {"name": "Financial District", "lat": 40.7074, "lng": -74.0113},
    {"name": "Greenwich Village", "lat": 40.7350, "lng": -74.0029},
    {"name": "Upper East Side", "lat": 40.7764, "lng": -73.9597},
    {"name": "Upper West Side", "lat": 40.7829, "lng": -73.9654},
]


async def seed_drivers():
    """Populate the database with 25 drivers."""
    async with AsyncSessionLocal() as session:
        # Check if drivers already exist
        result = await session.execute(select(Driver))
        existing_drivers = result.scalars().all()
        
        if len(existing_drivers) > 0:
            print(f"{len(existing_drivers)} drivers already exist. Skipping driver seeding.")
            return

        drivers = []
        for i, name in enumerate(DRIVER_NAMES, 1):
            area = random.choice(AREAS)
            
            # Add some random offset to the coordinates
            lat = area["lat"] + random.uniform(-0.05, 0.05)
            lng = area["lng"] + random.uniform(-0.05, 0.05)
            
            driver = Driver(
                driver_name=name,
                rating=round(random.uniform(4.0, 5.0), 1),
                lat=lat,
                lng=lng,
                max_capacity=random.choice([1, 2, 3])
            )
            drivers.append(driver)
            print(f"  Created driver {i}: {name} (Rating: {driver.rating}, Area: {area['name']})")

        session.add_all(drivers)
        await session.commit()
        print(f"Successfully seeded {len(drivers)} drivers!")


async def seed_test_ride_requests():
    """Create a few test ride requests for testing."""
    async with AsyncSessionLocal() as session:
        # Check if requests already exist
        result = await session.execute(select(RideRequest))
        existing_requests = result.scalars().all()
        
        if len(existing_requests) > 0:
            print(f"{len(existing_requests)} ride requests already exist. Skipping request seeding.")
            return

        requests = []
        
        # Create 5 test requests
        for i in range(5):
            area1 = random.choice(AREAS)
            area2 = random.choice(AREAS)
            
            request = RideRequest(
                rider_id=f"rider_{i+1}",
                pickup_lat=area1["lat"] + random.uniform(-0.02, 0.02),
                pickup_lng=area1["lng"] + random.uniform(-0.02, 0.02),
                dropoff_lat=area2["lat"] + random.uniform(-0.02, 0.02),
                dropoff_lng=area2["lng"] + random.uniform(-0.02, 0.02),
                pickup_address=f"{area1['name']}, New York",
                dropoff_address=f"{area2['name']}, New York",
                priority=random.choice(list(RidePriority)),
            )
            requests.append(request)
            print(f"  Created ride request {i+1}: {area1['name']} → {area2['name']}")

        session.add_all(requests)
        await session.commit()
        print(f"Successfully created {len(requests)} test ride requests!")


async def main():
    """Main seeding function."""
    print("Starting database seeding...\n")
    
    # Initialize database tables
    await init_db()
    print("Database tables initialized.\n")
    
    # Seed drivers
    print("Seeding drivers...")
    await seed_drivers()
    
    print("\nSeeding test ride requests...")
    await seed_test_ride_requests()
    
    print("\nDatabase seeding complete!")


if __name__ == "__main__":
    asyncio.run(main())
