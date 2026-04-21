"""通用 Response DTO。"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """統一錯誤回應格式。"""

    detail: str
    error_code: str | None = None


class PaginatedResponse(BaseModel):
    """分頁回應格式。"""

    items: list
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=100)


class TimestampMixin(BaseModel):
    """為含有 datetime 欄位的 DTO 提供統一的 UTC 序列化。

    繼承此 Mixin 後，所有 datetime 欄位皆以 ISO 8601 + Z 結尾格式輸出：
        例：2026-03-18T07:52:00.123Z

    規則：
    - naive datetime 視為 UTC
    - timezone-aware datetime 轉換為 UTC 後輸出
    """

    @staticmethod
    def _fmt(v: datetime | None) -> str | None:
        if v is None:
            return None
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        else:
            v = v.astimezone(timezone.utc)
        ms = v.microsecond // 1000
        return v.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ms:03d}Z"
