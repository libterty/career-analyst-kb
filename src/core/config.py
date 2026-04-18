"""集中管理所有環境變數設定（Pydantic Settings）。

取代各模組散落的 os.getenv() 呼叫，提供型別安全與啟動時快速失敗。

使用方式：
    from src.core.config import get_settings
    settings = get_settings()
    print(settings.llm_provider)
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """應用程式全域設定。

    所有欄位均可透過環境變數（或 .env 檔案）覆寫，
    欄位名稱即環境變數名稱（大寫不分）。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── LLM Provider ─────────────────────────────────────────────────
    llm_provider: str = "ollama"
    """LLM Provider: ollama | grok | openai"""

    llm_model: str | None = None
    """LLM 模型名稱（None 表示使用各 Provider 的預設模型）"""

    ollama_base_url: str = "http://localhost:11434"
    """Ollama 服務位址"""

    grok_api_key: str | None = None
    """xAI Grok API Key（llm_provider=grok 時必填）"""

    openai_api_key: str | None = None
    """OpenAI API Key（llm_provider=openai 時必填）"""

    # ── Embedding ─────────────────────────────────────────────────────
    embedding_provider: str | None = None
    """Embedding Provider（None 表示跟隨 llm_provider 邏輯）"""

    embedding_model: str | None = None
    """Embedding 模型名稱"""

    embedding_dim: int | None = None
    """向量維度（None 表示依模型自動推斷）"""

    # ── Milvus ────────────────────────────────────────────────────────
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_collection: str = "yiguandao_kb"

    # ── PostgreSQL ────────────────────────────────────────────────────
    database_url: str = (
        "postgresql+asyncpg://yiguandao:secret@localhost:5432/yiguandao_kb"
    )

    # ── Auth ──────────────────────────────────────────────────────────
    secret_key: str = "CHANGE_ME_IN_PRODUCTION_USE_RANDOM_32_CHARS"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # ── Sessions ──────────────────────────────────────────────────────
    max_messages_per_session: int = 100
    """每個對話 Session 最多允許的訊息數量"""

    max_sessions_per_user: int = 20
    """每位使用者最多可建立的 Session 數量（管理員可在後台調整）"""

    # ── Admin Seed ────────────────────────────────────────────────────
    admin_username: str = "admin"
    """預設管理員帳號名稱（首次啟動時自動建立）"""

    admin_password: str | None = None
    """預設管理員密碼（設定後啟動時自動建立管理員帳號）"""

    # ── Semantic Cache ────────────────────────────────────────────────
    semantic_cache_enabled: bool = False
    """是否啟用語意快取（相似問題直接回傳快取答案，降低 LLM 推論成本）"""

    semantic_cache_threshold: float = 0.95
    """語意快取命中的相似度門檻（0-1，越高越嚴格）"""

    semantic_cache_ttl_hours: int = 24
    """語意快取條目的存活時間（小時）"""

    # ── App ───────────────────────────────────────────────────────────
    app_env: str = "development"
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> AppSettings:
    """回傳快取的 AppSettings 實例（整個程序共用）。"""
    return AppSettings()
