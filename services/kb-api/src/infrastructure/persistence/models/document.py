"""Document ORM 模型。"""
from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.models._base import TS, now


class Document(Base):
    """已匯入文件的 metadata 資料表。

    Milvus 儲存向量與內容，PostgreSQL 儲存文件的管理資訊。
    doc_hash 為 SHA-256 指紋，用於防止同一文件重複匯入。
    """

    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    doc_hash = Column(String(32), unique=True, index=True)
    pages = Column(Integer)
    chunk_count = Column(Integer)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    uploaded_at = Column(TS, default=now)

    uploader = relationship("User", foreign_keys=[uploaded_by])
