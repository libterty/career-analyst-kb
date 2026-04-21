#!/usr/bin/env python3
"""CLI 工具：將文件匯入職涯分析師知識庫。

此腳本是文件匯入的命令列入口，會依序執行：
  解析文件 → 切塊 → 向量化 → 寫入 Milvus

Usage:
    # 匯入整個目錄（批次處理）
    python scripts/ingest_documents.py --path data/raw/

    # 匯入單一文件
    python scripts/ingest_documents.py --file data/raw/经典.pdf

    # 指定自訂 Milvus 位址
    python scripts/ingest_documents.py --path data/raw/ --milvus-host 192.168.1.100 --milvus-port 19530
"""
import argparse
import os
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]

# 將 backend service 根目錄加入 Python 路徑，讓 scripts/ 目錄下能 import src/
sys.path.insert(0, str(SERVICE_ROOT))

from dotenv import load_dotenv
load_dotenv(REPO_ROOT / ".env")  # 載入 repo root .env（MILVUS_HOST、EMBEDDING_PROVIDER 等）

from loguru import logger
from src.ingestion.pipeline import IngestionPipeline


def main():
    parser = argparse.ArgumentParser(description="職涯分析師知識庫 — 文件匯入工具")
    # --path 與 --file 互斥，至少提供一個
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--path", help="批次匯入目錄（匯入目錄下所有 PDF/DOCX）")
    group.add_argument("--file", help="匯入單一文件")
    parser.add_argument("--milvus-host", default=os.getenv("MILVUS_HOST", "localhost"), help="Milvus 主機位址")
    parser.add_argument("--milvus-port", type=int, default=int(os.getenv("MILVUS_PORT", "19530")), help="Milvus 連接埠")
    parser.add_argument("--reingest", action="store_true", help="重新匯入：先刪除舊向量再匯入（適用於文件已更新的情況）")
    args = parser.parse_args()

    # 初始化匯入管線（會連線 Milvus 並建立 Collection）
    pipeline = IngestionPipeline(
        milvus_host=args.milvus_host,
        milvus_port=args.milvus_port,
    )

    if args.file:
        if args.reingest:
            result = pipeline.reingest_file(args.file)
            if result["skipped"]:
                logger.info(f"Skipped (unchanged): {result['filename']}")
                print(f"  — {result['filename']} (unchanged, skipped)")
            else:
                logger.success(f"Re-ingested: {result}")
                print(f"  deleted {result['deleted']} old chunks, stored {result['stored']} new chunks")
        else:
            result = pipeline.ingest_file(args.file)
            logger.success(f"Ingested: {result}")
    else:
        if args.reingest:
            results = pipeline.reingest_directory(args.path)
            updated = [r for r in results if not r["skipped"]]
            skipped = [r for r in results if r["skipped"]]
            logger.success(f"Re-ingested {len(updated)} updated, {len(skipped)} unchanged (skipped)")
            for r in results:
                if r["skipped"]:
                    print(f"  — {r['filename']} (unchanged, skipped)")
                else:
                    print(f"  ✓ {r['filename']} — deleted {r['deleted']} old, stored {r['stored']} new chunks")
        else:
            results = pipeline.ingest_directory(args.path)
            logger.success(f"Ingested {len(results)} documents")
            for r in results:
                print(f"  ✓ {r['filename']} — {r['chunks']} chunks")


if __name__ == "__main__":
    main()
