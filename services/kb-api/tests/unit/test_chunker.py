"""Unit tests for SmartChunker — Phase 1."""
import pytest
from src.ingestion.chunker import SmartChunker
from src.ingestion.pdf_parser import ParsedDocument


@pytest.fixture
def chunker():
    return SmartChunker(max_tokens=100, chunk_overlap=10)


@pytest.fixture
def sample_doc():
    content = """第一章 履歷撰寫技巧
一份好的履歷需要清楚呈現個人價值。成功求職者通常能在履歷中展現量化成果，
讓面試官快速掌握應徵者的核心競爭力與專業背景。

第二章 面試準備策略
面試前的準備至關重要。應徵者應研究目標公司文化、準備 STAR 法則的具體案例，
並事先練習常見問題，才能在面試中展現自信與專業。"""
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
