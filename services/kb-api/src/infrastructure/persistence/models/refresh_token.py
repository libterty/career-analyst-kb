"""RefreshToken ORM 模型。"""
from __future__ import annotations

from sqlalchemy import Column, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.models._base import TS, now


class RefreshToken(Base):
    """Refresh Token 資料表。

    儲存 SHA-256(raw_token)，永不儲存明文 token。
    每次使用後 revoked_at 會被填入（token rotation），防止重放攻擊。
    """

    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at = Column(TS, nullable=False)
    revoked_at = Column(TS, nullable=True)
    created_at = Column(TS, default=now)

    user = relationship("User", lazy="select")
