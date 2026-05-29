# Architecture Documentation

## Overview

RideMatch follows a clean, layered architecture with clear separation of concerns:

```
┌─────────────────────────────────────┐
│        API Routes (FastAPI)         │
│  (driver_routes.py, ride_routes.py) │
└────────────────┬────────────────────┘
                 │
┌────────────────▼────────────────────┐
│       Service Layer (Business)      │
│ (driver_service.py, ride_service.py)│
└────────────────┬────────────────────┘
                 │
┌────────────────▼────────────────────┐
│       Repository Layer (Data)       │
│(driver_repository.py, ride_repo.py) │
└────────────────┬────────────────────┘
                 │
┌────────────────▼────────────────────┐
│      SQLAlchemy ORM Models          │
│  (driver.py, ride_request.py)       │
└────────────────┬────────────────────┘
                 │
┌────────────────▼────────────────────┐
│      Database (SQLite/PostgreSQL)   │
└─────────────────────────────────────┘
```

## Layer Responsibilities

### 1. API Routes Layer (`app/api/`)

**Purpose:** Handle HTTP requests/responses, validation, and routing.

**Files:**
- `driver_routes.py` - Driver endpoints
- `ride_routes.py` - Ride request endpoints
- `__init__.py` - Package initialization

**Responsibilities:**
- Accept HTTP requests
- Validate input using Pydantic schemas
- Call service methods
- Transform responses to API format
- Handle HTTP status codes and errors

**Example:**
```python
@router.post("/", response_model=DriverResponse)
async def create_driver(driver_in: DriverCreate, service: DriverService = Depends()):
    return await service.create_driver(driver_in)
```

### 2. Service Layer (`app/services/`)

**Purpose:** Implement business logic and orchestrate operations.

**Files:**
- `driver_service.py` - Driver business logic
- `ride_service.py` - Ride request business logic
- `__init__.py` - Package initialization

**Responsibilities:**
- Implement business rules
- Validate operations (e.g., can retry ride?)
- Coordinate multiple repositories
- Handle transactions
- Raise custom exceptions

**Example:**
```python
async def assign_ride(self, request_id: str, driver_id: str):
    request = await self.repo.get_by_id(request_id)
    if not request:
        raise RideRequestNotFound(...)
    if not request.is_assignable():
        raise InvalidRideStatus(...)
    # ... perform assignment
```

### 3. Repository Layer (`app/repositories/`)

**Purpose:** Abstract database access and provide a clean data interface.

**Files:**
- `base.py` - Base repository with common CRUD
- `driver_repository.py` - Driver data access
- `ride_request_repository.py` - Ride request data access
- `__init__.py` - Package initialization

**Responsibilities:**
- Encapsulate database queries
- Provide type-safe data access
- Handle query building
- Support filtering, sorting, pagination
- Return domain models

**Example:**
```python
async def get_available_drivers(self) -> List[Driver]:
    result = await self.session.execute(
        select(Driver).where(Driver.status == DriverStatus.AVAILABLE)
    )
    return result.scalars().all()
```

### 4. Schema Layer (`app/schemas/`)

**Purpose:** Define and validate request/response data structures.

**Files:**
- `schemas.py` - All Pydantic models
- `__init__.py` - Package initialization

**Models:**
- `DriverCreate`, `DriverUpdate`, `DriverResponse`
- `RideRequestCreate`, `RideRequestUpdate`, `RideRequestResponse`
- `MatchResult`, `MatchingBatchResponse`

### 5. Model Layer (`app/models/`)

**Purpose:** Define SQLAlchemy ORM models (data persistence).

**Files:**
- `driver.py` - Driver ORM model
- `ride_request.py` - RideRequest ORM model
- `enums.py` - Enumerations

### 6. Exception Layer (`app/exceptions.py`)

**Purpose:** Define custom application exceptions.

**Exceptions:**
- `RideMatchException` - Base exception
- `DriverNotFound` - Driver lookup failed
- `RideRequestNotFound` - Ride lookup failed
- `DriverNotAvailable` - Driver cannot accept rides
- `RideAlreadyAssigned` - Ride already has assignment
- `CannotRetryRide` - Max retries exceeded
- `InvalidRideStatus` - Operation invalid for current status

## Data Flow Examples

### Creating a Ride Request

```
1. POST /api/v1/rides/
   Request: RideRequestCreate

2. API Route (ride_routes.py)
   - Validates input via Pydantic
   - Calls service.create_ride_request()

3. Service (ride_service.py)
   - Extracts data
   - Calls repository.create()
   - Commits transaction

4. Repository (ride_request_repository.py)
   - Creates RideRequest instance
   - Inserts into database
   - Returns saved object

5. API Route
   - Converts to RideRequestResponse
   - Returns HTTP 201 Created
```

### Assigning a Ride

```
1. POST /api/v1/rides/{request_id}/assign/{driver_id}

2. API Route
   - Validates IDs
   - Calls service.assign_ride()

3. Service
   - Fetches ride request via repository
   - Validates ride is assignable
   - Validates driver availability
   - Updates request status
   - Commits transaction

4. Repository
   - Executes database queries
   - Manages session

5. API Route
   - Returns updated ride response
```

## Key Design Patterns

### 1. Repository Pattern

Abstracts database access behind a uniform interface:

```python
class DriverRepository(BaseRepository[Driver]):
    async def get_available_drivers(self) -> List[Driver]:
        # Query implementation
        pass
```

Benefits:
- Testability (can mock repositories)
- Centralized query logic
- Easy schema changes

### 2. Service/Business Logic Pattern

Concentrates business rules in services:

```python
class DriverService:
    async def assign_ride(self, driver_id, request):
        # Business logic validation
        if not driver.is_assignable:
            raise DriverNotAvailable()
        # ... perform operation
```

Benefits:
- Separates business from data access
- Reusable logic across routes
- Testable in isolation

### 3. Dependency Injection

FastAPI's `Depends()` provides loose coupling:

```python
@router.post("/")
async def create_driver(
    driver_in: DriverCreate,
    service: DriverService = Depends(get_driver_service)
):
    # Service injected at runtime
    pass
```

Benefits:
- Easy testing (inject mocks)
- Runtime flexibility
- Cleaner code

### 4. Base Repository Pattern

Reduces boilerplate with generic base:

```python
class BaseRepository(Generic[T]):
    async def create(self, obj_in: dict) -> T:
        # Common CRUD logic
        pass

class DriverRepository(BaseRepository[Driver]):
    # Specific queries only
    pass
```

Benefits:
- DRY principle
- Consistent interface
- Less code

## Testing Strategy

### Unit Tests (Service Layer)

```python
async def test_assign_ride_validates_availability():
    # Mock repository
    service = RideRequestService(mock_session)
    # Test business logic
    with pytest.raises(DriverNotAvailable):
        await service.assign_ride(...)
```

### Integration Tests (API Layer)

```python
async def test_create_driver_endpoint():
    # Use test database
    response = await client.post("/api/v1/drivers/", json={...})
    assert response.status_code == 201
    assert response.json()["driver_name"] == "John"
```

### Repository Tests

```python
async def test_get_available_drivers():
    # Uses test database
    repo = DriverRepository(test_session)
    drivers = await repo.get_available_drivers()
    assert len(drivers) > 0
```

## Configuration & Dependencies

**File:** `app/dependencies.py`

Provides FastAPI dependency injection functions:

```python
async def get_db() -> AsyncSession:
    """Get database session."""
    async with AsyncSessionLocal() as session:
        yield session

async def get_driver_service(session: AsyncSession) -> DriverService:
    """Get driver service."""
    return DriverService(session)
```

## Database & Models

**File:** `app/database.py`

Configures async SQLAlchemy:
- Async engine with asyncpg/aiosqlite
- Session management
- Database initialization

**Files:** `app/models/driver.py`, `app/models/ride_request.py`

Define SQLAlchemy ORM models with:
- Column definitions
- Relationships
- Computed properties
- Indexes

## Best Practices

1. **Single Responsibility:** Each layer has one job
2. **Dependency Injection:** Services depend on abstractions
3. **Error Handling:** Custom exceptions for business errors
4. **Async/Await:** Non-blocking database operations
5. **Type Hints:** Full type annotations for IDE support
6. **Validation:** Pydantic schemas validate input
7. **Composition:** Services use repositories, not other services
8. **Transaction Safety:** Services manage commits/rollbacks

## Adding a New Feature

### 1. Create Model (`app/models/new_model.py`)
```python
class NewModel(Base):
    __tablename__ = "new_models"
    # ... columns, relationships
```

### 2. Create Repository (`app/repositories/new_repository.py`)
```python
class NewRepository(BaseRepository[NewModel]):
    async def custom_query(self):
        # ... query implementation
```

### 3. Create Service (`app/services/new_service.py`)
```python
class NewService:
    def __init__(self, session: AsyncSession):
        self.repo = NewRepository(session)
    
    async def business_operation(self):
        # ... business logic
```

### 4. Create Schemas (`app/schemas/schemas.py`)
```python
class NewModelCreate(BaseModel):
    # ... fields

class NewModelResponse(BaseModel):
    # ... fields
```

### 5. Create Routes (`app/api/new_routes.py`)
```python
@router.post("/", response_model=NewModelResponse)
async def create_new(
    new_in: NewModelCreate,
    service: NewService = Depends(get_new_service)
):
    return await service.create(new_in)
```

### 6. Include in Main (`app/main.py`)
```python
app.include_router(new_routes.router)
```

## Summary

This architecture provides:
- ✅ Clear separation of concerns
- ✅ Testability at each layer
- ✅ Scalability for adding features
- ✅ Maintainability with clean code
- ✅ Flexibility to change implementations
- ✅ Async performance throughout
