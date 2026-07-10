"""KnowledgeGap DTO — 記錄答案品質不足問題的請求與回應結構。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class KnowledgeGapCreateDTO(BaseModel):
    question_hash: str = Field(max_length=64, description="問題的 SHA-256 hash（前64字元）")
    redacted_question: str = Field(description="脫敏後的問題文字")
    agent_name: str = Field(max_length=50, description="觸發的 agent 名稱")
    trigger: str = Field(max_length=50, description="觸發原因，例如 low_quality_score")
    quality_score: float | None = Field(default=None, ge=1, le=4, description="答案品質分數（1-4）")


class KnowledgeGapResponseDTO(BaseModel):
    id: int
    question_hash: str
    redacted_question: str
    agent_name: str
    trigger: str
    quality_score: float | None
    status: str
    occurrences: int
    created_at: datetime
    last_seen_at: datetime

    model_config = {"from_attributes": True}
