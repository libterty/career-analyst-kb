"""LLM & Embedding Factory
支援三種 provider：
  - ollama  : 本機 Ollama（Gemma3、Gemma2 等）
  - grok    : xAI Grok（OpenAI 相容 API）
  - openai  : OpenAI（保留相容，作為 fallback）

環境變數：
  LLM_PROVIDER          ollama | grok | openai   (default: ollama)
  LLM_MODEL             模型名稱                  (default 依 provider)
  OLLAMA_BASE_URL       Ollama 服務位址           (default: http://localhost:11434)
  GROK_API_KEY          xAI API Key              (grok 模式必填)
  EMBEDDING_PROVIDER    ollama | openai           (default: 同 LLM_PROVIDER 若為 ollama，否則 openai)
  EMBEDDING_MODEL       Embedding 模型名稱
  EMBEDDING_DIM         向量維度整數              (default 依 model 自動推斷)
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Union

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel
from loguru import logger


# ── 各 provider 的預設模型名稱 ──────────────────────────────────────
_LLM_DEFAULTS = {
    "ollama": "gemma3:12b",
    "grok": "grok-beta",
    "openai": "gpt-4o",
}

_EMBED_DEFAULTS = {
    "ollama": "nomic-embed-text",
    "openai": "text-embedding-3-large",
}

# 已知 Embedding 模型的向量維度對應表
# 若使用的模型不在此表中，會 fallback 到 768 並發出警告
_EMBED_DIMS: dict[str, int] = {
    "nomic-embed-text": 768,
    "mxbai-embed-large": 1024,
    "bge-m3": 1024,
    "bge-large-zh": 1024,
    "text-embedding-3-large": 3072,
    "text-embedding-3-small": 1536,
    "text-embedding-ada-002": 1536,
}


def get_embedding_dim() -> int:
    """回傳目前設定的 Embedding 模型的向量維度。

    優先順序：
        1. EMBEDDING_DIM 環境變數（明確指定，最優先）
        2. 從 _EMBED_DIMS 查詢 EMBEDDING_MODEL 對應的維度
        3. 未知模型 fallback 到 768（並輸出警告）
    """
    # 明確設定的維度優先
    if explicit := os.getenv("EMBEDDING_DIM"):
        return int(explicit)

    model = os.getenv("EMBEDDING_MODEL", _EMBED_DEFAULTS.get(_embedding_provider(), "nomic-embed-text"))
    dim = _EMBED_DIMS.get(model)
    if dim:
        return dim

    # 未知模型，回傳安全預設值
    logger.warning(
        f"Unknown embedding model '{model}'. "
        "Set EMBEDDING_DIM explicitly. Falling back to 768."
    )
    return 768


def _llm_provider() -> str:
    """讀取 LLM_PROVIDER 環境變數，預設為 ollama。"""
    return os.getenv("LLM_PROVIDER", "ollama").lower()


def _embedding_provider() -> str:
    """讀取 EMBEDDING_PROVIDER 環境變數。

    若未設定，則跟隨 LLM_PROVIDER：
        - LLM_PROVIDER=ollama → Embedding 也用 ollama
        - 其他 LLM provider  → Embedding 用 openai
    """
    ep = os.getenv("EMBEDDING_PROVIDER", "").lower()
    if ep:
        return ep
    return "ollama" if _llm_provider() == "ollama" else "openai"


# ── LLM 建構函式 ──────────────────────────────────────────────────────

def build_llm(
    model: str | None = None,
    temperature: float = 0.3,
    streaming: bool = True,
) -> BaseLanguageModel:
    """依環境變數建立對應的 LLM 實例。

    Args:
        model:       模型名稱（None 表示使用環境變數或預設值）
        temperature: 生成溫度（0.0-1.0，越低越穩定）
        streaming:   是否啟用串流輸出

    Returns:
        LangChain 相容的 BaseLanguageModel 實例
    """
    provider = _llm_provider()
    model = model or os.getenv("LLM_MODEL", _LLM_DEFAULTS.get(provider, "gemma3:12b"))

    if provider == "ollama":
        return _build_ollama_llm(model, temperature, streaming)
    if provider == "grok":
        return _build_grok_llm(model, temperature, streaming)
    if provider == "openai":
        return _build_openai_llm(model, temperature, streaming)

    raise ValueError(f"Unknown LLM_PROVIDER: '{provider}'. Choose ollama | grok | openai")


def _build_ollama_llm(model: str, temperature: float, streaming: bool):
    """建立 Ollama 本機 LLM（不需要 API Key，在本機執行）。"""
    from langchain_ollama import ChatOllama

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    logger.info(f"[LLMFactory] Ollama LLM — model={model} base_url={base_url}")
    return ChatOllama(
        model=model,
        base_url=base_url,
        temperature=temperature,
        # Ollama 的串流透過 astream() 原生支援
    )


def _build_grok_llm(model: str, temperature: float, streaming: bool):
    """建立 xAI Grok LLM（使用 OpenAI 相容 API，需要 GROK_API_KEY）。"""
    from langchain_openai import ChatOpenAI

    api_key = os.getenv("GROK_API_KEY")
    if not api_key:
        raise EnvironmentError("GROK_API_KEY is required when LLM_PROVIDER=grok")

    logger.info(f"[LLMFactory] xAI Grok LLM — model={model}")
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url="https://api.x.ai/v1",  # xAI 的 OpenAI 相容端點
        temperature=temperature,
        streaming=streaming,
    )


def _build_openai_llm(model: str, temperature: float, streaming: bool):
    """建立 OpenAI LLM（需要 OPENAI_API_KEY 環境變數）。"""
    from langchain_openai import ChatOpenAI

    logger.info(f"[LLMFactory] OpenAI LLM — model={model}")
    return ChatOpenAI(model=model, temperature=temperature, streaming=streaming)


# ── Embedding 建構函式 ────────────────────────────────────────────────

def build_embedder(model: str | None = None) -> Embeddings:
    """依環境變數建立對應的 Embedding 模型實例。

    Args:
        model: Embedding 模型名稱（None 表示使用環境變數或預設值）

    Returns:
        LangChain 相容的 Embeddings 實例
    """
    provider = _embedding_provider()
    model = model or os.getenv(
        "EMBEDDING_MODEL", _EMBED_DEFAULTS.get(provider, "nomic-embed-text")
    )

    if provider == "ollama":
        return _build_ollama_embedder(model)
    if provider == "openai":
        return _build_openai_embedder(model)

    raise ValueError(f"Unknown EMBEDDING_PROVIDER: '{provider}'. Choose ollama | openai")


def _build_ollama_embedder(model: str) -> Embeddings:
    """建立 Ollama 本機 Embedding 模型（預設使用 nomic-embed-text，768 維）。"""
    from langchain_ollama import OllamaEmbeddings

    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    logger.info(f"[LLMFactory] Ollama Embeddings — model={model} base_url={base_url}")
    return OllamaEmbeddings(model=model, base_url=base_url)


def _build_openai_embedder(model: str) -> Embeddings:
    """建立 OpenAI Embedding 模型（需要 OPENAI_API_KEY 環境變數）。"""
    from langchain_openai import OpenAIEmbeddings

    logger.info(f"[LLMFactory] OpenAI Embeddings — model={model}")
    return OpenAIEmbeddings(model=model)
