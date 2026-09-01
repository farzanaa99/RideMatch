# RideMatch

A FastAPI-based ride-matching backend for managing ride requests, driver assignment, queue processing, retries, and state validation.

## What it does
- accepts ride requests from riders
- evaluates available drivers using a matching workflow
- assigns rides based on driver availability and queue priority
- tracks ride lifecycle states from request to completion or retry
- retries failed or unmatched rides with backoff
- emits domain events for operational metrics and async processing

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
