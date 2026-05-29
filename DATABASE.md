# Database Setup Guide

This document describes the database configuration and migration setup for the RideMatch application.

## Configuration

### Environment Variables

Create a `.env` file in the project root with the following variables:

```
# For SQLite (development, default)
DATABASE_URL=sqlite+aiosqlite:///./ridematch.db

# For PostgreSQL (production)
# DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/ridematch

# SQL logging (optional)
SQL_ECHO=False
```

A template file `.env.example` is provided in the repository.

## Database Setup

### Initial Setup

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run migrations:**
   ```bash
   alembic upgrade head
   ```

3. **Seed the database with initial data:**
   ```bash
   python scripts/seed_db.py
   ```

## Database Schema

The application uses two main tables:

### Drivers Table
- `id` (UUID, Primary Key)
- `driver_name` (String)
- `rating` (Float)
- `lat` (Float) - Latitude
- `lng` (Float) - Longitude
- `max_capacity` (Integer)
- `status` (Enum: AVAILABLE, EN_ROUTE, ON_RIDE)
- `created_at` (DateTime)

**Indexes:**
- `status` (for quick filtering of available drivers)

### Ride Requests Table
- `id` (UUID, Primary Key)
- `rider_id` (String)
- `pickup_lat` (Float)
- `pickup_lng` (Float)
- `dropoff_lat` (Float)
- `dropoff_lng` (Float)
- `pickup_address` (String)
- `dropoff_address` (String)
- `priority` (Enum: LOW, NORMAL, HIGH)
- `status` (Enum: PENDING, QUEUED, ASSIGNED, EN_ROUTE, IN_PROGRESS, COMPLETED, FAILED, RETRYING)
- `retry_count` (Integer)
- `max_retries` (Integer)
- `assigned_driver_id` (Foreign Key → Driver.id)
- `created_at`, `queued_at`, `assigned_at`, `picked_up_at`, `completed_at`, `failed_at` (DateTime)

**Indexes:**
- `rider_id` (for quick lookup of rider's requests)
- `status` (for filtering requests by status)

**Foreign Keys:**
- `assigned_driver_id` references `drivers.id` with back-population relationship

## Migrations

Alembic is used for database schema management and versioning.

### Creating a New Migration

```bash
# Automatically generate migration from model changes
alembic revision --autogenerate -m "Description of changes"

# Or create an empty migration
alembic revision -m "Description of changes"
```

### Applying Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Apply specific number of migrations
alembic upgrade +2

# Revert to previous migration
alembic downgrade -1

# View migration history
alembic current
alembic history
```

## Seed Data

The `scripts/seed_db.py` script populates the database with:

- **25 drivers** with:
  - Randomized names
  - Ratings between 4.0 and 5.0
  - Locations spread across 9 different NYC areas
  - Capacity between 1 and 3 rides
  
- **5 test ride requests** with:
  - Random pickup and dropoff locations
  - Random priorities (LOW, NORMAL, HIGH)
  - Status set to PENDING (awaiting assignment)

Run the script again to verify the database state (it won't duplicate data if it already exists).

## Database Drivers

### SQLite (Development)
- Uses `aiosqlite` for async support
- File-based database at `./ridematch.db`
- Perfect for local development and testing

### PostgreSQL (Production)
- Uses `asyncpg` for async support
- Requires PostgreSQL server installed
- Update `DATABASE_URL` in `.env` to connect

Example PostgreSQL URL:
```
postgresql+asyncpg://username:password@localhost:5432/ridematch_db
```

## Working with the Database

### Async Sessions

The database module provides an async session factory:

```python
from app.database import AsyncSessionLocal

async with AsyncSessionLocal() as session:
    # Perform database operations
    result = await session.execute(select(Driver))
    drivers = result.scalars().all()
```

### Using with FastAPI Dependencies

```python
from app.database import get_db
from fastapi import Depends

@app.get("/drivers")
async def list_drivers(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Driver))
    return result.scalars().all()
```

## Database Files

- `app/database.py` - Database configuration and session setup
- `app/models/driver.py` - Driver ORM model
- `app/models/ride_request.py` - RideRequest ORM model
- `alembic/` - Migration directory
- `scripts/seed_db.py` - Database seeding script
- `.env.example` - Environment configuration template
