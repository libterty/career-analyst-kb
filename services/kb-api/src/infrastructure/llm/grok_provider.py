"""xAI Grok LLM Provider 實作（OpenAI 相容 API）。"""
from __future__ import annotations

from loguru import logger

from src.core.config import AppSettings
from src.core.interfaces.llm import ILLMProvider

_DEFAULT_LLM_MODEL = "grok-beta"
_DEFAULT_EMBED_MODEL = "text-embedding-3-large"

_EMBED_DIMS: dict[str, int] = {
    "text-embedding-3-large": 3072,
    "text-embedding-3-small": 1536,
    "text-embedding-ada-002": 1536,
}


class GrokProvider(ILLMProvider):
    """xAI Grok Provider（透過 OpenAI 相容 API）。

    Embedding 功能委派給 OpenAI（Grok 目前無原生 Embedding API）。
    """

    def __init__(self, settings: AppSettings) -> None:
        if not settings.grok_api_key:
            raise EnvironmentError("GROK_API_KEY is required when using grok provider")
        self._settings = settings

    def build_llm(
        self,
        model: str | None = None,
        temperature: float = 0.3,
        streaming: bool = True,
    ):
        from langchain_openai import ChatOpenAI

        m = model or self._settings.llm_model or _DEFAULT_LLM_MODEL
        logger.info(f"[GrokProvider] LLM model={m}")
        return ChatOpenAI(
            model=m,
            api_key=self._settings.grok_api_key,
            base_url="https://api.x.ai/v1",
            temperature=temperature,
            streaming=streaming,
        )

    def build_embedder(self, model: str | None = None):
        """Grok 無 Embedding API，委派給 OpenAI。"""
        from langchain_openai import OpenAIEmbeddings

        m = model or self._settings.embedding_model or _DEFAULT_EMBED_MODEL
        logger.info(f"[GrokProvider] Embedding delegated to OpenAI model={m}")
        return OpenAIEmbeddings(model=m)

    def get_embedding_dim(self, model: str | None = None) -> int:
        if self._settings.embedding_dim:
            return self._settings.embedding_dim
        m = model or self._settings.embedding_model or _DEFAULT_EMBED_MODEL
        return _EMBED_DIMS.get(m, 3072)
