"""Chunk 值物件。

從 src/ingestion/chunker.py 提取，作為共享的 Domain 物件，
避免 ingestion 與 rag 模組互相引入。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Chunk:
    """文字切塊值物件（不可變）。

    Attributes:
        chunk_id:    切塊唯一識別碼（doc_hash + 序號）
        doc_hash:    所屬文件的 SHA-256 指紋（前 16 碼）
        source:      來源文件名稱
        content:     切塊文字內容
        page_hint:   所在頁數（估算值，可為 None）
        section:     所屬章節名稱
        token_count: tiktoken 計算的 token 數量
        metadata:    其他擴充 metadata
    """

    chunk_id: str
    doc_hash: str
    source: str
    content: str
    page_hint: int | None = None
    section: str = ""
    token_count: int = 0
    metadata: dict = field(default_factory=dict)
    video_title: str = ""
    upload_date: str = ""
    url: str = ""
