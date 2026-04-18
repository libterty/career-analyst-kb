#!/usr/bin/env python3
"""YouTube transcript ingestion pipeline.

Usage:
    python scripts/ingest_youtube.py [--incremental] [--dry-run]

Flow:
    data/subtitles/*.vtt
        ↓  vtt_to_text.py  (run separately, or auto if missing)
    data/processed/transcripts/*.txt
        ↓  CareerChunker   → TranscriptChunk[]
        ↓  EmbeddingService → Milvus (career_kb collection)

Flags:
    --incremental  Skip videos already in Milvus (by video_id prefix in chunk_id)
    --dry-run      Parse and chunk without writing to Milvus
"""
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from loguru import logger

from src.ingestion.career_chunker import CareerChunker, TranscriptChunk
from src.ingestion.chunker import Chunk  # domain Chunk accepted by EmbeddingService

TRANSCRIPT_DIR = ROOT / "data" / "processed" / "transcripts"
SUBTITLE_DIR = ROOT / "data" / "subtitles"

# Filename pattern: {upload_date}_{video_id}_{title}.txt  (vtt_to_text output)
# The plain txt files use just {video_id}.txt (see vtt_to_text.py)

def _video_id_from_stem(stem: str) -> str:
    return stem  # vtt_to_text.py saves as {video_id}.txt


def _title_and_date_from_vtt(video_id: str) -> tuple[str, str]:
    """Look up title and upload_date from the original VTT filename."""
    candidates = list(SUBTITLE_DIR.glob(f"*_{video_id}_*.vtt"))
    if not candidates:
        return "", ""
    name = candidates[0].stem  # e.g. 20260417_pedq5_k3Vpw_【文化假象】...zh-TW
    # strip trailing language suffix (.zh-TW)
    name = re.sub(r"\.[a-z\-]+$", "", name)
    parts = name.split("_", 2)
    upload_date = parts[0] if len(parts) >= 1 else ""
    title = parts[2] if len(parts) >= 3 else ""
    return title, upload_date


def _to_domain_chunk(tc: TranscriptChunk) -> Chunk:
    """Convert TranscriptChunk → domain Chunk accepted by EmbeddingService."""
    doc_hash = hashlib.sha256(tc.video_id.encode()).hexdigest()[:16]
    primary_topic = tc.metadata.get("topics", ["general_career"])[0]
    return Chunk(
        chunk_id=tc.chunk_id,
        doc_hash=doc_hash,
        source=tc.source,
        content=tc.content,
        page_hint=None,
        section=primary_topic,
        token_count=tc.token_count,
        metadata=tc.metadata,
    )


def _existing_video_ids(embedder) -> set[str]:  # type: ignore[type-arg]
    """Query Milvus for distinct video_ids already ingested."""
    try:
        col = embedder._collection
        results = col.query(
            expr="chunk_id != ''",
            output_fields=["chunk_id"],
            limit=16384,
        )
        ids: set[str] = set()
        for r in results:
            cid: str = r["chunk_id"]
            # chunk_id format: {video_id}-{index}
            vid = cid.rsplit("-", 1)[0]
            ids.add(vid)
        return ids
    except Exception as exc:
        logger.warning(f"Could not fetch existing video_ids: {exc}")
        return set()


def _ensure_transcripts() -> None:
    """Run vtt_to_text.py if transcript dir is empty."""
    txts = list(TRANSCRIPT_DIR.glob("*.txt"))
    if not txts:
        logger.info("No transcripts found — running vtt_to_text.py first…")
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "vtt_to_text.py")],
            check=True,
        )


def ingest(incremental: bool, dry_run: bool) -> None:
    _ensure_transcripts()

    txt_files = sorted(TRANSCRIPT_DIR.glob("*.txt"))
    if not txt_files:
        logger.error("No transcript files found in %s", TRANSCRIPT_DIR)
        sys.exit(1)

    logger.info(f"Found {len(txt_files)} transcript files")

    embedder = None
    existing: set[str] = set()

    if not dry_run:
        from src.ingestion.embedder import EmbeddingService
        embedder = EmbeddingService()
        if incremental:
            existing = _existing_video_ids(embedder)
            logger.info(f"Incremental mode: {len(existing)} videos already in Milvus")

    chunker = CareerChunker(max_tokens=400, chunk_overlap=40)
    total_chunks = 0
    total_stored = 0
    skipped = 0

    for txt_path in txt_files:
        video_id = _video_id_from_stem(txt_path.stem)

        if incremental and video_id in existing:
            skipped += 1
            continue

        title, upload_date = _title_and_date_from_vtt(video_id)
        text = txt_path.read_text(encoding="utf-8", errors="replace")

        if not text.strip():
            logger.warning(f"Empty transcript: {txt_path.name}")
            continue

        transcript_chunks = chunker.chunk(
            text=text,
            video_id=video_id,
            title=title,
            upload_date=upload_date,
            source=txt_path.name,
        )
        total_chunks += len(transcript_chunks)

        if dry_run:
            topics = {t for tc in transcript_chunks for t in tc.metadata["topics"]}
            logger.info(
                f"[DRY-RUN] {video_id}: {len(transcript_chunks)} chunks | "
                f"topics={topics}"
            )
            continue

        domain_chunks = [_to_domain_chunk(tc) for tc in transcript_chunks]
        stored = embedder.embed_and_store(domain_chunks)  # type: ignore[union-attr]
        total_stored += stored
        logger.success(f"Stored {stored} chunks for {video_id} ({title[:40]})")

    logger.info(
        f"\n{'='*50}\n"
        f"Ingestion complete\n"
        f"  Files processed : {len(txt_files) - skipped}\n"
        f"  Files skipped   : {skipped}\n"
        f"  Total chunks    : {total_chunks}\n"
        f"  Stored in Milvus: {total_stored}\n"
        f"{'='*50}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest YouTube transcripts into career_kb")
    parser.add_argument("--incremental", action="store_true", help="Skip already-ingested videos")
    parser.add_argument("--dry-run", action="store_true", help="Parse/chunk without writing to Milvus")
    args = parser.parse_args()
    ingest(incremental=args.incremental, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
