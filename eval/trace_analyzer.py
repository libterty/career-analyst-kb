"""Phase C — Routing Trace Analyzer

Aggregates all routing eval results to surface confusion pairs, low-confidence
near-misses, and routing fallbacks — the raw signal for hill-climbing.

Supported result formats:
  routing_eval_*.json        — kb-api classifier format
  candidate_voltagent_routing_*.json — voltagent multi-agent format

Usage:
  python eval/trace_analyzer.py
  python eval/trace_analyzer.py --verbose

Output:
  eval/results/trace_analysis_YYYYMMDD_HHMMSS.json
  eval/results/trace_analysis_latest.json  (symlink / copy for easy access)
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
DATASET_PATH = EVAL_DIR / "golden_dataset.jsonl"

LOW_CONFIDENCE_THRESHOLD = 0.75  # correct-but-fragile if confidence < this


# ---------------------------------------------------------------------------
# Dataset helpers
# ---------------------------------------------------------------------------

def load_question_map() -> dict[str, str]:
    """Return {id: question_text} from golden_dataset.jsonl."""
    q_map: dict[str, str] = {}
    if not DATASET_PATH.exists():
        return q_map
    with DATASET_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                entry = json.loads(line)
                q_map[entry["id"]] = entry["question"]
    return q_map


# ---------------------------------------------------------------------------
# Result loaders
# ---------------------------------------------------------------------------

def _load_kb_api_results(path: Path) -> list[dict]:
    """Load routing_eval_*.json (kb-api classifier format)."""
    with path.open() as f:
        data = json.load(f)
    if not isinstance(data, list):
        return []
    rows = []
    for r in data:
        if not isinstance(r, dict):
            continue
        raw_conf = r.get("confidence")
        try:
            conf = float(raw_conf) if raw_conf is not None else 1.0
        except (TypeError, ValueError):
            conf = 1.0  # older files store "keyword" as confidence placeholder
        rows.append({
            "source": path.name,
            "id": r.get("id", ""),
            "expected": r.get("expected", ""),
            "predicted": r.get("predicted_primary", ""),
            "predicted_all": r.get("predicted_all", []),
            "confidence": conf,
            "correct": bool(r.get("correct", False)),
            "question": r.get("question", ""),
        })
    return rows


def _load_voltagent_results(path: Path) -> list[dict]:
    """Load candidate_voltagent_routing_*.json (voltagent agent-routing format)."""
    with path.open() as f:
        data = json.load(f)
    if not isinstance(data, dict):
        return []
    results = data.get("results", [])
    rows = []
    for r in results:
        if not isinstance(r, dict):
            continue
        expected_agents = r.get("expected_agents", [])
        predicted_agents = r.get("predicted_agents", [])
        expected = expected_agents[0] if expected_agents else ""
        predicted = predicted_agents[0] if predicted_agents else ""
        rows.append({
            "source": path.name,
            "id": r.get("id", ""),
            "expected": expected,
            "predicted": predicted,
            "predicted_all": predicted_agents,
            "confidence": float(r.get("confidence") or 1.0),
            "correct": bool(r.get("correct", False)),
            "question": "",  # voltagent format hashes the question
        })
    return rows


def load_all_results() -> list[dict]:
    """Load all routing eval result files."""
    all_rows: list[dict] = []

    for path in sorted(RESULTS_DIR.glob("routing_eval_*.json")):
        try:
            rows = _load_kb_api_results(path)
            all_rows.extend(rows)
        except Exception as e:
            print(f"  [WARN] Could not parse {path.name}: {e}", file=sys.stderr)

    for path in sorted(RESULTS_DIR.glob("candidate_voltagent_routing_*.json")):
        try:
            rows = _load_voltagent_results(path)
            all_rows.extend(rows)
        except Exception as e:
            print(f"  [WARN] Could not parse {path.name}: {e}", file=sys.stderr)

    return all_rows


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def build_confusion_matrix(rows: list[dict]) -> dict[str, dict[str, int]]:
    """Return {expected: {predicted: count}}."""
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        matrix[r["expected"]][r["predicted"]] += 1
    return {k: dict(v) for k, v in matrix.items()}


def extract_confusion_pairs(rows: list[dict], q_map: dict[str, str]) -> list[dict]:
    """Return wrong predictions with question text where available."""
    pairs = []
    for r in rows:
        if r["correct"]:
            continue
        question = r["question"] or q_map.get(r["id"], "")
        pairs.append({
            "id": r["id"],
            "expected": r["expected"],
            "predicted": r["predicted"],
            "predicted_all": r["predicted_all"],
            "confidence": r["confidence"],
            "question": question,
            "source": r["source"],
        })
    return pairs


def extract_near_misses(rows: list[dict], q_map: dict[str, str]) -> list[dict]:
    """Return correct predictions with confidence below threshold — fragile routing."""
    near_misses = []
    for r in rows:
        if not r["correct"]:
            continue
        if r["confidence"] < LOW_CONFIDENCE_THRESHOLD:
            question = r["question"] or q_map.get(r["id"], "")
            near_misses.append({
                "id": r["id"],
                "expected": r["expected"],
                "predicted": r["predicted"],
                "confidence": r["confidence"],
                "question": question,
                "source": r["source"],
            })
    return near_misses


def per_category_stats(rows: list[dict]) -> dict[str, dict]:
    """Accuracy + average confidence per expected category."""
    cats: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        cats[r["expected"]].append(r)

    stats = {}
    for cat, cat_rows in sorted(cats.items()):
        n = len(cat_rows)
        correct = sum(1 for r in cat_rows if r["correct"])
        confidences = [r["confidence"] for r in cat_rows if r.get("confidence") is not None]
        stats[cat] = {
            "n": n,
            "correct": correct,
            "accuracy": round(correct / n, 4) if n else 0.0,
            "mean_confidence": round(sum(confidences) / len(confidences), 4) if confidences else None,
        }
    return stats


def identify_hill_targets(
    confusion_pairs: list[dict],
    near_misses: list[dict],
) -> list[dict]:
    """
    Derive concrete routing rule improvements to attempt.

    Each target is:
      {rule: str, category: 'confusion'|'near_miss', priority: int}
    """
    targets = []

    # Group confusion pairs by (expected, predicted)
    pair_counts: dict[tuple, list[dict]] = defaultdict(list)
    for cp in confusion_pairs:
        pair_counts[(cp["expected"], cp["predicted"])].append(cp)

    for (expected, predicted), items in sorted(
        pair_counts.items(), key=lambda x: -len(x[1])
    ):
        examples = [i["question"] for i in items if i.get("question")][:2]
        targets.append({
            "type": "confusion",
            "expected": expected,
            "mispredicted_as": predicted,
            "count": len(items),
            "example_questions": examples,
            "suggested_rule": (
                f"Add clearer distinguishing keywords for '{expected}' vs '{predicted}' "
                f"in routing instructions"
            ),
        })

    # Near-miss categories (high count → highest priority)
    nm_cats: dict[str, list[dict]] = defaultdict(list)
    for nm in near_misses:
        nm_cats[nm["expected"]].append(nm)

    for cat, items in sorted(nm_cats.items(), key=lambda x: -len(x[1])):
        examples = [i["question"] for i in items if i.get("question")][:2]
        targets.append({
            "type": "near_miss",
            "expected": cat,
            "count": len(items),
            "mean_confidence": round(
                sum(i["confidence"] for i in items) / len(items), 4
            ),
            "example_questions": examples,
            "suggested_rule": (
                f"Strengthen routing signal for '{cat}' to raise confidence above "
                f"{LOW_CONFIDENCE_THRESHOLD}"
            ),
        })

    return targets


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_summary(
    rows: list[dict],
    confusion_pairs: list[dict],
    near_misses: list[dict],
    stats: dict[str, dict],
    verbose: bool,
) -> None:
    total = len(rows)
    wrong = len(confusion_pairs)
    correct = total - wrong
    accuracy = correct / total if total else 0.0

    print("\n" + "=" * 60)
    print("TRACE ANALYSIS SUMMARY")
    print("=" * 60)
    print(f"Total rows:      {total}  (across all result files)")
    print(f"Correct:         {correct}")
    print(f"Wrong:           {wrong}")
    print(f"Overall accuracy:{accuracy:.1%}")
    print(f"Near-misses:     {len(near_misses)}  (correct but confidence < {LOW_CONFIDENCE_THRESHOLD})")

    print("\nPer-category stats:")
    for cat, s in stats.items():
        conf_str = f"  avg_conf={s['mean_confidence']:.2f}" if s["mean_confidence"] is not None else ""
        print(f"  {cat:<28} {s['correct']}/{s['n']} ({s['accuracy']:.0%}){conf_str}")

    if confusion_pairs:
        print("\nConfusion pairs:")
        pair_counts: dict[tuple, int] = defaultdict(int)
        for cp in confusion_pairs:
            pair_counts[(cp["expected"], cp["predicted"])] += 1
        for (exp, pred), cnt in sorted(pair_counts.items(), key=lambda x: -x[1]):
            print(f"  {exp:<22} → predicted as {pred:<22} ×{cnt}")

        if verbose:
            print("\nConfusion details:")
            for cp in confusion_pairs:
                q = cp["question"] or "(no question text)"
                print(f"  [{cp['id']}] expected={cp['expected']} predicted={cp['predicted']}")
                print(f"    Q: {q[:100]}")
    else:
        print("\nNo confusion pairs — routing is 100% accurate on loaded results.")

    if near_misses and verbose:
        print("\nNear-misses (low-confidence correct):")
        for nm in near_misses:
            q = nm["question"] or "(no question text)"
            print(f"  [{nm['id']}] {nm['expected']} conf={nm['confidence']:.2f}")
            print(f"    Q: {q[:100]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Routing Trace Analyzer")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    q_map = load_question_map()
    print(f"Loaded {len(q_map)} questions from golden dataset.")

    rows = load_all_results()
    print(f"Loaded {len(rows)} routing result rows from {RESULTS_DIR.name}/")

    if not rows:
        print("No routing result files found. Run routing_eval.py first.")
        sys.exit(0)

    confusion_pairs = extract_confusion_pairs(rows, q_map)
    near_misses = extract_near_misses(rows, q_map)
    stats = per_category_stats(rows)
    confusion_matrix = build_confusion_matrix(rows)
    hill_targets = identify_hill_targets(confusion_pairs, near_misses)

    print_summary(rows, confusion_pairs, near_misses, stats, args.verbose)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "total_rows": len(rows),
        "overall_accuracy": round((len(rows) - len(confusion_pairs)) / len(rows), 4) if rows else 0.0,
        "confusion_pairs": confusion_pairs,
        "near_misses": near_misses,
        "per_category_stats": stats,
        "confusion_matrix": confusion_matrix,
        "hill_targets": hill_targets,
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"trace_analysis_{ts}.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    latest_path = RESULTS_DIR / "trace_analysis_latest.json"
    latest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print(f"\nReport saved to {out_path}")
    print(f"Latest symlink:  {latest_path}")

    if hill_targets:
        print(f"\n{len(hill_targets)} hill-climbing target(s) identified.")
        print("Run harness-improver to generate prompt diffs:")
        print("  npx tsx services/voltagent-career/hill-climbing/harness-improver.ts")


if __name__ == "__main__":
    main()
