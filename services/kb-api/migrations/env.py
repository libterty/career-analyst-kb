"""Alembic 環境設定。

Alembic 本身是同步工具，使用 psycopg2（同步驅動）執行 migration。
應用程式 runtime 則繼續使用 asyncpg（非同步），兩者互不干擾。
"""
from __future__ import annotations

import os
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import create_engine, pool

from alembic import context

# ── 載入所有 ORM models（autogenerate 需要） ─────────────────────────
from src.infrastructure.persistence.database import Base  # noqa: F401
import src.infrastructure.persistence.models  # noqa: F401  確保 models 已註冊到 Base.metadata

# ────────────────────────────────────────────────────────────────────
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
ROOT_ENV_FILE = next(
    (p / ".env" for p in Path(__file__).resolve().parents if (p / ".env").is_file()),
    Path(__file__).resolve().parents[1] / ".env",
)


def _get_sync_url() -> str:
    """從環境變數取得 DATABASE_URL，轉換成 psycopg2（同步）driver。"""
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        try:
            from dotenv import load_dotenv
            load_dotenv(ROOT_ENV_FILE)
            url = os.environ.get("DATABASE_URL", "")
        except ImportError:
            pass
    if not url:
        raise RuntimeError("DATABASE_URL 環境變數未設定")
    # 統一轉成 psycopg2 同步 driver 供 alembic 使用
    url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://")
    url = url.replace("postgresql://", "postgresql+psycopg2://")
    url = url.replace("postgres://", "postgresql+psycopg2://")
    return url


def run_migrations_offline() -> None:
    """Offline 模式：只產生 SQL，不實際連線。"""
    context.configure(
        url=_get_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Online 模式：使用同步 psycopg2 連線並執行 migration。"""
    engine = create_engine(_get_sync_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
