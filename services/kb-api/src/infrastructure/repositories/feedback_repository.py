"""MessageFeedback Repository — 評分資料存取層。"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.dto.feedback_dto import FeedbackStatsDTO
from src.infrastructure.persistence.models.feedback import MessageFeedback


class SQLAlchemyFeedbackRepository:
    """SQLAlchemy 實作的評分資料存取層。"""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def upsert(
        self,
        message_id: int,
        user_id: int,
        rating: str,
        comment: str | None,
    ) -> MessageFeedback:
        """建立或更新評分（同一使用者對同一訊息只保留最新評分）。"""
        # 先嘗試找已存在的評分
        result = await self._db.execute(
            select(MessageFeedback).where(
                MessageFeedback.message_id == message_id,
                MessageFeedback.user_id == user_id,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.rating = rating
            existing.comment = comment
            await self._db.commit()
            await self._db.refresh(existing)
            return existing

        feedback = MessageFeedback(
            message_id=message_id,
            user_id=user_id,
            rating=rating,
            comment=comment,
        )
        self._db.add(feedback)
        try:
            await self._db.commit()
            await self._db.refresh(feedback)
        except IntegrityError:
            await self._db.rollback()
            # race condition — 再 select 一次回傳
            result = await self._db.execute(
                select(MessageFeedback).where(
                    MessageFeedback.message_id == message_id,
                    MessageFeedback.user_id == user_id,
                )
            )
            return result.scalar_one()
        return feedback

    async def get_ratings_by_session_user(
        self, session_id: str, user_id: int
    ) -> dict[int, str]:
        """回傳 {message_id: rating} — 指定 session 下該使用者的所有評分。"""
        from src.infrastructure.persistence.models.chat import ChatMessage

        result = await self._db.execute(
            select(MessageFeedback.message_id, MessageFeedback.rating)
            .join(ChatMessage, ChatMessage.id == MessageFeedback.message_id)
            .where(
                ChatMessage.session_id == session_id,
                MessageFeedback.user_id == user_id,
            )
        )
        return {row.message_id: row.rating for row in result.all()}

    async def get_stats_by_session(self, session_id: str) -> FeedbackStatsDTO:
        """統計指定 session 所有訊息的評分數量。"""
        from src.infrastructure.persistence.models.chat import ChatMessage

        result = await self._db.execute(
            select(
                MessageFeedback.rating,
                func.count(MessageFeedback.id).label("cnt"),
            )
            .join(ChatMessage, ChatMessage.id == MessageFeedback.message_id)
            .where(ChatMessage.session_id == session_id)
            .group_by(MessageFeedback.rating)
        )
        rows = result.all()
        counts = {row.rating: row.cnt for row in rows}
        up = counts.get("up", 0)
        down = counts.get("down", 0)
        return FeedbackStatsDTO(total=up + down, up=up, down=down)