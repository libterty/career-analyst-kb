#!/usr/bin/env python3
"""Audit downloaded subtitles: count coverage, list missing videos."""
import re
from pathlib import Path
from collections import defaultdict

SUBTITLE_DIR = Path(__file__).parent.parent / "data" / "subtitles"
LOG_FILE = SUBTITLE_DIR / "download.log"


def parse_log(log_path: Path) -> tuple[int, list[str]]:
    """Return (total_videos, list_of_video_ids_without_subtitles)."""
    total = 0
    no_sub_ids = []
    no_sub_pattern = re.compile(r"There are no subtitles.*?/watch\?v=([A-Za-z0-9_-]+)")
    total_pattern = re.compile(r"Downloading (\d+) items")

    if not log_path.exists():
        return 0, []

    content = log_path.read_text(errors="replace")
    m = total_pattern.search(content)
    if m:
        total = int(m.group(1))

    for m in no_sub_pattern.finditer(content):
        no_sub_ids.append(m.group(1))

    return total, no_sub_ids


def count_vtt_files() -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for f in SUBTITLE_DIR.glob("*.vtt"):
        lang = f.suffixes[-2].lstrip(".") if len(f.suffixes) >= 2 else "unknown"
        counts[lang] += 1
    return dict(counts)


def main() -> None:
    total, no_sub_ids = parse_log(LOG_FILE)
    vtt_counts = count_vtt_files()

    total_vtts = sum(vtt_counts.values())
    print(f"Subtitle directory: {SUBTITLE_DIR}")
    print(f"Total videos in channel: {total or '(run download first)'}")
    print(f"VTT files downloaded:    {total_vtts}")
    if total:
        print(f"Coverage:                {total_vtts / total * 100:.1f}%")
    print()
    print("By language:")
    for lang, count in sorted(vtt_counts.items(), key=lambda x: -x[1]):
        print(f"  {lang:20s} {count}")

    if no_sub_ids:
        print(f"\nVideos without any subtitles ({len(no_sub_ids)}):")
        for vid_id in no_sub_ids:
            print(f"  https://www.youtube.com/watch?v={vid_id}")
        no_sub_path = SUBTITLE_DIR / "no_subtitles.txt"
        no_sub_path.write_text("\n".join(no_sub_ids) + "\n")
        print(f"\nSaved to {no_sub_path} (for Whisper fallback)")
    else:
        print("\nNo missing-subtitle videos detected (or download not yet complete).")


if __name__ == "__main__":
    main()
