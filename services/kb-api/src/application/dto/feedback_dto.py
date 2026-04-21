"""回覆品質回饋相關 DTO。"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class FeedbackCreateDTO(BaseModel):
    """建立或更新評分的請求 DTO。"""

    message_id: int = Field(description="被評分的訊息 ID")
    rating: Literal["up", "down"] = Field(description="評分：up（好）或 down（差）")
    comment: str | None = Field(default=None, max_length=500, description="可選文字說明")


class FeedbackResponseDTO(BaseModel):
    """評分回應 DTO。"""

    id: int
    message_id: int
    rating: str
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedbackStatsDTO(BaseModel):
    """Session 評分統計 DTO。"""

    total: int = Field(description="總評分數")
    up: int = Field(description="好評數")
    down: int = Field(description="差評數")
