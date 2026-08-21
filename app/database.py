"""Database configuration and async SQLAlchemy setup."""

import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

# Database URL configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./ridematch.db")

# Create async engine — pool_size/max_overflow are QueuePool-only args (Postgres);
# SQLite's async driver uses NullPool and rejects them.
engine_kwargs = {
    "echo": os.getenv("SQL_ECHO", "False").lower() == "true",
    "future": True,
}
if not DATABASE_URL.startswith("sqlite"):
    engine_kwargs["pool_size"] = 50
    engine_kwargs["max_overflow"] = 20

engine = create_async_engine(DATABASE_URL, **engine_kwargs)

# Create async session factory
AsyncSessionLocal = sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

# Base class for models
Base = declarative_base()


async def get_db():
    """Dependency for getting database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database connections."""
    await engine.dispose()