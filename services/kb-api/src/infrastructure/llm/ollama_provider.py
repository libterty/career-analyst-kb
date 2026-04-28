"""Ollama LLM Provider 實作。"""
from __future__ import annotations

from loguru import logger

from src.core.config import AppSettings
from src.core.interfaces.llm import ILLMProvider

# 已知 Embedding 模型的向量維度對應表
_EMBED_DIMS: dict[str, int] = {
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
    "bge-m3": 1024,
    "bge-large-zh": 1024,
    "text-embedding-3-large": 3072,
    "text-embedding-3-small": 1536,
    "text-embedding-ada-002": 1536,
}

_DEFAULT_LLM_MODEL = "qwen3-30b-a3b"
_DEFAULT_EMBED_MODEL = "nomic-embed-text"


class OllamaProvider(ILLMProvider):
    """Ollama 本機 LLM Provider（不需要 API Key）。"""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def build_llm(
        self,
        model: str | None = None,
        temperature: float = 0.3,
        streaming: bool = True,
    ):
        from langchain_ollama import ChatOllama

        m = model or self._settings.llm_model or _DEFAULT_LLM_MODEL
        logger.info(f"[OllamaProvider] LLM model={m} base_url={self._settings.ollama_base_url}")
        return ChatOllama(
            model=m,
            base_url=self._settings.ollama_base_url,
            temperature=temperature,
        )

    def build_embedder(self, model: str | None = None):
        from langchain_ollama import OllamaEmbeddings

        m = model or self._settings.embedding_model or _DEFAULT_EMBED_MODEL
        logger.info(f"[OllamaProvider] Embeddings model={m}")
        return OllamaEmbeddings(model=m, base_url=self._settings.ollama_base_url)

    def get_embedding_dim(self, model: str | None = None) -> int:
        m = model or self._settings.embedding_model or _DEFAULT_EMBED_MODEL
        if self._settings.embedding_dim:
            return self._settings.embedding_dim
        dim = _EMBED_DIMS.get(m)
        if dim:
            return dim
        logger.warning(f"[OllamaProvider] Unknown embedding model '{m}', falling back to 768.")
        return 768
