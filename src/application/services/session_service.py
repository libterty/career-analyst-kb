"""Session Service — 對話 Session 業務邏輯。

職責（SRP）：
    - 建立 Session
    - 列出使用者的 Session
    - 取得 Session 詳細資訊（含訊息）
    - 重新命名 Session
    - 刪除 Session
    - 檢查訊息數量是否達到上限
"""
from __future__ import annotations

import uuid

from fastapi import HTTPException, status

from src.application.dto.session_dto import (
    MessageDTO,
    SessionDetailDTO,
    SessionListItemDTO,
)
from src.core.interfaces.repository import IChatSessionRepository


class SessionService:
    """對話 Session 管理服務。"""

    def __init__(
        self,
        session_repo: IChatSessionRepository,
        max_messages_per_session: int = 100,
        max_sessions_per_user: int = 20,
    ) -> None:
        self._repo = session_repo
        self._max_messages = max_messages_per_session
        self._max_sessions = max_sessions_per_user

    async def create_session(
        self, user_id: int, title: str | None = None, max_sessions: int | None = None
    ) -> SessionListItemDTO:
        """建立新 Session，回傳 SessionListItemDTO。

        若使用者的 Session 數量已達上限，回傳 429。
        max_sessions 優先使用傳入值，否則使用 self._max_sessions（全域預設）。
        """
        limit = max_sessions if max_sessions is not None else self._max_sessions
        count = await self._repo.count_by_user(user_id)
        if count >= limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"已達對話數量上限（最多 {limit} 個），請刪除舊對話後再建立新的。",
            )
        session_id = str(uuid.uuid4())
        session = await self._repo.create_session(session_id, user_id, title)
        return SessionListItemDTO(
            session_id=session.session_id,
            title=session.title,
            message_count=session.message_count,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

    async def list_sessions(
        self, user_id: int, page: int = 1, page_size: int = 20
    ) -> list[SessionListItemDTO]:
        """列出使用者的 Session（分頁，依更新時間倒序）。"""
        offset = (page - 1) * page_size
        sessions = await self._repo.list_by_user(user_id, limit=page_size, offset=offset)
        return [
            SessionListItemDTO(
                session_id=s.session_id,
                title=s.title,
                message_count=s.message_count,
                created_at=s.created_at,
                updated_at=s.updated_at,
            )
            for s in sessions
        ]

    async def get_session(
        self, session_id: str, user_id: int, ratings: dict[int, str] | None = None
    ) -> SessionDetailDTO:
        """取得 Session 詳細資訊（含訊息列表）。

        Raises:
            HTTPException 404: Session 不存在
            HTTPException 403: 非 Session 擁有者
        """
        session = await self._repo.find_by_session_id(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' 不存在",
            )
        if session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="無權存取此 Session",
            )

        messages = await self._repo.get_messages(session_id, limit=1000)
        _ratings = ratings or {}
        return SessionDetailDTO(
            session_id=session.session_id,
            title=session.title,
            messages=[
                MessageDTO(
                    id=m.id,
                    role=m.role,
                    content=m.content,
                    created_at=m.created_at,
                    my_rating=_ratings.get(m.id) if m.id is not None else None,
                )
                for m in messages
            ],
            message_count=session.message_count,
        )

    async def rename_session(
        self, session_id: str, user_id: int, title: str
    ) -> bool:
        """重新命名 Session。

        Raises:
            HTTPException 404: Session 不存在
            HTTPException 403: 非 Session 擁有者
        """
        session = await self._repo.find_by_session_id(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' 不存在",
            )
        if session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="無權修改此 Session",
            )
        return await self._repo.update_title(session_id, title)

    async def delete_session(self, session_id: str, user_id: int) -> bool:
        """刪除指定 Session。

        Raises:
            HTTPException 404: Session 不存在
            HTTPException 403: 非 Session 擁有者
        """
        session = await self._repo.find_by_session_id(session_id)
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Session '{session_id}' 不存在",
            )
        if session.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="無權刪除此 Session",
            )
        return await self._repo.delete_session(session_id)

    async def check_message_limit(self, session_id: str) -> bool:
        """檢查 Session 是否低於訊息上限。

        Returns:
            True：訊息數量尚未達到上限，可繼續發送
            False：已達上限
        """
        count = await self._repo.get_message_count(session_id)
        return count < self._max_messages
