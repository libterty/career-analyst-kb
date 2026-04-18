"""SQLAlchemy 對話 Session Repository 實作。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.interfaces.repository import IChatSessionRepository
from src.infrastructure.persistence.models import ChatMessage, ChatSession


class SQLAlchemyChatSessionRepository(IChatSessionRepository):
    """以 SQLAlchemy 實作的對話 Session 資料存取層。

    message_count 遞增採用原子性 UPDATE ... SET message_count = message_count + 1，
    避免高並發環境下的競態條件。
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_session(
        self, session_id: str, user_id: int, title: str | None = None
    ) -> ChatSession:
        """建立新 Session 並回傳 ORM 實例。"""
        chat_session = ChatSession(
            session_id=session_id,
            user_id=user_id,
            title=title,
        )
        self._session.add(chat_session)
        await self._session.commit()
        await self._session.refresh(chat_session)
        return chat_session

    async def find_by_session_id(self, session_id: str) -> ChatSession | None:
        """依 session_id 查詢，找不到回傳 None。"""
        result = await self._session.execute(
            select(ChatSession).where(ChatSession.session_id == session_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(
        self, user_id: int, limit: int, offset: int
    ) -> list[ChatSession]:
        """取得指定使用者的 Session 列表（依更新時間倒序）。"""
        result = await self._session.execute(
            select(ChatSession)
            .where(ChatSession.user_id == user_id)
            .order_by(ChatSession.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def update_title(self, session_id: str, title: str) -> bool:
        """更新 Session 標題，成功回傳 True。"""
        result = await self._session.execute(
            update(ChatSession)
            .where(ChatSession.session_id == session_id)
            .values(title=title, updated_at=datetime.now(timezone.utc))
        )
        await self._session.commit()
        return result.rowcount > 0

    async def delete_session(self, session_id: str) -> bool:
        """刪除指定 Session（連同訊息），成功回傳 True。"""
        chat_session = await self.find_by_session_id(session_id)
        if not chat_session:
            return False
        await self._session.delete(chat_session)
        await self._session.commit()
        return True

    async def add_message(
        self, session_id: str, role: str, content: str
    ) -> ChatMessage:
        """新增訊息並回傳 ORM 實例。"""
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
        )
        self._session.add(message)
        await self._session.commit()
        await self._session.refresh(message)
        return message

    async def get_messages(self, session_id: str, limit: int = 100) -> list[ChatMessage]:
        """取得指定 Session 的訊息列表（依建立時間正序）。"""
        result = await self._session.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.created_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_message_count(self, session_id: str) -> int:
        """取得指定 Session 的訊息數量（讀取 message_count 欄位）。"""
        result = await self._session.execute(
            select(ChatSession.message_count).where(
                ChatSession.session_id == session_id
            )
        )
        count = result.scalar_one_or_none()
        return count if count is not None else 0

    async def count_by_user(self, user_id: int) -> int:
        """計算指定使用者的 Session 數量。"""
        result = await self._session.execute(
            select(func.count()).select_from(ChatSession).where(ChatSession.user_id == user_id)
        )
        return result.scalar_one() or 0

    async def increment_message_count(self, session_id: str) -> int:
        """原子性遞增訊息計數，回傳更新後的數量。

        使用 UPDATE ... SET message_count = message_count + 1 確保原子性，
        避免高並發競態條件。
        """
        await self._session.execute(
            update(ChatSession)
            .where(ChatSession.session_id == session_id)
            .values(
                message_count=ChatSession.message_count + 1,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self._session.commit()
        return await self.get_message_count(session_id)
