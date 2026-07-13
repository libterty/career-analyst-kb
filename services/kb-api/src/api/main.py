"""Phase 5 — FastAPI Application Entry Point"""
from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from prometheus_fastapi_instrumentator import Instrumentator

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from src.api.auth import hash_password
from src.api.limiter import limiter
from src.api.middleware import CorrelationIdMiddleware
from src.core.config import get_settings
from src.core.tracing import langfuse_client
from src.infrastructure.persistence.database import AsyncSessionLocal
from src.infrastructure.persistence.migrations import run_migrations
from src.infrastructure.repositories.user_repository import SQLAlchemyUserRepository
from .routers import admin, auth, chat, documents, ingestion, sessions, feedback, system_prompts, knowledge_gaps, hill_climbing


# ---- App Lifespan -------------------------------------------------- #

@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用程式生命週期管理。

    啟動時：建立資料庫資料表（若不存在）
    關閉時：執行清理工作
    """
    settings = get_settings()
    logger.info("🚀 Starting Career Analyst KB...")

    # Warn if CORS still allows localhost in production
    if settings.app_env == "production":
        localhost_origins = [o.strip() for o in settings.cors_origins.split(",") if "localhost" in o]
        if localhost_origins:
            logger.warning(
                f"⚠️  CORS: production env allows localhost origins {localhost_origins}. "
                "Set CORS_ORIGINS to the production frontend URL."
            )

    # Guard: reject the dev placeholder secret key in non-development environments
    _DEV_SECRET = "CHANGE_ME_IN_PRODUCTION_USE_RANDOM_32_CHARS"
    if settings.secret_key == _DEV_SECRET and settings.app_env != "development":
        raise RuntimeError(
            "SECRET_KEY is still set to the development placeholder. "
            "Set the SECRET_KEY environment variable to a random 32+ character string before running in production."
        )

    if not settings.admin_password:
        logger.warning("⚠️  ADMIN_PASSWORD not set — no admin account will be created on first boot")

    run_migrations()  # 執行 Alembic migration（自動套用所有待執行的版本）
    logger.success("✅ Database migrations applied")

    # 若 ADMIN_PASSWORD 已設定且目前沒有任何 admin，自動建立初始管理員帳號
    if settings.admin_password:
        async with AsyncSessionLocal() as db:
            repo = SQLAlchemyUserRepository(db)
            admin_count = await repo.count_by_role("admin")
            if admin_count == 0:
                hashed = hash_password(settings.admin_password)
                await repo.create(settings.admin_username, hashed, "admin")
                logger.success(
                    f"✅ 初始管理員帳號已建立：{settings.admin_username}"
                )

    # Eagerly initialize Langfuse singleton so @observe decorators can flush spans.
    # Without this call the singleton is never created and all @observe spans are no-ops.
    lf = langfuse_client()
    if lf:
        logger.success("✅ Langfuse tracing initialised")
    else:
        logger.info("ℹ️  Langfuse not configured — tracing disabled")

    # Eager-load BM25 index so the first user request isn't blocked by corpus fetch.
    try:
        from src.api.dependencies import get_chat_service
        svc = get_chat_service()
        await asyncio.get_running_loop().run_in_executor(
            None, svc._search_engine._ensure_bm25_index
        )
        logger.success("✅ BM25 index pre-loaded")
    except Exception as exc:
        logger.warning(f"⚠️  BM25 index pre-load failed (will retry on first query): {exc}")

    yield
    if lf:
        lf.flush()
    logger.info("🛑 Shutting down...")


# ---- Application --------------------------------------------------- #

app = FastAPI(
    title="Career Analyst KB",
    description="基於 RAG 架構的職涯分析師知識庫系統",
    version="1.0.0",
    lifespan=lifespan,
    # 正式環境關閉 Swagger UI（/docs），避免暴露 API 文件
    docs_url="/docs" if os.getenv("APP_ENV") != "production" else None,
)

# 掛載速率限制器與例外處理器
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Correlation ID — must be added before CORS so the response header is always present
app.add_middleware(CorrelationIdMiddleware)

# CORS 設定：允許的前端來源（多個來源用逗號分隔）
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "PATCH"],
    allow_headers=["*"],
)

# Prometheus 指標暴露（監控用），路徑：/metrics
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# 掛載所有路由模組
app.include_router(auth.router)            # /api/auth/*
app.include_router(chat.router)            # /api/chat/*
app.include_router(documents.router)       # /api/documents/*
app.include_router(admin.router)           # /api/admin/*
app.include_router(sessions.router)        # /api/sessions/*
app.include_router(feedback.router)        # /api/feedback/*
app.include_router(system_prompts.router)  # /api/admin/system-prompts/*
app.include_router(ingestion.router)       # /api/ingestion/*
app.include_router(knowledge_gaps.router)  # /api/knowledge-gaps/*
app.include_router(hill_climbing.router)   # /api/admin/hill-climbing/*


# ---- Health Check -------------------------------------------------- #

@app.get("/health", tags=["System"])
async def health():
    """健康檢查端點，供 Docker / K8s 探針使用。"""
    return {"status": "ok", "version": "1.0.0"}


@app.get("/health/ready", tags=["System"])
async def health_ready():
    """Readiness probe：實際探測 Milvus 與 Ollama 是否可用。"""
    import httpx
    import pymilvus

    settings = get_settings()
    checks: dict[str, str] = {}

    try:
        pymilvus.connections.connect(
            host=settings.milvus_host, port=settings.milvus_port, timeout=3
        )
        pymilvus.utility.has_collection(settings.milvus_collection)
        checks["milvus"] = "ok"
    except Exception as exc:
        checks["milvus"] = f"error: {exc}"

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
        checks["ollama"] = "ok" if resp.status_code == 200 else f"http_{resp.status_code}"
    except Exception as exc:
        checks["ollama"] = f"error: {exc}"

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ready" if all_ok else "not_ready", "checks": checks},
    )


# ---- Global Error Handler ------------------------------------------ #

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全域例外處理器。

    捕捉所有未被個別路由處理的例外，
    記錄完整 stack trace 後回傳通用錯誤訊息給使用者（不洩漏內部細節）。
    """
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "系統發生內部錯誤，請聯絡管理員"},
    )
