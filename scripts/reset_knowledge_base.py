#!/usr/bin/env python3
"""清空知識庫中已匯入的所有文件典籍。

操作範圍：
  1. 刪除 Milvus collection（向量索引全清）
  2. 清空 PostgreSQL documents 表（文件 metadata）
  3. 可選：同時清空 chat_messages / chat_sessions

使用時機：
  - 重新匯入所有文件（切塊策略或 Embedding 模型有更動時）
  - 清除測試資料，回到乾淨狀態
  - CI/CD 測試環境的初始化

⚠️  警告：此操作不可復原，執行前請確認已備份或確認要清空。

Usage:
    # 互動確認模式（預設，會詢問是否確定）
    python scripts/reset_knowledge_base.py

    # 靜默模式（跳過確認，用於 CI/自動化腳本）
    python scripts/reset_knowledge_base.py --yes

    # 只清 Milvus 向量，保留 PostgreSQL 文件紀錄
    python scripts/reset_knowledge_base.py --vectors-only

    # 只清 PostgreSQL documents 表，保留向量（不建議，會造成資料不一致）
    python scripts/reset_knowledge_base.py --db-only

    # 同時清空對話紀錄（chat_messages / chat_sessions）
    python scripts/reset_knowledge_base.py --include-chat-history
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

# 將專案根目錄加入 Python 路徑
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()  # 載入 MILVUS_HOST、DATABASE_URL 等環境變數


# ── Milvus 清空函式 ────────────────────────────────────────────────────

def reset_milvus(host: str, port: int, collection_name: str) -> None:
    """刪除指定的 Milvus Collection（向量索引全清）。

    Args:
        host:            Milvus 主機位址
        port:            Milvus 連接埠
        collection_name: 要刪除的 Collection 名稱

    注意：drop_collection 會同時刪除索引與所有向量資料，無法復原。
    """
    from pymilvus import connections, utility

    connections.connect("default", host=host, port=port)

    if utility.has_collection(collection_name):
        utility.drop_collection(collection_name)
        print(f"  ✓ Milvus collection 已刪除：{collection_name}")
    else:
        # Collection 不存在時不報錯，只提示已是空的狀態
        print(f"  ℹ  Milvus collection 不存在（已是空的）：{collection_name}")


# ── PostgreSQL 清空函式 ────────────────────────────────────────────────

async def reset_postgres(database_url: str, include_chat: bool) -> None:
    """清空 PostgreSQL 中的文件 metadata（及可選的對話紀錄）。

    Args:
        database_url:  PostgreSQL 連線字串（asyncpg 格式）
        include_chat:  是否同時清空 chat_messages / chat_sessions 表

    注意：使用 DELETE（非 TRUNCATE）以保留資料表結構，只清除資料列。
    """
    import sqlalchemy as sa
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(database_url)
    async with engine.begin() as conn:
        # 清空文件 metadata 表（匯入紀錄）
        result = await conn.execute(sa.text("DELETE FROM documents"))
        print(f"  ✓ documents 表已清空（刪除 {result.rowcount} 筆）")

        if include_chat:
            # 先刪 chat_messages（有 FK 到 chat_sessions），再刪 sessions
            await conn.execute(sa.text("DELETE FROM chat_messages"))
            await conn.execute(sa.text("DELETE FROM chat_sessions"))
            print("  ✓ chat_messages / chat_sessions 已清空")

    await engine.dispose()  # 關閉連線池，釋放資源


# ── 互動確認 ──────────────────────────────────────────────────────────

def confirm(prompt: str) -> bool:
    """顯示提示並等待使用者輸入 y/N 確認。"""
    ans = input(f"{prompt} [y/N] ").strip().lower()
    return ans == "y"


# ── 主程式 ────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="清空職涯分析師知識庫")
    parser.add_argument("--yes", "-y", action="store_true", help="跳過確認，直接執行（CI 用）")
    parser.add_argument("--vectors-only", action="store_true", help="只清 Milvus 向量，保留 PostgreSQL 紀錄")
    parser.add_argument("--db-only", action="store_true", help="只清 PostgreSQL documents 表，保留向量")
    parser.add_argument("--include-chat-history", action="store_true", help="同時清空對話紀錄")
    # Milvus 連線設定（優先讀取環境變數，可在 .env 中設定）
    parser.add_argument("--milvus-host", default=os.getenv("MILVUS_HOST", "localhost"))
    parser.add_argument("--milvus-port", type=int, default=int(os.getenv("MILVUS_PORT", "19530")))
    parser.add_argument(
        "--collection",
        default=os.getenv("MILVUS_COLLECTION", "career_kb"),
        help="Milvus Collection 名稱",
    )
    args = parser.parse_args()

    # 從環境變數取得 PostgreSQL 連線字串
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://career:secret@localhost:5432/career_kb",
    )

    # ── 顯示操作摘要，讓使用者清楚即將執行的操作 ──
    print("\n⚠️  即將執行以下清空操作：")
    if not args.db_only:
        print(f"  • Milvus collection '{args.collection}' @ {args.milvus_host}:{args.milvus_port}")
    if not args.vectors_only:
        # 隱藏密碼，只顯示 @ 後的主機資訊
        print(f"  • PostgreSQL documents 表 @ {database_url.split('@')[-1]}")
        if args.include_chat_history:
            print("  • PostgreSQL chat_messages / chat_sessions 表")
    print()

    # ── 互動確認（除非帶 --yes 跳過）──
    if not args.yes:
        if not confirm("確定要清空知識庫嗎？此操作無法復原。"):
            print("已取消。")
            sys.exit(0)

    # ── 執行清空操作 ──
    if not args.db_only:
        print("\n[1/2] 清空 Milvus 向量...")
        try:
            reset_milvus(args.milvus_host, args.milvus_port, args.collection)
        except Exception as e:
            print(f"  ✗ Milvus 清空失敗：{e}")

    if not args.vectors_only:
        print("\n[2/2] 清空 PostgreSQL...")
        try:
            asyncio.run(reset_postgres(database_url, args.include_chat_history))
        except Exception as e:
            print(f"  ✗ PostgreSQL 清空失敗：{e}")

    # ── 完成提示，告知下一步 ──
    print("\n✅ 知識庫已清空。重新匯入文件：")
    print("   python scripts/ingest_documents.py --path data/raw/\n")


if __name__ == "__main__":
    main()
