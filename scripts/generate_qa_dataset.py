#!/usr/bin/env python3
"""CLI 工具：從典籍文件自動生成 QA 訓練資料集。

此腳本讀取 PDF/DOCX 文件，切割為切塊後，
對每個切塊呼叫 LLM 生成問答對，輸出為 JSON 格式。

生成的 QA 資料集用途：
  1. Fine-tuning：微調 LLM，提升一貫道問答的準確度與語氣
  2. Evaluation：評測 RAG 系統的召回率（Ground Truth 比對）

Usage:
    # 基本用法
    python scripts/generate_qa_dataset.py --file data/raw/经典.pdf --output data/processed/qa_dataset.json

    # 自訂每個切塊生成的 QA 對數（預設 3 對）
    python scripts/generate_qa_dataset.py --file data/raw/经典.pdf --pairs-per-chunk 5
"""
import argparse
import os
import sys
from pathlib import Path

# 將專案根目錄加入 Python 路徑
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv()  # 載入 LLM_PROVIDER、LLM_MODEL 等環境變數

from src.ingestion.chunker import SmartChunker
from src.ingestion.pdf_parser import DocumentParser
from src.finetuning.qa_generator import QADatasetGenerator


SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".pptx", ".png", ".jpg", ".jpeg"}


def main():
    parser = argparse.ArgumentParser(description="QA 資料集生成工具")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="來源單一文件路徑（PDF/DOCX/PPTX）")
    group.add_argument("--path", help="批次模式：掃描目錄下所有支援格式的文件")
    parser.add_argument(
        "--output",
        default="data/processed/qa_dataset.json",
        help="輸出 JSON 檔案路徑（預設: data/processed/qa_dataset.json）",
    )
    parser.add_argument(
        "--pairs-per-chunk",
        type=int,
        default=3,
        help="每個切塊生成的 QA 對數量（預設: 3）",
    )
    args = parser.parse_args()

    # 收集要處理的檔案清單
    if args.file:
        files = [Path(args.file)]
    else:
        base = Path(args.path)
        files = [f for f in sorted(base.iterdir()) if f.suffix.lower() in SUPPORTED_EXTENSIONS]
        if not files:
            print(f"No supported files found in {args.path}")
            sys.exit(1)
        print(f"Found {len(files)} files in {args.path}")

    doc_parser = DocumentParser()
    chunker = SmartChunker(max_tokens=512)
    qa_gen = QADatasetGenerator()

    all_pairs = []
    for f in files:
        print(f"\n[{files.index(f)+1}/{len(files)}] Processing {f.name} ...")
        try:
            doc = doc_parser.parse(str(f))
            chunks = chunker.chunk(doc)
            print(f"  → {len(chunks)} chunks")
            pairs = qa_gen.generate_from_chunks(
                chunks,
                num_pairs_per_chunk=args.pairs_per_chunk,
                output_path=None,
            )
            all_pairs.extend(pairs)
            print(f"  → {len(pairs)} QA pairs generated")
        except Exception as e:
            print(f"  [SKIP] {f.name}: {e}")

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    import json
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(all_pairs, fh, ensure_ascii=False, indent=2)
    print(f"\nTotal {len(all_pairs)} QA pairs → {output_path}")


if __name__ == "__main__":
    main()
