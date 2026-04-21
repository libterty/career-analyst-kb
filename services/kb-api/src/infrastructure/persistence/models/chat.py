"""ChatSession 與 ChatMessage ORM 模型。"""
from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.models._base import TS, now


class ChatSession(Base):
    """對話 Session 資料表。

    session_id 為 UUID 字串，由前端或後端自動產生。
    """

    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), unique=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    title = Column(String(200), nullable=True)
    created_at = Column(TS, default=now)
    updated_at = Column(TS, default=now, onupdate=now)
    message_count = Column(Integer, default=0)

    user = relationship("User", back_populates="sessions")
    messages = relationship("ChatMessage", back_populates="session", lazy="dynamic")


class ChatMessage(Base):
    """對話訊息資料表。

    Attributes:
        role:    "user" 或 "assistant"
        content: 訊息文字
    """

    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(64), ForeignKey("chat_sessions.session_id"), index=True)
    role = Column(String(16))
    content = Column(Text)
    created_at = Column(TS, default=now)

    session = relationship("ChatSession", back_populates="messages")
    feedback = relationship("MessageFeedback", back_populates="message", uselist=False)
