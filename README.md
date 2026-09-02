# RideMatch 

RideMatch is a FastAPI-based ride dispatch backend that models ride request intake, driver matching, queue processing, retries, and lifecycle state management. The project is structured around API, service, repository, and engine layers to keep business logic, matching behavior, and workflow processing separated and easier to reason about.

## Architecture
The system is organized into distinct layers for request handling, business logic, persistence, and matching behavior. Ride lifecycle rules are centralized in the state machine, while background worker processing coordinates retries and dispatch work asynchronously. Redis handles async ride-matching jobs, delayed retries, deduplication, and dead-letter handling.

## Tech stack
- Python
- FastAPI
- SQLAlchemy 2.0
- SQLite for local development
- Docker / Docker Compose
- pytest

## Quick start 
```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
pytest -q
```

## Project structure
- `app/` — API, services, models, queue logic, matching engine
- `tests/` — automated validation
- `alembic/` — database migrations
- `docker-compose.yml` — local service setup 

