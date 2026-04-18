"""LLM & Embedding Provider 抽象介面（Strategy Pattern）。

新增 Provider 時只需：
    1. 實作 ILLMProvider
    2. 向 LLMProviderRegistry 註冊

不需修改任何現有程式碼（Open/Closed Principle）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from langchain.schema.embeddings import Embeddings
    from langchain.schema.language_model import BaseLanguageModel


class ILLMProvider(ABC):
    """LLM Provider 策略介面。

    每個 provider（Ollama、Grok、OpenAI）都是此介面的具體策略實作。
    使用 TYPE_CHECKING 延遲引入 langchain，避免在測試環境未安裝時失敗。
    """

    @abstractmethod
    def build_llm(
        self,
        model: str | None = None,
        temperature: float = 0.3,
        streaming: bool = True,
    ) -> "BaseLanguageModel":
        """建立 LangChain 相容的 LLM 實例。"""

    @abstractmethod
    def build_embedder(self, model: str | None = None) -> "Embeddings":
        """建立 LangChain 相容的 Embeddings 實例。"""

    @abstractmethod
    def get_embedding_dim(self, model: str | None = None) -> int:
        """回傳指定 Embedding 模型的向量維度。"""
