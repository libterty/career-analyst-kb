"""系統提示詞相關 DTO。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class SystemPromptCreateDTO(BaseModel):
    """建立系統提示詞的請求 DTO。"""

    name: str = Field(min_length=1, max_length=100, description="提示詞名稱")
    content: str = Field(min_length=10, description="提示詞內容，必須包含 {context}")

    @field_validator("content")
    @classmethod
    def must_have_context_placeholder(cls, v: str) -> str:
        if "{context}" not in v:
            raise ValueError("提示詞內容必須包含 {context} 佔位符")
        return v


class SystemPromptUpdateDTO(BaseModel):
    """更新系統提示詞的請求 DTO。"""

    name: str | None = Field(default=None, min_length=1, max_length=100, description="提示詞名稱（可選）")
    content: str = Field(min_length=10, description="新的提示詞內容，必須包含 {context}")

    @field_validator("content")
    @classmethod
    def must_have_context_placeholder(cls, v: str) -> str:
        if "{context}" not in v:
            raise ValueError("提示詞內容必須包含 {context} 佔位符")
        return v


class SystemPromptResponseDTO(BaseModel):
    """系統提示詞回應 DTO。"""

    id: int
    name: str
    content: str
    is_active: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}
