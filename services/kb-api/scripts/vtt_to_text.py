#!/usr/bin/env python3
"""Convert WebVTT subtitle files to clean plain text, one file per video."""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SUBTITLE_DIR = REPO_ROOT / "data" / "subtitles"
TEXT_DIR = REPO_ROOT / "data" / "processed" / "transcripts"

# Prefer zh-TW, fall back to zh-Hant, zh, en
LANG_PRIORITY = ["zh-TW", "zh-Hant", "zh", "en"]

_TIMESTAMP_RE = re.compile(
    r"\d{2}:\d{2}:\d{2}\.\d{3} --> \d{2}:\d{2}:\d{2}\.\d{3}.*"
)
_TAG_RE = re.compile(r"<[^>]+>")

def clean_vtt(vtt_path: Path) -> str:
    lines = vtt_path.read_text(encoding="utf-8", errors="replace").splitlines()
    chunks: list[str] = []
    skip = True  # skip WEBVTT header block
    for line in lines:
        if line.startswith("WEBVTT"):
            skip = False
            continue
        if _TIMESTAMP_RE.match(line):
            skip = False
            continue
        if line.strip() == "" or line.strip().isdigit():
            skip = True
            continue
        if not skip:
            cleaned = _TAG_RE.sub("", line).strip()
            if cleaned:
                chunks.append(cleaned)

    # Deduplicate consecutive identical lines (auto-caption artifact)
    deduped: list[str] = []
    prev = ""
    for chunk in chunks:
        if chunk != prev:
            deduped.append(chunk)
        prev = chunk

    return "\n".join(deduped)


def best_vtt(stem_prefix: str) -> Path | None:
    for lang in LANG_PRIORITY:
        candidates = list(SUBTITLE_DIR.glob(f"{stem_prefix}*.{lang}.vtt"))
        if candidates:
            return candidates[0]
    return None


def video_id_from_filename(name: str) -> str:
    parts = name.split("_")
    return parts[1] if len(parts) >= 2 else name


def main(force: bool = False) -> None:
    TEXT_DIR.mkdir(parents=True, exist_ok=True)

    # Group vtt files by video id
    vtts: dict[str, list[Path]] = {}
    for f in SUBTITLE_DIR.glob("*.vtt"):
        vid_id = video_id_from_filename(f.name)
        vtts.setdefault(vid_id, []).append(f)

    converted = 0
    skipped = 0
    for vid_id, paths in vtts.items():
        out_path = TEXT_DIR / f"{vid_id}.txt"
        if out_path.exists() and not force:
            skipped += 1
            continue

        # Pick best language
        chosen: Path | None = None
        for lang in LANG_PRIORITY:
            for p in paths:
                if f".{lang}.vtt" in p.name:
                    chosen = p
                    break
            if chosen:
                break
        if not chosen:
            chosen = paths[0]

        text = clean_vtt(chosen)
        if text.strip():
            out_path.write_text(text, encoding="utf-8")
            converted += 1

    print(f"Converted: {converted}  Skipped (already exist): {skipped}")
    print(f"Output dir: {TEXT_DIR}")


if __name__ == "__main__":
    force = "--force" in sys.argv
    main(force=force)
