"""FastAPI 依賴注入設定（Dependency Inversion Principle）。

所有 Service 與 Repository 的建立都集中在此，
Router 只透過 Depends() 取得所需的 Service，
不直接引入任何具體的 infrastructure 實作。

好處：
    - 測試時可用 app.dependency_overrides 替換為 Mock
    - 新增 Provider 只需修改 registry 建立，不觸碰 router
"""
from __future__ import annotations

from functools import lru_cache
from typing import Annotated, AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.services.admin_service import AdminService
from src.application.services.auth_service import AuthService
from src.application.services.chat_service import ChatService
from src.application.services.ingestion_service import IngestionService
from src.application.services.session_service import SessionService
from src.core.config import AppSettings, get_settings
from src.infrastructure.llm.grok_provider import GrokProvider
from src.infrastructure.llm.ollama_provider import OllamaProvider
from src.infrastructure.llm.openai_provider import OpenAIProvider
from src.infrastructure.llm.registry import LLMProviderRegistry
from src.infrastructure.persistence.database import AsyncSessionLocal
from src.infrastructure.repositories.chat_session_repository import SQLAlchemyChatSessionRepository
from src.infrastructure.repositories.document_repository import SQLAlchemyDocumentRepository
from src.infrastructure.repositories.user_repository import SQLAlchemyUserRepository


# ── 資料庫 Session ─────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """提供資料庫 Session，請求結束後自動關閉。"""
    async with AsyncSessionLocal() as session:
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]


# ── LLM Provider Registry（Singleton）────────────────────────────────

@lru_cache
def get_llm_registry() -> LLMProviderRegistry:
    """建立並快取 LLM Provider Registry（程序啟動時執行一次）。"""
    settings = get_settings()
    registry = LLMProviderRegistry()
    registry.register("ollama", OllamaProvider(settings))
    registry.register("openai", OpenAIProvider(settings))
    if settings.grok_api_key:
        registry.register("grok", GrokProvider(settings))
    return registry


# ── Repository（每 request 建立，依賴 Session）────────────────────────

async def get_user_repo(
    db: DbDep,
) -> SQLAlchemyUserRepository:
    return SQLAlchemyUserRepository(db)


async def get_document_repo(
    db: DbDep,
) -> SQLAlchemyDocumentRepository:
    return SQLAlchemyDocumentRepository(db)


async def get_chat_session_repo(
    db: DbDep,
) -> SQLAlchemyChatSessionRepository:
    """每 request 建立 ChatSession Repository（依賴 Session）。"""
    return SQLAlchemyChatSessionRepository(db)


# ── Auth Service（每 request 建立）────────────────────────────────────

async def get_auth_service(
    user_repo: Annotated[SQLAlchemyUserRepository, Depends(get_user_repo)],
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> AuthService:
    return AuthService(
        user_repo=user_repo,
        secret_key=settings.secret_key,
        algorithm=settings.algorithm,
        expire_minutes=settings.access_token_expire_minutes,
    )


async def get_admin_service(
    user_repo: Annotated[SQLAlchemyUserRepository, Depends(get_user_repo)],
) -> AdminService:
    """建立 AdminService（每 request）。"""
    return AdminService(user_repo=user_repo)


async def get_session_service(
    session_repo: Annotated[SQLAlchemyChatSessionRepository, Depends(get_chat_session_repo)],
    settings: Annotated[AppSettings, Depends(get_settings)],
) -> SessionService:
    """建立 SessionService（每 request）。"""
    return SessionService(
        session_repo=session_repo,
        max_messages_per_session=settings.max_messages_per_session,
        max_sessions_per_user=settings.max_sessions_per_user,
    )


# ── Chat Service（Singleton：初始化 LLM/Milvus 連線較昂貴）──────────

_chat_service: ChatService | None = None


def get_chat_service() -> ChatService:
    """建立或回傳快取的 ChatService 實例。

    採用模組層級 singleton 而非 @lru_cache，
    是為了在測試時可透過 dependency_overrides 替換。
    """
    global _chat_service
    if _chat_service is None:
        _chat_service = _build_chat_service()
    return _chat_service


def _build_chat_service() -> ChatService:
    """實際建立 ChatService 及其所有依賴。"""
    from src.ingestion.embedder import EmbeddingService
    from src.rag.hybrid_search import HybridSearchEngine
    from src.rag.retriever import MilvusRetriever
    from src.finetuning.prompt_optimizer import PromptOptimizer
    from src.security.guardrail import SecurityGuardrail

    settings = get_settings()
    registry = get_llm_registry()
    provider = registry.get(settings.llm_provider)

    host = settings.milvus_host
    port = settings.milvus_port

    retriever = MilvusRetriever(host=host, port=port)
    embedder = EmbeddingService(milvus_host=host, milvus_port=port)
    search_engine = HybridSearchEngine(retriever, dense_top_k=50, final_top_k=8, bm25_top_k=25)
    guardrail = SecurityGuardrail()
    query_enhancer = PromptOptimizer()
    llm = provider.build_llm(temperature=0.3, streaming=True)

    service = ChatService(
        input_validator=guardrail,
        output_sanitizer=guardrail,
        query_enhancer=query_enhancer,
        search_engine=search_engine,
        llm=llm,
        embed_query_fn=embedder.embed_query,
        db_session_factory=AsyncSessionLocal,
        max_messages_per_session=settings.max_messages_per_session,
    )

    # 若設定啟用語意快取，注入快取服務
    if settings.semantic_cache_enabled:
        from src.application.services.semantic_cache_service import SemanticCacheService
        from src.core.llm_factory import get_embedding_dim
        cache = SemanticCacheService(
            db_session_factory=AsyncSessionLocal,
            embed_query_fn=embedder.embed_query,
            milvus_host=host,
            milvus_port=port,
            embedding_dim=get_embedding_dim(),
            similarity_threshold=settings.semantic_cache_threshold,
            ttl_hours=settings.semantic_cache_ttl_hours,
        )
        service.set_semantic_cache(cache)

    return service


# ── Ingestion Service（Singleton）─────────────────────────────────────

_ingestion_service_cache: dict[int, IngestionService] = {}


async def get_ingestion_service(
    document_repo: Annotated[SQLAlchemyDocumentRepository, Depends(get_document_repo)],
) -> IngestionService:
    """建立 IngestionService（Milvus 連線部分共用，DB repo 每 request 新建）。"""
    from src.ingestion.chunker import SmartChunker
    from src.ingestion.embedder import EmbeddingService
    from src.ingestion.pdf_parser import DocumentParser
    from src.infrastructure.repositories.vector_repository import MilvusVectorRepository

    settings = get_settings()
    host = settings.milvus_host
    port = settings.milvus_port

    embedder_svc = EmbeddingService(milvus_host=host, milvus_port=port)
    vector_repo = MilvusVectorRepository(embedder_svc._collection)

    return IngestionService(
        parser=DocumentParser(),
        chunker=SmartChunker(max_tokens=512, chunk_overlap=64),
        embedder=embedder_svc._embedder,
        vector_repo=vector_repo,
        document_repo=document_repo,
    )
