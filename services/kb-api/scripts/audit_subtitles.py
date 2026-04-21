#!/usr/bin/env python3
"""Audit downloaded subtitles: count coverage across all tabs, list missing videos."""
import re
from pathlib import Path
from collections import defaultdict

REPO_ROOT = Path(__file__).resolve().parents[2]
SUBTITLE_DIR = REPO_ROOT / "data" / "subtitles"

# One log file per channel tab
TAB_LOGS: dict[str, str] = {
    "videos":   "download.log",
    "shorts":   "download_shorts.log",
    "streams":  "download_streams.log",
    "podcasts": "download_podcasts.log",
}

_TOTAL_RE = re.compile(r"Downloading (\d+) items")
_URL_RE = re.compile(
    r"Extracting URL: https://www\.youtube\.com/(?:watch\?v=|shorts/)([A-Za-z0-9_-]+)"
)


def parse_log(log_path: Path) -> tuple[int, list[str]]:
    """Return (total_in_tab, video_ids_without_subtitles)."""
    if not log_path.exists():
        return 0, []

    lines = log_path.read_text(errors="replace").splitlines()

    m = _TOTAL_RE.search("\n".join(lines[:20]))
    total = int(m.group(1)) if m else 0

    no_sub_ids: list[str] = []
    last_video_id = ""
    for line in lines:
        mu = _URL_RE.search(line)
        if mu:
            last_video_id = mu.group(1)
        elif "There are no subtitles" in line and last_video_id:
            no_sub_ids.append(last_video_id)
            last_video_id = ""

    return total, no_sub_ids


def count_vtt_files() -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for f in SUBTITLE_DIR.glob("*.vtt"):
        lang = f.suffixes[-2].lstrip(".") if len(f.suffixes) >= 2 else "unknown"
        counts[lang] += 1
    return dict(counts)


def main() -> None:
    grand_total = 0
    all_no_sub: list[str] = []

    print(f"Subtitle directory: {SUBTITLE_DIR}\n")
    print(f"{'Tab':<12} {'Total':>6}  {'No-sub':>6}  Status")
    print("-" * 40)

    for tab, log_name in TAB_LOGS.items():
        log_path = SUBTITLE_DIR / log_name
        total, no_sub = parse_log(log_path)
        status = "done" if log_path.exists() and "Finished" in log_path.read_text(errors="replace") else ("in progress" if log_path.exists() else "not started")
        print(f"  {tab:<10} {total:>6}  {len(no_sub):>6}  {status}")
        grand_total += total
        all_no_sub.extend(no_sub)

    vtt_counts = count_vtt_files()
    total_vtts = sum(vtt_counts.values())

    print("-" * 40)
    print(f"  {'TOTAL':<10} {grand_total:>6}  {len(all_no_sub):>6}")
    print(f"\nVTT files on disk:   {total_vtts}")
    if grand_total:
        print(f"Coverage:            {total_vtts / grand_total * 100:.1f}%")

    print("\nBy language:")
    for lang, count in sorted(vtt_counts.items(), key=lambda x: -x[1]):
        print(f"  {lang:<20} {count}")

    # Deduplicate (a video ID might appear across multiple tabs)
    unique_no_sub = list(dict.fromkeys(all_no_sub))
    if unique_no_sub:
        no_sub_path = SUBTITLE_DIR / "no_subtitles.txt"
        no_sub_path.write_text("\n".join(unique_no_sub) + "\n")
        print(f"\nVideos needing Whisper fallback: {len(unique_no_sub)}")
        print(f"Saved to: {no_sub_path}")
    else:
        print("\nNo missing-subtitle videos detected (or downloads not yet complete).")


if __name__ == "__main__":
    main()
