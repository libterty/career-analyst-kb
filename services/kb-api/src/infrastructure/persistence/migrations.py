"""應用程式啟動時執行 Alembic migration。

此模組封裝 alembic upgrade head 邏輯，讓 FastAPI lifespan 可以呼叫。
Migration 檔案位於 /migrations/versions/。
"""
from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from loguru import logger


def run_migrations() -> None:
    """執行所有待執行的 Alembic migration（等同 `alembic upgrade head`）。

    - 若資料庫已是最新版本，此函式不做任何事。
    - 若有新的 migration，會自動套用。
    """
    # backend service root 位於 services/kb-api（此檔在 src/infrastructure/persistence/）
    project_root = Path(__file__).resolve().parents[3]
    alembic_ini = project_root / "alembic.ini"
    migrations_dir = project_root / "migrations"

    alembic_cfg = Config(str(alembic_ini))
    alembic_cfg.set_main_option("script_location", str(migrations_dir))

    logger.info("Running Alembic migrations...")
    command.upgrade(alembic_cfg, "head")
    logger.success("Alembic migrations complete")
