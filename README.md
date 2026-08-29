# RideMatch

An asynchronous ride-dispatch backend which continuously matches incoming ride requests with the best available drivers without human intervention.

Built with FastAPI, SQLAlchemy 2.0, PostgreSQL, and Docker, RideMatch combines a background dispatch worker, weighted driver-matching algorithm, ride state machine, and automated retry system.

# How it Works
1. Riders submit a ride request with pickup, dropoff, and priority.
2. Requests enter a queue and are continuously processed by a background worker.
3. The matching engine evaluates available drivers using:
- Distance from pickup
- Driver quality
- Ride priority
- Current driver workload
- Dropoff alignment

4. The highest-scoring driver is assigned to the ride.
5. If no driver is available, the request automatically retries using exponential backoff.
6. Every ride follows a validated lifecycle to prevent invalid state changes.
- PENDING → QUEUED → ASSIGNED → EN_ROUTE → IN_PROGRESS → COMPLETED
              ↓
           FAILED → RETRYING → PENDING

# Tech Stack
	
Backend - FastAPI, Python, Pydantic
Database - PostgreSQL, SQLAlchemy 2.0
Deployment - Docker Compose
Possibly will add Redis in the future. 

# Features
- Weighted matching algorithm - scores drivers on proximity, priority, workload, and dropoff alignment
- Finite state machine enforcing every ride's lifecycle, so no ride can enter an invalid state
- Row-level locking to prevent double-booking a driver under concurrent load
- Exponential backoff retry queue for unmatched rides
- Async event bus decoupling metrics/logging from core dispatch logic
- Independently deployable API and background worker processes (Docker Compose)
- Two-tier test suite — unit tests plus real integration tests against a live database session
- Load-tested under concurrent traffic; diagnosed and resolved three infrastructure bottlenecks

## Project Structure

- `app/` - Main application code
  - `api/` - API routes and endpoints
  - `engine/` - Core matching and queue management logic
  - `models/` - Data models
  - `services/` - Business logic services
- `tests/` - Test suite

## Setup

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   pip install -e ".[dev]" 
   ```

3. Run tests:
   ```bash
   pytest
   ```

## Development

Make sure to install pre-commit hooks:
```bash
pre-commit install
```