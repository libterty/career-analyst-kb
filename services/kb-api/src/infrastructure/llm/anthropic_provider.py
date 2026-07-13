"""Anthropic Claude LLM Provider 實作。"""
from __future__ import annotations

from loguru import logger

from src.core.config import AppSettings
from src.core.interfaces.llm import ILLMProvider

_DEFAULT_LLM_MODEL = "claude-haiku-4-5-20251001"


class AnthropicProvider(ILLMProvider):
    """Anthropic Claude LLM Provider（cloud fallback）。"""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def build_llm(
        self,
        model: str | None = None,
        temperature: float = 0.3,
        streaming: bool = True,
    ):
        from langchain_anthropic import ChatAnthropic

        m = model or self._settings.llm_model or _DEFAULT_LLM_MODEL
        logger.info(f"[AnthropicProvider] LLM model={m}")
        return ChatAnthropic(  # type: ignore[call-arg]
            model_name=m,
            temperature=temperature,
            streaming=streaming,
        )

    def build_embedder(self, model: str | None = None):
        # Anthropic 沒有 embedding API，fallback 到 Ollama nomic-embed-text
        from langchain_ollama import OllamaEmbeddings

        ollama_url = self._settings.ollama_base_url
        embed_model = self._settings.embedding_model or "nomic-embed-text"
        logger.info(
            f"[AnthropicProvider] Embeddings fallback to Ollama model={embed_model}"
        )
        return OllamaEmbeddings(model=embed_model, base_url=ollama_url)

    def get_embedding_dim(self, model: str | None = None) -> int:
        if self._settings.embedding_dim:
            return self._settings.embedding_dim
        return 768  # nomic-embed-text default
