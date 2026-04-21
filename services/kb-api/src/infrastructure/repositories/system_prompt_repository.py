"""SystemPrompt Repository — 系統提示詞資料存取層。"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.persistence.models.system_prompt import SystemPrompt


class SQLAlchemySystemPromptRepository:
    """SQLAlchemy 實作的系統提示詞資料存取層。"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_active(self) -> SystemPrompt | None:
        """取得第一個啟用中的系統提示詞（向下相容）。"""
        result = await self._db.execute(
            select(SystemPrompt).where(SystemPrompt.is_active.is_(True)).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_all_active(self) -> list[SystemPrompt]:
        """取得所有啟用中的系統提示詞（依建立時間排序）。"""
        result = await self._db.execute(
            select(SystemPrompt)
            .where(SystemPrompt.is_active.is_(True))
            .order_by(SystemPrompt.created_at)
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[SystemPrompt]:
        """列出所有系統提示詞。"""
        result = await self._db.execute(
            select(SystemPrompt).order_by(SystemPrompt.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, prompt_id: int) -> SystemPrompt | None:
        result = await self._db.execute(
            select(SystemPrompt).where(SystemPrompt.id == prompt_id)
        )
        return result.scalar_one_or_none()

    async def create(self, name: str, content: str, created_by: int | None) -> SystemPrompt:
        """建立新的系統提示詞（預設未啟用）。"""
        prompt = SystemPrompt(name=name, content=content, created_by=created_by, is_active=False)
        self._db.add(prompt)
        await self._db.commit()
        await self._db.refresh(prompt)
        return prompt

    async def update_content(
        self, prompt_id: int, content: str, name: str | None = None
    ) -> SystemPrompt | None:
        """更新提示詞內容（及可選的名稱）。"""
        prompt = await self.get_by_id(prompt_id)
        if prompt is None:
            return None
        prompt.content = content
        if name is not None:
            prompt.name = name
        await self._db.commit()
        await self._db.refresh(prompt)
        return prompt

    async def toggle_active(self, prompt_id: int) -> SystemPrompt | None:
        """切換指定提示詞的啟用狀態（不影響其他提示詞）。"""
        prompt = await self.get_by_id(prompt_id)
        if prompt is None:
            return None
        prompt.is_active = not prompt.is_active
        await self._db.commit()
        await self._db.refresh(prompt)
        return prompt

    async def delete(self, prompt_id: int) -> bool:
        """刪除提示詞（不允許刪除正在啟用的提示詞）。"""
        prompt = await self.get_by_id(prompt_id)
        if prompt is None:
            return False
        if prompt.is_active:
            raise ValueError("無法刪除正在使用中的提示詞，請先啟用其他提示詞")
        await self._db.delete(prompt)
        await self._db.commit()
        return True