"""A/B Evaluation — qwen3:8b vs qwen3:14b 回答品質比較

直接呼叫 Ollama 對每道 golden_dataset 問題產生兩個回答，
用 LLM-as-judge（qwen3-30b-a3b）評分後輸出比較報告。

用法：
  python eval/ab_eval.py
  python eval/ab_eval.py --model-a qwen3:8b --model-b qwen3:14b --no-judge

評分維度：
  - Relevance score (0-4):  LLM judge 評估與問題的相關性
  - Keyword hit rate:       expected_keywords 出現在答案中的比率
  - Latency (ms):           Ollama 推論時間
"""
from __future__ import annotations

import argparse
import json
import re
import time
from datetime import datetime
from pathlib import Path

import httpx

EVAL_DIR = Path(__file__).parent
DATASET_PATH = EVAL_DIR / "golden_dataset.jsonl"
RESULTS_DIR = EVAL_DIR / "results"

OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL_A = "qwen3:8b"
DEFAULT_MODEL_B = "qwen3:14b"
JUDGE_MODEL = "qwen3-30b-a3b:latest"

SYSTEM_PROMPT = """\
你是一位專業的職涯分析師，擅長提供台灣職場相關建議。
請針對使用者的問題給出具體、實用的建議，包含實際例子或步驟。
回答使用繁體中文，長度約 150-300 字。"""

JUDGE_PROMPT = """\
/no_think
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


def call_ollama(model: str, question: str) -> tuple[str, float]:
    """回傳 (answer, latency_ms)。"""
    t0 = time.perf_counter()
    try:
        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": question},
                ],
                "stream": False,
                "options": {"temperature": 0.3},
            },
            timeout=180,
        )
        resp.raise_for_status()
        latency_ms = (time.perf_counter() - t0) * 1000
        answer = resp.json()["message"]["content"]
        # strip <think>...</think> blocks
        answer = re.sub(r"<think>.*?</think>", "", answer, flags=re.DOTALL).strip()
        return answer, round(latency_ms)
    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000
        return f"[ERROR: {e}]", round(latency_ms)


def judge_relevance(question: str, answer: str) -> int:
    if answer.startswith("[ERROR"):
        return -1
    prompt = JUDGE_PROMPT.format(question=question, answer=answer[:3000])
    try:
        resp = httpx.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": JUDGE_MODEL, "prompt": prompt, "stream": False},
            timeout=180,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "").strip()
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        m = re.search(r"[0-4]", text)
        return int(m.group()) if m else 0
    except Exception:
        return -1


def keyword_hit_rate(answer: str, keywords: list[str]) -> float:
    if not keywords:
        return 1.0
    answer_lower = answer.lower()
    hits = sum(1 for kw in keywords if kw.lower() in answer_lower)
    return hits / len(keywords)


def run_ab_eval(model_a: str, model_b: str, use_judge: bool) -> list[dict]:
    dataset = load_dataset()
    results = []

    for i, entry in enumerate(dataset, 1):
        q = entry["question"]
        kws = entry.get("expected_keywords", [])
        print(f"[{i:02d}/{len(dataset)}] {entry['id']}")

        print(f"  {model_a} ...", end=" ", flush=True)
        ans_a, lat_a = call_ollama(model_a, q)
        score_a = judge_relevance(q, ans_a) if use_judge else -1
        kw_a = keyword_hit_rate(ans_a, kws)
        print(f"score={score_a} kw={kw_a:.0%} {lat_a}ms")

        print(f"  {model_b} ...", end=" ", flush=True)
        ans_b, lat_b = call_ollama(model_b, q)
        score_b = judge_relevance(q, ans_b) if use_judge else -1
        kw_b = keyword_hit_rate(ans_b, kws)
        print(f"score={score_b} kw={kw_b:.0%} {lat_b}ms")

        winner = "tie"
        if score_a > score_b:
            winner = model_a
        elif score_b > score_a:
            winner = model_b

        results.append({
            "id": entry["id"],
            "topic": entry["topic"],
            "question": q,
            model_a: {
                "answer": ans_a[:800],
                "relevance_score": score_a,
                "keyword_hit_rate": round(kw_a, 2),
                "latency_ms": lat_a,
            },
            model_b: {
                "answer": ans_b[:800],
                "relevance_score": score_b,
                "keyword_hit_rate": round(kw_b, 2),
                "latency_ms": lat_b,
            },
            "winner": winner,
        })

    return results


def print_summary(results: list[dict], model_a: str, model_b: str) -> None:
    judged = [r for r in results if r[model_a]["relevance_score"] >= 0]
    avg_a: float = -1.0
    avg_b: float = -1.0

    print("\n" + "=" * 65)
    print("A/B EVAL SUMMARY")
    print("=" * 65)
    print(f"{'Metric':<28} {model_a:<18} {model_b}")
    print("-" * 65)

    if judged:
        avg_a = sum(r[model_a]["relevance_score"] for r in judged) / len(judged)
        avg_b = sum(r[model_b]["relevance_score"] for r in judged) / len(judged)
        print(f"{'Avg relevance (0-4)':<28} {avg_a:<18.2f} {avg_b:.2f}")

        wins_a = sum(1 for r in results if r["winner"] == model_a)
        wins_b = sum(1 for r in results if r["winner"] == model_b)
        ties = sum(1 for r in results if r["winner"] == "tie")
        print(f"{'Wins':<28} {wins_a:<18} {wins_b}  (ties: {ties})")

    kw_a = sum(r[model_a]["keyword_hit_rate"] for r in results) / len(results)
    kw_b = sum(r[model_b]["keyword_hit_rate"] for r in results) / len(results)
    print(f"{'Avg keyword hit rate':<28} {kw_a:<18.0%} {kw_b:.0%}")

    lat_a = sum(r[model_a]["latency_ms"] for r in results) / len(results)
    lat_b = sum(r[model_b]["latency_ms"] for r in results) / len(results)
    print(f"{'Avg latency (ms)':<28} {lat_a:<18.0f} {lat_b:.0f}")

    print("\nPer-topic breakdown (avg relevance):")
    topics = sorted({r["topic"] for r in results})
    for topic in topics:
        t = [r for r in judged if r["topic"] == topic]
        if not t:
            continue
        a = sum(r[model_a]["relevance_score"] for r in t) / len(t)
        b = sum(r[model_b]["relevance_score"] for r in t) / len(t)
        diff = b - a
        indicator = "↑B" if diff > 0.2 else ("↑A" if diff < -0.2 else "≈")
        print(f"  {topic:<22} {a:.2f}  vs  {b:.2f}  {indicator}")

    print()
    if judged:
        overall_winner = model_a if avg_a > avg_b else (model_b if avg_b > avg_a else "tie")
        print(f"Overall winner: {overall_winner}")


def main() -> None:
    parser = argparse.ArgumentParser(description="A/B model quality comparison")
    parser.add_argument("--model-a", default=DEFAULT_MODEL_A)
    parser.add_argument("--model-b", default=DEFAULT_MODEL_B)
    parser.add_argument("--no-judge", action="store_true",
                        help="Skip LLM-as-judge (keyword-only, much faster)")
    args = parser.parse_args()

    print(f"A/B Eval: {args.model_a} vs {args.model_b}")
    print(f"Dataset:  {DATASET_PATH.name} ({sum(1 for _ in DATASET_PATH.open())} questions)")
    print(f"Judge:    {'disabled' if args.no_judge else JUDGE_MODEL}\n")

    results = run_ab_eval(args.model_a, args.model_b, use_judge=not args.no_judge)
    print_summary(results, args.model_a, args.model_b)

    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"ab_eval_{ts}.json"
    out_path.write_text(json.dumps({
        "generated_at": datetime.now().isoformat(),
        "model_a": args.model_a,
        "model_b": args.model_b,
        "judge_model": JUDGE_MODEL if not args.no_judge else None,
        "results": results,
    }, ensure_ascii=False, indent=2))
    print(f"Results saved to {out_path}")


if __name__ == "__main__":
    main()
