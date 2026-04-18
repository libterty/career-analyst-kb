"""User ORM 模型。"""
from __future__ import annotations

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.models._base import TS, now


class User(Base):
    """使用者資料表。

    角色說明：
        viewer: 只能查詢問答
        editor: 可上傳文件 + 查詢問答
        admin:  完整系統管理權限
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    hashed_password = Column(String(128), nullable=False)
    role = Column(String(20), default="viewer")
    max_sessions = Column(Integer, nullable=False, default=20, server_default="20")
    created_at = Column(TS, default=now)

    sessions = relationship("ChatSession", back_populates="user", lazy="dynamic")
