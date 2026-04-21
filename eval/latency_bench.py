"""Latency Benchmark — P50 / P95 / P99

對 /api/chat/query/sync 發送並發請求，測量端到端延遲。

用法：
  python eval/latency_bench.py --url http://localhost:8000 --token <JWT>
  python eval/latency_bench.py --url http://localhost:8000 --token <JWT> --concurrency 5 --runs 20

選項：
  --concurrency N   並發請求數（預設 1，壓測時可設 3-5）
  --runs N          總請求次數（預設 10）
  --topic           固定 topic filter（可選）

輸出：
  - 終端機：avg / P50 / P95 / P99 / min / max
  - eval/results/latency_bench_<timestamp>.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

EVAL_DIR = Path(__file__).parent
DATASET_PATH = EVAL_DIR / "golden_dataset.jsonl"
RESULTS_DIR = EVAL_DIR / "results"


def load_questions() -> list[dict]:
    entries = []
    with DATASET_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int(len(sorted_vals) * p / 100)
    return sorted_vals[min(idx, len(sorted_vals) - 1)]


async def single_request(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    question: str,
    topic: str,
    session_id: str,
) -> dict:
    t0 = time.perf_counter()
    try:
        resp = await client.post(
            f"{base_url}/api/chat/query/sync",
            json={"question": question, "session_id": session_id, "topic": topic},
            headers={"Authorization": f"Bearer {token}"},
            timeout=120,
        )
        resp.raise_for_status()
        latency_ms = (time.perf_counter() - t0) * 1000
        return {"latency_ms": latency_ms, "status": resp.status_code, "error": None}
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000
        return {"latency_ms": latency_ms, "status": 0, "error": str(e)}


async def run_bench(
    base_url: str,
    token: str,
    runs: int,
    concurrency: int,
    fixed_topic: str | None,
) -> list[dict]:
    questions = load_questions()
    if fixed_topic:
        questions = [q for q in questions if q["topic"] == fixed_topic] or questions

    results = []
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded_request(i: int) -> dict:
        entry = random.choice(questions)
        session_id = f"bench-{i}-{entry['id']}"
        async with semaphore:
            r = await single_request(
                client, base_url, token,
                entry["question"], entry["topic"], session_id,
            )
            r["run"] = i
            r["question_id"] = entry["id"]
            status = f"ERROR: {r['error']}" if r["error"] else f"{r['latency_ms']:.0f}ms"
            print(f"  [{i+1:03d}/{runs}] {entry['id']:<25} {status}")
            return r

    async with httpx.AsyncClient() as client:
        tasks = [bounded_request(i) for i in range(runs)]
        results = await asyncio.gather(*tasks)

    return list(results)


def print_summary(results: list[dict], concurrency: int) -> None:
    success = [r for r in results if r["error"] is None]
    errors = [r for r in results if r["error"] is not None]
    lats = [r["latency_ms"] for r in success]

    print("\n" + "=" * 60)
    print("LATENCY BENCHMARK SUMMARY")
    print("=" * 60)
    print(f"Total runs:   {len(results)}")
    print(f"Concurrency:  {concurrency}")
    print(f"Successful:   {len(success)}")
    print(f"Errors:       {len(errors)}")

    if lats:
        print(f"\nLatency (ms):")
        print(f"  Min:  {min(lats):.0f}")
        print(f"  Avg:  {sum(lats)/len(lats):.0f}")
        print(f"  P50:  {percentile(lats, 50):.0f}")
        print(f"  P95:  {percentile(lats, 95):.0f}")
        print(f"  P99:  {percentile(lats, 99):.0f}")
        print(f"  Max:  {max(lats):.0f}")

    if errors:
        print(f"\nErrors:")
        for r in errors[:5]:
            print(f"  [{r['run']}] {r['error']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Latency Benchmark")
    parser.add_argument("--url", default="http://localhost:8000", help="KB API base URL")
    parser.add_argument("--token", default=os.environ.get("CAREER_API_TOKEN", ""),
                        help="JWT bearer token")
    parser.add_argument("--runs", type=int, default=10, help="Total number of requests")
    parser.add_argument("--concurrency", type=int, default=1, help="Concurrent requests")
    parser.add_argument("--topic", default=None, help="Fix topic filter for all requests")
    args = parser.parse_args()

    if not args.token:
        print("ERROR: --token or CAREER_API_TOKEN required", file=sys.stderr)
        sys.exit(1)

    print(f"Benchmarking {args.url}  runs={args.runs}  concurrency={args.concurrency}")
    results = asyncio.run(
        run_bench(args.url, args.token, args.runs, args.concurrency, args.topic)
    )
    print_summary(results, args.concurrency)

    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"latency_bench_{ts}.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
