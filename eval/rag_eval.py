"""RAG Precision Evaluation — LLM-as-judge

用法：
  python eval/rag_eval.py --url http://localhost:8000 --token <JWT>

指標：
  - Relevance score (0-4):  LLM 評估答案與問題的相關性
  - Keyword hit rate:       expected_keywords 出現在答案中的比率
  - Has sources:            回應是否附帶來源
  - Mean scores per topic

輸出：
  - 終端機摘要
  - eval/results/rag_eval_<timestamp>.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

EVAL_DIR = Path(__file__).parent
DATASET_PATH = EVAL_DIR / "golden_dataset.jsonl"
RESULTS_DIR = EVAL_DIR / "results"

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "gemma3:12b")

JUDGE_PROMPT = """\
你是一位公正的評審，請評估以下「答案」對於「問題」的相關性與品質。

問題：{question}

答案：{answer}

請從以下角度評分（0-4 分）：
0 = 完全不相關或無法回答
1 = 略有相關但缺乏具體內容
2 = 中等，有部分回應但不夠完整
3 = 良好，有效回應問題且包含實用建議
4 = 優秀，回應完整、具體、有實例或步驟說明

只輸出一個 0 到 4 的整數，不要有任何其他文字。"""


def load_dataset() -> list[dict]:
    entries = []
    with DATASET_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def call_kb_api(
    client: httpx.Client,
    base_url: str,
    token: str,
    question: str,
    topic: str,
    session_id: str,
) -> dict:
    resp = client.post(
        f"{base_url}/api/chat/query/sync",
        json={"question": question, "session_id": session_id, "topic": topic},
        headers={"Authorization": f"Bearer {token}"},
        timeout=180,
    )
    resp.raise_for_status()
    return resp.json()


def judge_relevance(question: str, answer: str) -> int:
    prompt = JUDGE_PROMPT.format(question=question, answer=answer[:1500])
    try:
        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": JUDGE_MODEL, "prompt": prompt, "stream": False},
            timeout=120,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        score = int(text[0]) if text and text[0].isdigit() else 0
        return min(max(score, 0), 4)
    except Exception:
        return -1


def keyword_hit_rate(answer: str, keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    answer_lower = answer.lower()
    hits = sum(1 for kw in keywords if kw.lower() in answer_lower)
    return hits / len(keywords)


def run_eval(base_url: str, token: str, use_judge: bool) -> dict:
    dataset = load_dataset()
    results = []

    with httpx.Client() as client:
        for i, entry in enumerate(dataset, 1):
            print(f"[{i:02d}/{len(dataset)}] {entry['id']} ...", end=" ", flush=True)

            session_id = f"eval-{entry['id']}"
            t0 = time.perf_counter()
            try:
                data = call_kb_api(
                    client, base_url, token,
                    entry["question"], entry["topic"], session_id,
                )
                latency_ms = (time.perf_counter() - t0) * 1000
                answer = data.get("answer", "")
                sources = data.get("sources", [])

                relevance = judge_relevance(entry["question"], answer) if use_judge else -1
                kw_rate = keyword_hit_rate(answer, entry.get("expected_keywords", []))
                has_sources = len(sources) > 0

                result = {
                    **entry,
                    "answer": answer[:300],
                    "latency_ms": round(latency_ms),
                    "relevance_score": relevance,
                    "keyword_hit_rate": round(kw_rate, 2),
                    "has_sources": has_sources,
                    "source_count": len(sources),
                    "error": None,
                }
                status = f"score={relevance} kw={kw_rate:.0%} {latency_ms:.0f}ms"
            except Exception as e:
                latency_ms = (time.perf_counter() - t0) * 1000
                result = {**entry, "answer": "", "latency_ms": round(latency_ms),
                          "relevance_score": -1, "keyword_hit_rate": 0.0,
                          "has_sources": False, "source_count": 0, "error": str(e)}
                status = f"ERROR: {e}"

            print(status)
            results.append(result)

    return results


def print_summary(results: list[dict]) -> None:
    valid = [r for r in results if r["error"] is None]
    judged = [r for r in valid if r["relevance_score"] >= 0]

    print("\n" + "=" * 60)
    print("RAG EVAL SUMMARY")
    print("=" * 60)
    print(f"Total entries:     {len(results)}")
    print(f"Successful calls:  {len(valid)}")
    print(f"Errors:            {len(results) - len(valid)}")

    if judged:
        avg_score = sum(r["relevance_score"] for r in judged) / len(judged)
        print(f"Avg relevance:     {avg_score:.2f} / 4.0")
        score_dist = {i: sum(1 for r in judged if r["relevance_score"] == i) for i in range(5)}
        print(f"Score dist:        {score_dist}")

    if valid:
        avg_kw = sum(r["keyword_hit_rate"] for r in valid) / len(valid)
        has_src_pct = sum(1 for r in valid if r["has_sources"]) / len(valid)
        avg_lat = sum(r["latency_ms"] for r in valid) / len(valid)
        lats = sorted(r["latency_ms"] for r in valid)
        p50 = lats[int(len(lats) * 0.5)]
        p95 = lats[int(len(lats) * 0.95)]
        print(f"Avg keyword hit:   {avg_kw:.0%}")
        print(f"Has sources:       {has_src_pct:.0%}")
        print(f"Latency avg/P50/P95: {avg_lat:.0f}ms / {p50}ms / {p95}ms")

    print("\nPer-topic breakdown:")
    topics = sorted({r["topic"] for r in results})
    for topic in topics:
        t_results = [r for r in results if r["topic"] == topic and r["error"] is None]
        if not t_results:
            continue
        t_judged = [r for r in t_results if r["relevance_score"] >= 0]
        avg = sum(r["relevance_score"] for r in t_judged) / len(t_judged) if t_judged else -1
        kw = sum(r["keyword_hit_rate"] for r in t_results) / len(t_results)
        score_str = f"{avg:.2f}" if avg >= 0 else "N/A"
        print(f"  {topic:<22} relevance={score_str}  kw={kw:.0%}  n={len(t_results)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="RAG Precision Evaluation")
    parser.add_argument("--url", default="http://localhost:8000", help="KB API base URL")
    parser.add_argument("--token", default=os.environ.get("CAREER_API_TOKEN", ""),
                        help="JWT bearer token (or set CAREER_API_TOKEN env var)")
    parser.add_argument("--no-judge", action="store_true",
                        help="Skip LLM-as-judge scoring (faster, keyword-only)")
    args = parser.parse_args()

    if not args.token:
        print("ERROR: --token or CAREER_API_TOKEN required", file=sys.stderr)
        sys.exit(1)

    print(f"Evaluating {DATASET_PATH.name} against {args.url}")
    print(f"LLM judge: {'disabled' if args.no_judge else JUDGE_MODEL}\n")

    results = run_eval(args.url, args.token, use_judge=not args.no_judge)
    print_summary(results)

    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"rag_eval_{ts}.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
