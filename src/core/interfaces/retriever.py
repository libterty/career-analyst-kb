"""向量搜索介面（Interface Segregation）。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.domain.search_result import SearchResult


class IVectorRetriever(ABC):
    """向量搜索介面。

    MilvusRetriever 等具體實作依賴此介面，
    HybridSearchEngine 透過此介面取得向量搜索結果。
    """

    @abstractmethod
    def search(
        self, query_embedding: list[float], top_k: int = 10
    ) -> list["SearchResult"]:
        """以向量查詢 top_k 筆最相似的段落。"""
