"""Base repository class with common database operations."""

from abc import ABC
from typing import Generic, List, Optional, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

T = TypeVar("T", bound=DeclarativeBase)


class BaseRepository(ABC, Generic[T]):

    def __init__(self, session: AsyncSession, model: type[T]):
        self.session = session
        self.model = model

    async def create(self, obj_in: dict) -> T:
        db_obj = self.model(**obj_in)
        self.session.add(db_obj)
        await self.session.flush()
        return db_obj

    async def get_by_id(self, obj_id: str) -> Optional[T]:
        result = await self.session.execute(select(self.model).where(self.model.id == obj_id))
        return result.scalars().first()

    async def get_all(self, skip: int = 0, limit: int = 100) -> List[T]:
        result = await self.session.execute(
            select(self.model).offset(skip).limit(limit)
        )
        return result.scalars().all()

    async def update(self, obj_id: str, obj_in: dict) -> Optional[T]:
        db_obj = await self.get_by_id(obj_id)
        if not db_obj:
            return None
        
        for key, value in obj_in.items():
            if value is not None:
                setattr(db_obj, key, value)
        
        await self.session.flush()
        return db_obj

    async def delete(self, obj_id: str) -> bool:
        db_obj = await self.get_by_id(obj_id)
        if not db_obj:
            return False
        
        await self.session.delete(db_obj)
        await self.session.flush()
        return True

    async def commit(self):
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()
