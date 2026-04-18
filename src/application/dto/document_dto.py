"""文件相關 DTO。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_serializer

from src.application.dto.common import TimestampMixin


class UploadResponseDTO(BaseModel):
    """文件上傳回應 DTO。"""

    filename: str
    doc_hash: str
    pages: int = Field(ge=0)
    chunks: int = Field(ge=0)
    stored: int = Field(ge=0)
    message: str = "文件已成功匯入知識庫"


class DeleteDocumentResponseDTO(BaseModel):
    """文件刪除回應 DTO。"""

    document_id: int
    filename: str
    doc_hash: str
    deleted_chunks: int
    message: str = "文件已從知識庫中刪除"


class ReingestResponseDTO(BaseModel):
    """文件重新匯入回應 DTO。"""

    document_id: int
    filename: str
    doc_hash: str
    pages: int = Field(ge=0)
    chunks: int = Field(ge=0)
    stored: int = Field(ge=0)
    deleted_chunks: int = Field(ge=0)
    message: str = "文件已重新匯入知識庫"


class DocumentListItemDTO(TimestampMixin):
    """文件列表項目 DTO。"""

    id: int
    filename: str
    doc_hash: str
    pages: int
    chunk_count: int
    uploaded_at: datetime

    model_config = {"from_attributes": True}

    @field_serializer("uploaded_at")
    def _ser_uploaded_at(self, v: datetime | None) -> str | None:
        return self._fmt(v)
