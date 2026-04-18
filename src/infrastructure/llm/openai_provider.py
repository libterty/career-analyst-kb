"""OpenAI LLM Provider 實作。"""
from __future__ import annotations

from loguru import logger

from src.core.config import AppSettings
from src.core.interfaces.llm import ILLMProvider

_DEFAULT_LLM_MODEL = "gpt-4o"
_DEFAULT_EMBED_MODEL = "text-embedding-3-large"

_EMBED_DIMS: dict[str, int] = {
    "text-embedding-3-large": 3072,
    "text-embedding-3-small": 1536,
    "text-embedding-ada-002": 1536,
}


class OpenAIProvider(ILLMProvider):
    """OpenAI LLM & Embedding Provider。"""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def build_llm(
        self,
        model: str | None = None,
        temperature: float = 0.3,
        streaming: bool = True,
    ):
        from langchain_openai import ChatOpenAI

        m = model or self._settings.llm_model or _DEFAULT_LLM_MODEL
        logger.info(f"[OpenAIProvider] LLM model={m}")
        return ChatOpenAI(model=m, temperature=temperature, streaming=streaming)

    def build_embedder(self, model: str | None = None):
        from langchain_openai import OpenAIEmbeddings

        m = model or self._settings.embedding_model or _DEFAULT_EMBED_MODEL
        logger.info(f"[OpenAIProvider] Embeddings model={m}")
        return OpenAIEmbeddings(model=m)

    def get_embedding_dim(self, model: str | None = None) -> int:
        if self._settings.embedding_dim:
            return self._settings.embedding_dim
        m = model or self._settings.embedding_model or _DEFAULT_EMBED_MODEL
        return _EMBED_DIMS.get(m, 3072)
