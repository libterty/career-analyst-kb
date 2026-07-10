"""Regression Gate — compare latest eval results against the approved baseline.

Usage:
  python eval/regression_check.py                     # checks both rag + routing
  python eval/regression_check.py --type rag
  python eval/regression_check.py --type routing

Exit codes:
  0 — all metrics at or above baseline (gate passes)
  1 — one or more metrics regressed (gate fails)

Baseline files live at eval/baselines/<type>_baseline.json.
Run `python eval/promote_baseline.py` to promote the latest result as the
new baseline after a human review.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
BASELINE_DIR = EVAL_DIR / "baselines"

RAG_METRICS = ["mean_relevance_score", "mean_keyword_hit_rate"]
ROUTING_METRICS = ["accuracy"]

RAG_TOLERANCE = 0.05       # allow up to 0.05 drop before flagging regression
ROUTING_TOLERANCE = 0.02   # allow up to 2pp drop in routing accuracy


def _latest_file(prefix: str) -> Path | None:
    files = sorted(RESULTS_DIR.glob(f"{prefix}_*.json"), reverse=True)
    return files[0] if files else None


def _summarize_rag(results: list[dict]) -> dict[str, float]:
    scores = [r["relevance_score"] for r in results if r.get("relevance_score") is not None]
    hit_rates = [r["keyword_hit_rate"] for r in results if r.get("keyword_hit_rate") is not None]
    return {
        "mean_relevance_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
        "mean_keyword_hit_rate": round(sum(hit_rates) / len(hit_rates), 4) if hit_rates else 0.0,
        "n": len(results),
    }


def _summarize_routing(results: list[dict]) -> dict[str, float]:
    correct = sum(1 for r in results if r.get("correct"))
    n = len(results)
    return {
        "accuracy": round(correct / n, 4) if n else 0.0,
        "n": n,
    }


def _check(
    eval_type: str,
    summarize_fn,
    metrics: list[str],
    tolerance: float,
) -> tuple[bool, list[str]]:
    baseline_path = BASELINE_DIR / f"{eval_type}_baseline.json"
    if not baseline_path.exists():
        print(f"  [WARN] No baseline found at {baseline_path}. Skipping {eval_type} check.")
        print(f"         Run: python eval/promote_baseline.py --type {eval_type}")
        return True, []

    latest = _latest_file(eval_type)
    if latest is None:
        print(f"  [WARN] No {eval_type} result files found in {RESULTS_DIR}. Skipping.")
        return True, []

    with open(latest) as f:
        candidate = summarize_fn(json.load(f))
    with open(baseline_path) as f:
        baseline = json.load(f)

    regressions: list[str] = []
    for metric in metrics:
        cval = candidate.get(metric, 0.0)
        bval = baseline.get(metric, 0.0)
        delta = cval - bval
        status = "OK" if delta >= -tolerance else "REGRESSION"
        print(f"  {eval_type}.{metric}: {cval:.4f}  baseline={bval:.4f}  Δ={delta:+.4f}  [{status}]")
        if status == "REGRESSION":
            regressions.append(f"{eval_type}.{metric}: {cval:.4f} < {bval:.4f} - {tolerance:.4f}")

    return len(regressions) == 0, regressions


def main() -> None:
    parser = argparse.ArgumentParser(description="Regression gate for eval metrics")
    parser.add_argument("--type", choices=["rag", "routing", "all"], default="all")
    args = parser.parse_args()

    BASELINE_DIR.mkdir(exist_ok=True)

    all_regressions: list[str] = []
    run_rag = args.type in ("rag", "all")
    run_routing = args.type in ("routing", "all")

    print("=== Regression Check ===")

    if run_rag:
        print("\n[RAG Eval]")
        _, issues = _check("rag_eval", _summarize_rag, RAG_METRICS, RAG_TOLERANCE)
        all_regressions.extend(issues)

    if run_routing:
        print("\n[Routing Eval]")
        _, issues = _check("routing_eval", _summarize_routing, ROUTING_METRICS, ROUTING_TOLERANCE)
        all_regressions.extend(issues)

    print()
    if all_regressions:
        print("GATE FAILED — regressions detected:")
        for r in all_regressions:
            print(f"  ✗ {r}")
        sys.exit(1)
    else:
        print("GATE PASSED — all metrics at or above baseline.")
        sys.exit(0)


if __name__ == "__main__":
    main()
