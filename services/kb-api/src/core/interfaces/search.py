"""搜索引擎介面（支援 Strategy Pattern）。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.domain.search_result import SearchResult


class ISearchEngine(ABC):
    """搜索引擎策略介面。

    HybridSearchEngine 是具體實作，未來可替換為其他搜索策略
    （如純向量搜索、全文搜索等），不需修改呼叫端。
    """

    @abstractmethod
    def search(
        self,
        query: str,
        query_embedding: list[float],
        topic: str | None = None,
    ) -> list["SearchResult"]:
        """執行搜索並回傳排序後的結果列表。topic 可選，篩選指定類別。"""
