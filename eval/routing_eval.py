"""Agent Routing Accuracy Evaluation

測試 CareerClassifier 是否將問題正確分類到預期 topic。

用法：
  # 從 repo root（或 services/kb-api/）執行
  python eval/routing_eval.py

  # 顯示每一筆錯誤的分類
  python eval/routing_eval.py --verbose

輸出：
  - 終端機摘要（overall accuracy + per-topic breakdown）
  - eval/results/routing_eval_<timestamp>.json
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

EVAL_DIR = Path(__file__).parent
DATASET_PATH = EVAL_DIR / "golden_dataset.jsonl"
RESULTS_DIR = EVAL_DIR / "results"

# Add services/kb-api to sys.path so we can import career_classifier
KB_API_DIR = Path(__file__).parent.parent / "services" / "kb-api"
if str(KB_API_DIR) not in sys.path:
    sys.path.insert(0, str(KB_API_DIR))


def load_dataset() -> list[dict]:
    entries = []
    with DATASET_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def run_eval(verbose: bool) -> list[dict]:
    from src.ingestion.career_classifier import classify

    dataset = load_dataset()
    results = []

    for entry in dataset:
        result_obj = classify(entry["question"])
        predicted_topics = result_obj.topics
        confidence = result_obj.confidence
        primary = predicted_topics[0] if predicted_topics else "general_career"
        expected = entry["topic"]
        # correct if expected topic appears anywhere in predicted topics
        correct = expected in predicted_topics

        result = {
            "id": entry["id"],
            "question": entry["question"],
            "expected": expected,
            "predicted_primary": primary,
            "predicted_all": predicted_topics,
            "confidence": confidence,
            "correct": correct,
        }

        if verbose and not correct:
            print(f"WRONG [{entry['id']}]")
            print(f"  Q:         {entry['question'][:80]}")
            print(f"  Expected:  {expected}")
            print(f"  Predicted: {predicted_topics} ({confidence})")

        results.append(result)

    return results


def print_summary(results: list[dict]) -> None:
    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    accuracy = correct / total if total else 0

    print("\n" + "=" * 60)
    print("ROUTING EVAL SUMMARY")
    print("=" * 60)
    print(f"Total:    {total}")
    print(f"Correct:  {correct}")
    print(f"Accuracy: {accuracy:.1%}")

    print("\nPer-topic breakdown:")
    topics = sorted({r["expected"] for r in results})
    for topic in topics:
        t_results = [r for r in results if r["expected"] == topic]
        t_correct = sum(1 for r in t_results if r["correct"])
        t_acc = t_correct / len(t_results) if t_results else 0
        mistakes = [r["predicted_all"] for r in t_results if not r["correct"]]
        mistake_str = f"  → misclassified as: {mistakes}" if mistakes else ""
        print(f"  {topic:<22} {t_correct}/{len(t_results)} ({t_acc:.0%}){mistake_str}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Agent Routing Accuracy Evaluation")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Print details for each misclassified entry")
    args = parser.parse_args()

    print(f"Running routing eval on {DATASET_PATH.name}")
    results = run_eval(args.verbose)
    print_summary(results)

    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"routing_eval_{ts}.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()
