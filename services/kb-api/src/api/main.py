"""Phase 5 — FastAPI Application Entry Point"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.api.auth import hash_password
from src.core.config import get_settings
from src.infrastructure.persistence.database import AsyncSessionLocal
from src.infrastructure.persistence.migrations import run_migrations
from src.infrastructure.repositories.user_repository import SQLAlchemyUserRepository
from .routers import admin, auth, chat, documents, ingestion, sessions, feedback, system_prompts

REPO_ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "frontend").is_dir()),
    Path(__file__).resolve().parents[2],
)

# ---- Rate Limiter -------------------------------------------------- #
# 依來源 IP 進行請求頻率限制，防止濫用
limiter = Limiter(key_func=get_remote_address)


# ---- App Lifespan -------------------------------------------------- #

@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用程式生命週期管理。

    啟動時：建立資料庫資料表（若不存在）
    關閉時：執行清理工作
    """
    settings = get_settings()
    logger.info("🚀 Starting Career Analyst KB...")
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

    yield
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


# ---- Health Check -------------------------------------------------- #
# Must be registered before the StaticFiles("/") mount, which shadows any
# route defined after it.

@app.get("/health", tags=["System"])
async def health():
    """健康檢查端點，供 Docker / K8s 探針使用。"""
    return {"status": "ok", "version": "1.0.0"}


# 掛載前端靜態檔案（若前端目錄存在）
frontend_path = REPO_ROOT / "frontend"
if frontend_path.is_dir():
    # /admin 明確路由（StaticFiles 不會自動對應 admin.html）
    @app.get("/admin", include_in_schema=False)
    async def admin_page():
        from fastapi.responses import FileResponse
        return FileResponse(frontend_path / "admin.html")

    app.mount("/", StaticFiles(directory=str(frontend_path), html=True), name="static")


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
