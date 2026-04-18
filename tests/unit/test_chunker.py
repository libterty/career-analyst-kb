"""Unit tests for SmartChunker — Phase 1."""
import pytest
from src.ingestion.chunker import SmartChunker
from src.ingestion.pdf_parser import ParsedDocument


@pytest.fixture
def chunker():
    return SmartChunker(max_tokens=100, chunk_overlap=10)


@pytest.fixture
def sample_doc():
    content = """第一章 天道總論
天道者，宇宙萬物之根本也。一貫道以儒釋道三教為本，五教同源，
引渡有緣眾生返本歸原。求道者須心誠意正，方能得明師一指。

第二章 三寶之義
三寶者，道之根本。玄關竅開，乃通天之路。合同訣印，護身之符。
摩頂禮法，天命之證。三寶合一，方為完整修行。"""
    return ParsedDocument(
        source="test.pdf",
        content=content,
        pages=1,
        metadata={"filename": "test.pdf"},
    )


class TestSmartChunker:
    def test_chunks_non_empty(self, chunker, sample_doc):
        chunks = chunker.chunk(sample_doc)
        assert len(chunks) > 0

    def test_chunk_ids_unique(self, chunker, sample_doc):
        chunks = chunker.chunk(sample_doc)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_chunk_content_not_empty(self, chunker, sample_doc):
        chunks = chunker.chunk(sample_doc)
        for chunk in chunks:
            assert chunk.content.strip()

    def test_doc_hash_preserved(self, chunker, sample_doc):
        chunks = chunker.chunk(sample_doc)
        for chunk in chunks:
            assert chunk.doc_hash == sample_doc.doc_hash

    def test_section_extracted(self, chunker, sample_doc):
        chunks = chunker.chunk(sample_doc)
        sections = [c.section for c in chunks if c.section]
        assert len(sections) > 0
