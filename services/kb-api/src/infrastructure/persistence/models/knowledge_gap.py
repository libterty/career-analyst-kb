"""KnowledgeGap ORM 模型 — 記錄答案品質不足的問題，供後續改善使用。"""
from __future__ import annotations

from sqlalchemy import Column, Float, Integer, String, Text

from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.models._base import TS, now


class KnowledgeGap(Base):
    __tablename__ = "knowledge_gaps"

    id = Column(Integer, primary_key=True, index=True)
    question_hash = Column(String(64), nullable=False, index=True)
    redacted_question = Column(Text, nullable=False)
    agent_name = Column(String(50), nullable=False)
    trigger = Column(String(50), nullable=False)
    quality_score = Column(Float, nullable=True)
    status = Column(String(20), nullable=False, server_default="open")
    occurrences = Column(Integer, nullable=False, server_default="1")
    created_at = Column(TS, default=now)
    last_seen_at = Column(TS, default=now, onupdate=now)
