"""PostgreSQL 連線管理（SQLAlchemy async engine + session factory）。

ORM 模型移至 models.py，此檔案只負責連線基礎設施。
"""
from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.core.config import get_settings


def _build_engine():
    settings = get_settings()
    return create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,  # 每次取出連線前先 ping，自動重連斷線的連線
    )


engine = _build_engine()

# expire_on_commit=False：commit 後不自動過期 ORM 物件，
# 避免非同步環境下的 lazy load 問題
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """所有 ORM 模型的基礎類別。"""


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency：提供資料庫 Session，請求結束後自動關閉。"""
    async with AsyncSessionLocal() as session:
        yield session


async def create_tables() -> None:
    """建立所有資料表（若不存在）。應用程式啟動時呼叫。"""
    from src.infrastructure.persistence import models  # noqa: F401 確保模型已載入

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
