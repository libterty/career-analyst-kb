"""SystemPrompt ORM 模型 — 管理員可配置的系統提示詞。"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.models._base import TS, now


class SystemPrompt(Base):
    """系統提示詞資料表。

    只允許一個提示詞同時為 active（is_active=True）。
    content 必須包含 {context} 佔位符，供 RAG 插入檢索段落。

    Attributes:
        name:       提示詞名稱（如 "default"、"concise"）
        content:    提示詞完整內容，必須包含 {context}
        is_active:  是否為當前使用中的提示詞
        created_by: 建立者的使用者 ID
    """

    __tablename__ = "system_prompts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    content = Column(Text, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(TS, default=now)
    updated_at = Column(TS, default=now, onupdate=now)

    creator = relationship("User")