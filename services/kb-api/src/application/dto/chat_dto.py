"""問答相關 DTO（含嚴格輸入驗證）。"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class ChatRequestDTO(BaseModel):
    """問答請求 DTO。

    驗證規則：
        - question:   1-2000 字元
        - session_id: 最長 64 字元，只允許字母數字底線連字號
        - language:   只允許 zh-TW 或 en
    """

    model_config = ConfigDict(strict=True)

    question: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="使用者問題（1-2000 字元）",
        examples=["三寶是什麼意思？"],
    )
    session_id: str = Field(
        default="default",
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="對話 session 識別碼",
    )
    language: str = Field(
        default="zh-TW",
        pattern=r"^(zh-TW|en)$",
        description="回應語言偏好：zh-TW | en",
    )
    topic: str | None = Field(
        default=None,
        description="限縮搜索主題（如 interview、salary、career_planning 等），None 表示不限制",
    )


class SourceDocumentDTO(BaseModel):
    """引用的來源資訊 DTO。"""

    source: str = Field(description="來源文件名稱")
    section: str = Field(description="所屬章節／主題")
    score: float = Field(ge=0.0, description="相似度分數")
    page_number: int | None = Field(default=None, description="來源頁碼（None 表示無頁碼資訊）")
    video_title: str = Field(default="", description="影片標題")
    upload_date: str = Field(default="", description="上傳日期（YYYYMMDD）")
    url: str = Field(default="", description="YouTube 影片連結")


class ChatResponseDTO(BaseModel):
    """問答回應 DTO（非串流版本）。"""

    answer: str
    session_id: str
    sources: list[SourceDocumentDTO] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
