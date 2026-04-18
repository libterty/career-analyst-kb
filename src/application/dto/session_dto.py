"""對話 Session 相關 DTO。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_serializer

from src.application.dto.common import TimestampMixin


class MessageDTO(TimestampMixin):
    """單則訊息的回應 DTO。"""

    id: int | None = None
    role: str
    content: str
    created_at: datetime
    my_rating: str | None = None

    model_config = {"from_attributes": True}

    @field_serializer("created_at")
    def _ser_created_at(self, v: datetime) -> str | None:
        return self._fmt(v)


class SessionListItemDTO(TimestampMixin):
    """Session 列表項目 DTO（不含訊息內容）。"""

    session_id: str
    title: str | None
    message_count: int
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}

    @field_serializer("created_at", "updated_at")
    def _ser_dt(self, v: datetime | None) -> str | None:
        return self._fmt(v)


class SessionDetailDTO(TimestampMixin):
    """Session 詳細資訊 DTO（含完整訊息列表）。"""

    session_id: str
    title: str | None
    messages: list[MessageDTO]
    message_count: int

    model_config = {"from_attributes": True}


class CreateSessionDTO(BaseModel):
    """建立新 Session 的請求 DTO。"""

    title: str | None = None


class RenameSessionDTO(BaseModel):
    """重新命名 Session 的請求 DTO。"""

    title: str = Field(min_length=1, max_length=200)
