"""認證相關 DTO（含嚴格輸入驗證）。

Pydantic v2 ConfigDict(strict=True) 禁止隱式型別轉換，
field_validator 加入密碼強度規則。
"""
from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from src.application.dto.common import TimestampMixin


class UserCreateDTO(BaseModel):
    """建立使用者的請求 DTO。

    驗證規則：
        - username: 3-50 字元，只允許字母數字底線連字號
        - password: 8-128 字元，需包含大寫字母與數字
        - role:     只允許 viewer | editor | admin
    """

    model_config = ConfigDict(strict=True)

    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="使用者名稱（字母、數字、底線、連字號）",
        examples=["admin_user"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="密碼（至少 8 碼，需含大寫字母與數字）",
    )
    role: str = Field(
        default="viewer",
        pattern=r"^(viewer|editor|admin)$",
        description="角色：viewer | editor | admin",
    )

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """密碼強度驗證：需含大寫字母與數字。"""
        if not re.search(r"[A-Z]", v):
            raise ValueError("密碼必須包含至少一個大寫字母")
        if not re.search(r"[0-9]", v):
            raise ValueError("密碼必須包含至少一個數字")
        return v


class TokenDTO(BaseModel):
    """JWT Token 回應 DTO。"""

    access_token: str
    token_type: str = "bearer"


class UserDTO(BaseModel):
    """使用者資訊回應 DTO（不含密碼）。"""

    id: int
    username: str
    role: str


class UserUpdatePasswordDTO(BaseModel):
    """管理員更新使用者密碼的請求 DTO。"""

    new_password: str = Field(min_length=8)


class UserListItemDTO(TimestampMixin):
    """使用者列表項目 DTO（管理員使用）。"""

    id: int
    username: str
    role: str
    max_sessions: int
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("created_at")
    def _ser_created_at(self, v: datetime | None) -> str | None:
        return self._fmt(v)


class UserUpdateMaxSessionsDTO(BaseModel):
    """管理員更新使用者 Session 上限的請求 DTO。"""

    max_sessions: int = Field(..., ge=1, le=1000, description="最多可建立的 Session 數量")
