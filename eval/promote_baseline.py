"""Promote the latest eval result as the approved baseline.

Usage:
  python eval/promote_baseline.py              # promotes both rag + routing
  python eval/promote_baseline.py --type rag
  python eval/promote_baseline.py --type routing
  python eval/promote_baseline.py --file eval/results/rag_eval_20260504_205201.json

Only run this after a human review confirms the new result is acceptable.
The baseline is stored at eval/baselines/<type>_baseline.json.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
BASELINE_DIR = EVAL_DIR / "baselines"


def _latest_file(prefix: str) -> Path | None:
    files = sorted(RESULTS_DIR.glob(f"{prefix}_*.json"), reverse=True)
    return files[0] if files else None


def _summarize_rag(results: list[dict]) -> dict:
    scores = [r["relevance_score"] for r in results if r.get("relevance_score") is not None]
    hit_rates = [r["keyword_hit_rate"] for r in results if r.get("keyword_hit_rate") is not None]
    return {
        "mean_relevance_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "mean_keyword_hit_rate": round(sum(hit_rates) / len(hit_rates), 4) if hit_rates else 0.0,
        "n": len(results),
    }


def _summarize_routing(results: list[dict]) -> dict:
    correct = sum(1 for r in results if r.get("correct"))
    n = len(results)
    return {
        "accuracy": round(correct / n, 4) if n else 0.0,
        "n": n,
    }


def _promote(eval_type: str, source_file: Path | None, summarize_fn) -> None:
    if source_file is None:
        print(f"  [SKIP] No result file for {eval_type}.")
        return
    with open(source_file) as f:
        results = json.load(f)
    summary = summarize_fn(results)
    summary["promoted_from"] = source_file.name
    from datetime import timezone
    summary["promoted_at"] = datetime.now(timezone.utc).isoformat()

    out = BASELINE_DIR / f"{eval_type}_baseline.json"
    BASELINE_DIR.mkdir(exist_ok=True)
    with open(out, "w") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"  Promoted {source_file.name} → {out}")
    for k, v in summary.items():
        if k not in ("promoted_from", "promoted_at"):
            print(f"    {k}: {v}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Promote eval baseline")
    parser.add_argument("--type", choices=["rag", "routing", "all"], default="all")
    parser.add_argument("--file", type=Path, help="Explicit result file to promote")
    args = parser.parse_args()

    print("=== Promote Baseline ===\n")

    if args.file:
        name = args.file.stem
        if "rag_eval" in name:
            _promote("rag_eval", args.file, _summarize_rag)
        elif "routing_eval" in name:
            _promote("routing_eval", args.file, _summarize_routing)
        else:
            print(f"Cannot determine eval type from filename: {args.file}")
        return

    if args.type in ("rag", "all"):
        print("[RAG Eval]")
        _promote("rag_eval", _latest_file("rag_eval"), _summarize_rag)

    if args.type in ("routing", "all"):
        print("\n[Routing Eval]")
        _promote("routing_eval", _latest_file("routing_eval"), _summarize_routing)


if __name__ == "__main__":
    main()
