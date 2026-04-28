"""Build SFT dataset from golden_dataset.jsonl + optional CoT seeds.

Steps:
  1. Load eval/golden_dataset.jsonl (questions + expected keywords)
  2. Call /api/chat/query/sync for each question to get model answers
  3. Format as chat-style SFT pairs (system / user / assistant)
  4. Append any hand-crafted CoT seed examples from eval/sft_seeds.jsonl
  5. Write to eval/sft_dataset.jsonl

Usage:
  python3 scripts/build_sft_dataset.py --url http://localhost:8000 --token <JWT>
  python3 scripts/build_sft_dataset.py --url http://localhost:8000 --token <JWT> --seeds-only
  python3 scripts/build_sft_dataset.py --url http://localhost:8000 --token <JWT> --no-seeds
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import httpx

EVAL_DIR = Path(__file__).parent.parent / "eval"
DATASET_PATH = EVAL_DIR / "golden_dataset.jsonl"
SEEDS_PATH = EVAL_DIR / "sft_seeds.jsonl"
OUTPUT_PATH = EVAL_DIR / "sft_dataset.jsonl"

SYSTEM_PROMPT = (
    "你是一位專業的職涯分析師，根據職涯顧問的影片內容協助使用者解決職涯問題。"
    "回答前先拆解問題的核心需求，找出最相關的建議，再提供具體、有條理的回應。"
    "回答以繁體中文撰寫，語調專業而親切。"
)


def load_questions() -> list[dict]:
    entries = []
    with DATASET_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def load_seeds() -> list[dict]:
    if not SEEDS_PATH.exists():
        return []
    entries = []
    with SEEDS_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def query_kb(client: httpx.Client, base_url: str, token: str, question: str) -> str | None:
    try:
        resp = client.post(
            f"{base_url}/api/chat/query/sync",
            json={"question": question},
            headers={"Authorization": f"Bearer {token}"},
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json().get("answer", "").strip()
    except Exception as exc:
        print(f"  ERROR: {exc}", file=sys.stderr)
        return None


def to_sft_record(question: str, answer: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SFT dataset")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--token", default=os.environ.get("CAREER_API_TOKEN", ""))
    parser.add_argument("--seeds-only", action="store_true", help="Only include seed examples")
    parser.add_argument("--no-seeds", action="store_true", help="Skip seed examples")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between requests")
    args = parser.parse_args()

    if not args.token and not args.seeds_only:
        print("ERROR: --token or CAREER_API_TOKEN required", file=sys.stderr)
        sys.exit(1)

    records: list[dict] = []

    # --- golden dataset → model responses ---
    if not args.seeds_only:
        questions = load_questions()
        print(f"Loaded {len(questions)} questions from golden_dataset.jsonl")
        with httpx.Client() as client:
            for i, entry in enumerate(questions, 1):
                q = entry["question"]
                topic = entry.get("topic", "?")
                print(f"[{i:2d}/{len(questions)}] [{topic}] {q[:60]}...")
                answer = query_kb(client, args.url, args.token, q)
                if answer:
                    records.append(to_sft_record(q, answer))
                    print(f"       → {len(answer)} chars")
                else:
                    print("       → SKIPPED (no answer)")
                if i < len(questions):
                    time.sleep(args.delay)

    # --- seed CoT examples ---
    if not args.no_seeds:
        seeds = load_seeds()
        if seeds:
            print(f"\nAppending {len(seeds)} seed CoT examples")
            records.extend(seeds)
        else:
            print("\nNo seed file found at eval/sft_seeds.jsonl — skipping seeds")

    # --- write output ---
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"\nWrote {len(records)} SFT records → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
