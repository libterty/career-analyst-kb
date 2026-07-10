"""Phase C-3 — Apply Low-Risk Diffs + Regression Gate

Reads the latest proposed-diffs JSON, applies every low_risk diff to
supervisor.ts, runs the regression gate, and auto-reverts on failure.

Usage:
  python eval/apply_low_risk_diffs.py
  python eval/apply_low_risk_diffs.py --dry-run
  python eval/apply_low_risk_diffs.py --also-high-risk   # human-supervised run

Exit codes:
  0 — all low-risk diffs applied and gate passed (or nothing to apply)
  1 — gate failed; changes reverted automatically
  2 — patch error (excerpt not found); no file was modified
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
SUPERVISOR_PATH = REPO_ROOT / "services/voltagent-career/src/agents/supervisor.ts"
DIFFS_LATEST = REPO_ROOT / "services/voltagent-career/hill-climbing/proposed-diffs/latest.json"
APPLY_LOG = REPO_ROOT / "services/voltagent-career/hill-climbing/apply-log.jsonl"
BACKUP_DIR = REPO_ROOT / "services/voltagent-career/hill-climbing/backups"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_diffs(also_high_risk: bool) -> list[dict]:
    if not DIFFS_LATEST.exists():
        print(f"No proposed diffs found at {DIFFS_LATEST}")
        print("Run: npx tsx services/voltagent-career/hill-climbing/harness-improver.ts")
        sys.exit(0)

    data = json.loads(DIFFS_LATEST.read_text())
    diffs = data.get("diffs", [])
    if also_high_risk:
        return diffs
    return [d for d in diffs if d.get("risk") == "low_risk"]


def backup_supervisor() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"supervisor_{ts}.ts"
    shutil.copy2(SUPERVISOR_PATH, backup_path)
    return backup_path


def apply_diffs(source: str, diffs: list[dict]) -> tuple[str, list[str], list[str]]:
    """Return (patched_source, applied_ids, missed_ids)."""
    patched = source
    applied: list[str] = []
    missed: list[str] = []

    for diff in diffs:
        excerpt = diff["original_excerpt"]
        replacement = diff["replacement"]
        if excerpt in patched:
            patched = patched.replace(excerpt, replacement, 1)
            applied.append(diff["id"])
        else:
            missed.append(diff["id"])

    return patched, applied, missed


def run_regression_gate() -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "eval/regression_check.py"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    output = result.stdout + result.stderr
    return result.returncode == 0, output


def log_run(entry: dict) -> None:
    APPLY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with APPLY_LOG.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Apply low-risk prompt diffs")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be applied without writing files")
    parser.add_argument("--also-high-risk", action="store_true",
                        help="Also apply high-risk diffs (requires human review)")
    args = parser.parse_args()

    diffs = load_diffs(args.also_high_risk)

    if not diffs:
        risk_label = "any" if args.also_high_risk else "low-risk"
        print(f"No {risk_label} diffs to apply.")
        sys.exit(0)

    print(f"=== Apply Low-Risk Diffs ===\n")
    print(f"Found {len(diffs)} diff(s) to attempt:")
    for d in diffs:
        print(f"  [{d['risk'].ljust(9)}] {d['id']}")

    if not SUPERVISOR_PATH.exists():
        print(f"\nERROR: Supervisor not found at {SUPERVISOR_PATH}")
        sys.exit(2)

    source = SUPERVISOR_PATH.read_text()
    patched, applied, missed = apply_diffs(source, diffs)

    if missed:
        print(f"\nWARNING: {len(missed)} excerpt(s) not found in current file:")
        for m in missed:
            print(f"  MISS: {m}")

    if not applied:
        print("\nNothing to apply — all excerpts were missing. File unchanged.")
        sys.exit(2)

    print(f"\nWould apply: {applied}")

    if args.dry_run:
        print("\n--- Dry run: no files written ---")
        print(f"\nPatched instructions diff preview:")
        orig_instr = _extract_instructions(source)
        new_instr = _extract_instructions(patched)
        _show_diff(orig_instr, new_instr)
        return

    # Backup + write
    backup_path = backup_supervisor()
    print(f"\nBacked up supervisor to {backup_path.name}")

    SUPERVISOR_PATH.write_text(patched)
    print(f"Applied {len(applied)} diff(s) to {SUPERVISOR_PATH.relative_to(REPO_ROOT)}")

    # Run regression gate
    print("\nRunning regression gate ...")
    gate_passed, gate_output = run_regression_gate()
    print(gate_output.rstrip())

    log_entry: dict = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "applied": applied,
        "missed": missed,
        "backup": str(backup_path),
        "gate_passed": gate_passed,
    }

    if gate_passed:
        print("\nGATE PASSED — diffs committed to supervisor.ts")
        log_entry["outcome"] = "applied"
        log_run(log_entry)
        sys.exit(0)
    else:
        print("\nGATE FAILED — reverting supervisor.ts")
        shutil.copy2(backup_path, SUPERVISOR_PATH)
        print(f"Restored from {backup_path.name}")
        log_entry["outcome"] = "reverted"
        log_run(log_entry)
        sys.exit(1)


def _extract_instructions(source: str) -> str:
    import re
    m = re.search(r"instructions:\s*`([\s\S]*?)`", source)
    return m.group(1).strip() if m else source


def _show_diff(original: str, patched: str) -> None:
    orig_lines = original.splitlines()
    patch_lines = patched.splitlines()
    for i, (o, p) in enumerate(zip(orig_lines, patch_lines)):
        if o != p:
            print(f"  - line {i+1}: {o[:100]}")
            print(f"  + line {i+1}: {p[:100]}")
    extra = len(patch_lines) - len(orig_lines)
    if extra > 0:
        print(f"  + {extra} new line(s)")
    elif extra < 0:
        print(f"  - {-extra} removed line(s)")


if __name__ == "__main__":
    main()
