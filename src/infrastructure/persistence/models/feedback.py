"""MessageFeedback ORM 模型 — 記錄使用者對 AI 回覆的評分。"""
from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.models._base import TS, now


class MessageFeedback(Base):
    """訊息評分資料表。

    每位使用者對每則訊息只能評分一次（unique message_id + user_id）。

    Attributes:
        message_id: 被評分的訊息 ID（FK -> chat_messages.id）
        user_id:    評分的使用者 ID（FK -> users.id）
        rating:     "up"（好）或 "down"（差）
        comment:    可選的文字說明
    """

    __tablename__ = "message_feedbacks"
    __table_args__ = (
        UniqueConstraint("message_id", "user_id", name="uq_feedback_message_user"),
    )

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    rating = Column(String(8), nullable=False)   # "up" | "down"
    comment = Column(Text, nullable=True)
    created_at = Column(TS, default=now)

    message = relationship("ChatMessage", back_populates="feedback")
    user = relationship("User")