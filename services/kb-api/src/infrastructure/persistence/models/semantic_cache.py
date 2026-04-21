"""SemanticCacheEntry ORM 模型 — 語意快取的 metadata 儲存。"""
from __future__ import annotations

import json

from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship

from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.models._base import TS, now


class SemanticCacheEntry(Base):
    """語意快取資料表。

    Attributes:
        cache_key:    Milvus 中向量對應的唯一 ID（UUID）
        query_text:   原始問題
        answer:       LLM 回答
        sources_json: JSON 序列化的來源文件列表
        hit_count:    被命中的次數
        expires_at:   快取過期時間（NULL 表示永不過期）
    """

    __tablename__ = "semantic_cache_entries"

    id = Column(Integer, primary_key=True, index=True)
    cache_key = Column(String(64), unique=True, nullable=False, index=True)
    query_text = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    sources_json = Column(Text, nullable=True)   # JSON list
    hit_count = Column(Integer, default=0, nullable=False)
    created_at = Column(TS, default=now)
    expires_at = Column(TS, nullable=True)

    def get_sources(self) -> list[dict]:
        """反序列化來源文件列表。"""
        if not self.sources_json:
            return []
        try:
            return json.loads(self.sources_json)
        except Exception:
            return []