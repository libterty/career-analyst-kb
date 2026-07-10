"""Knowledge Gap Daily Summary — 聚合每日 score ≤ 2 的問題，按主題分群輸出 markdown。

Usage:
  # Activate the kb-api venv first, or have psycopg2 installed
  python eval/knowledge_gap_analyzer.py
  python eval/knowledge_gap_analyzer.py --date 2026-07-10
  python eval/knowledge_gap_analyzer.py --days 7          # last 7 days

Output:
  data/knowledge_gaps/YYYY-MM-DD.md

Reads from the knowledge_gaps table (populated by the answer-quality judge
middleware when quality_score ≤ 2).

Requires:
  DATABASE_URL env var  OR  uses default postgresql://career:secret@localhost:5432/career_kb
"""
from __future__ import annotations

import argparse
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://career:secret@localhost:5432/career_kb",
)

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "knowledge_gaps"

TOPIC_KEYWORDS: dict[str, list[str]] = {
    "resume": ["履歷", "resume", "cv", "ats", "自傳", "cover letter", "作品集"],
    "interview": ["面試", "interview", "star", "自我介紹", "behavioral"],
    "career_plan": ["轉職", "升遷", "職涯", "career", "技能", "學習路徑", "發展"],
    "salary": ["薪資", "薪水", "offer", "salary", "談判", "行情", "compensation"],
}


def _infer_topic(question: str) -> str:
    q = question.lower()
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return topic
    return "general"


def _sync_url(url: str) -> str:
    """Strip asyncpg/async driver prefix for psycopg2."""
    return re.sub(r"postgresql\+asyncpg", "postgresql", url)


def fetch_gaps(target_date: date, window_days: int) -> list[dict]:
    import psycopg2
    import psycopg2.extras

    start = datetime(target_date.year, target_date.month, target_date.day, tzinfo=timezone.utc)
    if window_days > 1:
        start -= timedelta(days=window_days - 1)
    end = start + timedelta(days=window_days)

    conn = psycopg2.connect(_sync_url(DATABASE_URL))
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT
                    id,
                    question_hash,
                    redacted_question,
                    agent_name,
                    trigger,
                    quality_score,
                    status,
                    occurrences,
                    created_at,
                    last_seen_at
                FROM knowledge_gaps
                WHERE last_seen_at >= %s AND last_seen_at < %s
                ORDER BY occurrences DESC, quality_score ASC
                """,
                (start, end),
            )
            return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def render_report(gaps: list[dict], target_date: date, window_days: int) -> str:
    if window_days == 1:
        date_str = target_date.isoformat()
        title = f"# Knowledge Gap Report — {date_str}"
    else:
        end = target_date
        start = end - timedelta(days=window_days - 1)
        date_str = target_date.isoformat()
        title = f"# Knowledge Gap Report — {start} to {end}"

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    lines = [
        title,
        f"_Generated: {generated}_",
        "",
        f"**Total gaps:** {len(gaps)}",
        "",
    ]

    if not gaps:
        lines.append("_No low-quality answers recorded in this period._")
        return "\n".join(lines)

    # Group by inferred topic
    by_topic: dict[str, list[dict]] = defaultdict(list)
    for gap in gaps:
        topic = _infer_topic(gap["redacted_question"])
        by_topic[topic].append(gap)

    topic_order = ["resume", "interview", "career_plan", "salary", "general"]
    for topic in topic_order:
        items = by_topic.get(topic, [])
        if not items:
            continue
        lines.append(f"## {topic.replace('_', ' ').title()} ({len(items)})")
        lines.append("")
        lines.append("| Occurrences | Score | Question | Agent | Trigger | Status |")
        lines.append("|-------------|-------|----------|-------|---------|--------|")
        for g in items:
            q = g["redacted_question"].replace("|", "｜")[:80]
            score = f"{g['quality_score']:.1f}" if g["quality_score"] is not None else "—"
            lines.append(
                f"| {g['occurrences']} | {score} | {q} | {g['agent_name']} | {g['trigger']} | {g['status']} |"
            )
        lines.append("")

    # Repeat-offenders section (occurrences ≥ 3)
    repeats = [g for g in gaps if g["occurrences"] >= 3]
    if repeats:
        lines.append("## Repeat Offenders (occurrences ≥ 3)")
        lines.append("")
        for g in repeats:
            lines.append(f"- **[{g['occurrences']}×]** {g['redacted_question'][:100]}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Knowledge gap daily summary")
    parser.add_argument("--date", default=date.today().isoformat(), help="Target date (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=1, help="Number of days to include (default: 1)")
    parser.add_argument("--dry-run", action="store_true", help="Print report to stdout only")
    args = parser.parse_args()

    target_date = date.fromisoformat(args.date)
    print(f"Fetching knowledge gaps for {target_date} (window: {args.days} day(s))...")

    try:
        gaps = fetch_gaps(target_date, args.days)
    except Exception as exc:
        print(f"ERROR: Could not connect to database: {exc}")
        print("Is the KB API database running? Check DATABASE_URL env var.")
        raise SystemExit(1)

    print(f"Found {len(gaps)} gap(s).")
    report = render_report(gaps, target_date, args.days)

    if args.dry_run:
        print("\n" + report)
        return

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{target_date.isoformat()}.md"
    out_path.write_text(report, encoding="utf-8")
    print(f"Report written to {out_path}")


if __name__ == "__main__":
    main()
