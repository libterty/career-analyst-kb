"""SearchResult 值物件。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SearchResult:
    """搜索結果值物件（不可變）。

    Attributes:
        chunk_id:         切塊唯一識別碼
        content:          段落文字內容
        source:           來源文件名稱
        section:          所屬章節名稱
        score:            RRF 融合後的相似度分數
        page_number:      來源頁碼（1-based，None 表示不支援）
    """

    chunk_id: str
    content: str
    source: str
    section: str
    score: float
    page_number: int | None = None
