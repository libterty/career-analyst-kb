"""共用型別與工具函式，供各 model 檔案使用。"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import TIMESTAMP

# 毫秒精度、帶時區的 timestamp 型別（對應 PostgreSQL TIMESTAMP(3) WITH TIME ZONE）
TS = TIMESTAMP(precision=3, timezone=True)


def now() -> datetime:
    """回傳當前 UTC 時間（timezone-aware）。"""
    return datetime.now(timezone.utc)
