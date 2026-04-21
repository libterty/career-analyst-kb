"""Chunker specialised for YouTube career transcripts.

Differences from the generic SmartChunker:
- Input is plain text (no PDF page breaks or section headers).
- Separators optimised for spoken-language transcripts: sentence endings,
  clause boundaries (，。！？), rather than document structure markers.
- Each chunk is tagged with career topics via career_classifier.
- Metadata includes video_id, upload_date, title, and topics.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import tiktoken
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

from .career_classifier import classify

# Spoken Mandarin sentence / clause boundaries, in priority order.
_TRANSCRIPT_SEPARATORS = [
    "。", "！", "？",   # full-stop equivalents
    "…",               # ellipsis (spoken hesitation)
    "，",              # comma — last resort before character split
    "\n",
    " ",
    "",
]

_ENCODING = "cl100k_base"


@dataclass
class TranscriptChunk:
    chunk_id: str
    video_id: str
    source: str         # original .txt filename
    content: str
    token_count: int
    metadata: dict = field(default_factory=dict)
    # metadata will include: title, upload_date, topics, chunk_index, total_chunks


class CareerChunker:
    """Split a YouTube transcript into RAG-ready chunks with topic tags."""

    def __init__(self, max_tokens: int = 400, chunk_overlap: int = 40) -> None:
        self._enc = tiktoken.get_encoding(_ENCODING)
        self._splitter = RecursiveCharacterTextSplitter(
            separators=_TRANSCRIPT_SEPARATORS,
            chunk_size=max_tokens,
            chunk_overlap=chunk_overlap,
            length_function=self._token_len,
            is_separator_regex=False,
        )

    def chunk(
        self,
        text: str,
        video_id: str,
        title: str = "",
        upload_date: str = "",
        source: str = "",
    ) -> list[TranscriptChunk]:
        raw = self._splitter.split_text(text)
        chunks: list[TranscriptChunk] = []

        for idx, piece in enumerate(raw):
            piece = piece.strip()
            if not piece:
                continue

            classification = classify(piece)
            chunk_id = f"{video_id}-{idx:04d}"
            chunks.append(
                TranscriptChunk(
                    chunk_id=chunk_id,
                    video_id=video_id,
                    source=source or f"{video_id}.txt",
                    content=piece,
                    token_count=self._token_len(piece),
                    metadata={
                        "title": title,
                        "upload_date": upload_date,
                        "topics": classification.topics,
                        "topic_confidence": classification.confidence,
                        "chunk_index": idx,
                        "total_chunks": len(raw),
                    },
                )
            )

        logger.info(
            f"[CareerChunker] {video_id}: {len(chunks)} chunks "
            f"(title={title[:30]}...)"
        )
        return chunks

    def _token_len(self, text: str) -> int:
        return len(self._enc.encode(text))
