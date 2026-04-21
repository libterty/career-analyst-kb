#!/usr/bin/env python3
"""Whisper fallback transcription for videos without subtitles.

Reads video IDs from data/subtitles/no_subtitles.txt, downloads audio-only,
runs Whisper, and saves transcripts to data/processed/transcripts/{video_id}.txt.

Usage:
    pip install mlx-whisper          # Apple Silicon (M1/M2/M3) — recommended
    pip install openai-whisper       # fallback for non-Apple hardware
    python scripts/whisper_fallback.py [--model medium] [--limit N]

Models (mlx-whisper uses HuggingFace repos from mlx-community):
    tiny     — mlx-community/whisper-tiny-mlx
    base     — mlx-community/whisper-base-mlx
    medium   — mlx-community/whisper-medium-mlx       (default, ~40-80x realtime on M3)
    large-v3 — mlx-community/whisper-large-v3-mlx     (best accuracy)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = SERVICE_ROOT.parents[1]
sys.path.insert(0, str(SERVICE_ROOT))

NO_SUB_FILE = REPO_ROOT / "data" / "subtitles" / "no_subtitles.txt"
TRANSCRIPT_DIR = REPO_ROOT / "data" / "processed" / "transcripts"
AUDIO_DIR = REPO_ROOT / "data" / "subtitles" / "audio"


def download_audio(video_id: str, audio_dir: Path) -> Path | None:
    """Download audio-only for a YouTube video. Returns path to downloaded file."""
    out_tmpl = str(audio_dir / f"{video_id}.%(ext)s")
    result = subprocess.run(
        [
            "yt-dlp",
            "--extract-audio",
            "--audio-format", "mp3",
            "--audio-quality", "5",   # 0=best, 9=worst; 5 is good enough for speech
            "--output", out_tmpl,
            "--no-playlist",
            f"https://www.youtube.com/watch?v={video_id}",
        ],
        capture_output=True,
        text=True,
    )
    mp3 = audio_dir / f"{video_id}.mp3"
    if mp3.exists():
        return mp3
    # yt-dlp may produce .m4a or .webm if mp3 conversion fails
    for ext in ("m4a", "webm", "opus"):
        f = audio_dir / f"{video_id}.{ext}"
        if f.exists():
            return f
    print(f"  [WARN] audio download failed for {video_id}: {result.stderr[-200:]}")
    return None


_MLX_MODEL_MAP = {
    "tiny":     "mlx-community/whisper-tiny-mlx",
    "base":     "mlx-community/whisper-base-mlx",
    "small":    "mlx-community/whisper-small-mlx",
    "medium":   "mlx-community/whisper-medium-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
}


def transcribe(audio_path: Path, model: str, language: str) -> str | None:
    """Run Whisper on audio file. Prefers mlx-whisper on Apple Silicon, falls back to openai-whisper."""
    try:
        import mlx_whisper  # type: ignore[import]
        hf_repo = _MLX_MODEL_MAP.get(model, model)
        print(f"  Transcribing {audio_path.name} with mlx-whisper:{model}…")
        result = mlx_whisper.transcribe(
            str(audio_path),
            path_or_hf_repo=hf_repo,
            language=language,
            task="transcribe",
        )
        return result.get("text", "").strip()
    except ImportError:
        pass

    try:
        import whisper  # type: ignore[import]
    except ImportError:
        print("ERROR: neither mlx-whisper nor openai-whisper is installed.")
        print("  Apple Silicon: pip install mlx-whisper")
        print("  Other:         pip install openai-whisper")
        sys.exit(1)

    print(f"  Transcribing {audio_path.name} with openai-whisper:{model}…")
    wm = whisper.load_model(model)
    result = wm.transcribe(str(audio_path), language=language, task="transcribe")
    return result.get("text", "").strip()


def main() -> None:
    parser = argparse.ArgumentParser(description="Whisper fallback for videos without subtitles")
    parser.add_argument("--model", default="medium", help="Whisper model (tiny/base/medium/large-v3)")
    parser.add_argument("--language", default="zh", help="Audio language hint (zh / en)")
    parser.add_argument("--limit", type=int, default=0, help="Max videos to process (0=all)")
    parser.add_argument("--input", default=str(NO_SUB_FILE),
                        help="Path to text file with one video_id per line")
    parser.add_argument("--skip-existing", action="store_true", default=True,
                        help="Skip videos already transcribed (default: True)")
    args = parser.parse_args()

    input_file = Path(args.input)
    if not input_file.exists():
        print(f"Input file not found: {input_file}")
        print("Run: python scripts/audit_subtitles.py first")
        sys.exit(1)

    video_ids = [l.strip() for l in input_file.read_text().splitlines() if l.strip()]
    if args.limit:
        video_ids = video_ids[: args.limit]

    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Videos to transcribe: {len(video_ids)} | model: {args.model}")

    done = skipped = failed = 0
    for vid_id in video_ids:
        out_path = TRANSCRIPT_DIR / f"{vid_id}.txt"
        if args.skip_existing and out_path.exists():
            skipped += 1
            continue

        print(f"\n[{done+1}/{len(video_ids)}] {vid_id}")
        audio = download_audio(vid_id, AUDIO_DIR)
        if not audio:
            failed += 1
            continue

        text = transcribe(audio, model=args.model, language=args.language)
        if text:
            out_path.write_text(text, encoding="utf-8")
            print(f"  Saved: {out_path.name} ({len(text)} chars)")
            audio.unlink(missing_ok=True)  # delete audio after transcription
            done += 1
        else:
            print(f"  Empty transcript for {vid_id}")
            failed += 1

    print(f"\nDone: {done}  Skipped: {skipped}  Failed: {failed}")


if __name__ == "__main__":
    main()
