"""查詢強化介面。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class IQueryEnhancer(ABC):
    """查詢強化策略介面。

    PromptOptimizer 實作此介面。
    未來可替換為更複雜的查詢重寫策略。
    """

    @abstractmethod
    def enhance_query(self, query: str) -> str:
        """將術語別名正規化、強化查詢語意。"""

    @abstractmethod
    def build_glossary_context(self, query: str) -> str:
        """依查詢內容注入相關術語定義，豐富 System Prompt。"""
