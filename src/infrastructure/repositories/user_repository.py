"""SQLAlchemy 使用者 Repository 實作。"""
from __future__ import annotations

from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.interfaces.repository import IUserRepository
from src.infrastructure.persistence.models import User


class SQLAlchemyUserRepository(IUserRepository):
    """以 SQLAlchemy 實作的使用者資料存取層。

    路由層不直接使用 SQLAlchemy，只依賴 IUserRepository 介面。
    可在測試中替換為 InMemoryUserRepository，無需真實資料庫。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_by_username(self, username: str) -> User | None:
        result = await self._session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        username: str,
        hashed_password: str,
        role: str,
    ) -> User:
        user = User(
            username=username,
            hashed_password=hashed_password,
            role=role,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def find_by_id(self, user_id: int) -> User | None:
        result = await self._session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> Sequence[User]:
        result = await self._session.execute(
            select(User).order_by(User.created_at)
        )
        return result.scalars().all()

    async def delete(self, user_id: int) -> bool:
        user = await self.find_by_id(user_id)
        if user is None:
            return False
        await self._session.delete(user)
        await self._session.commit()
        return True

    async def update_max_sessions(self, user_id: int, max_sessions: int) -> None:
        user = await self.find_by_id(user_id)
        if user is not None:
            user.max_sessions = max_sessions
            await self._session.commit()

    async def update_password(self, user_id: int, hashed_password: str) -> None:
        user = await self.find_by_id(user_id)
        if user is not None:
            user.hashed_password = hashed_password
            await self._session.commit()

    async def count_by_role(self, role: str) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(User).where(User.role == role)
        )
        return result.scalar_one()
