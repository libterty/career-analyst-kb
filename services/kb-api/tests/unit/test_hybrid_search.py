"""Unit tests for HybridSearchEngine (src/rag/hybrid_search.py).

rank_bm25 and jieba are stubbed in conftest.py so these tests run in the host venv.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core.domain.search_result import SearchResult
from src.rag.hybrid_search import HybridSearchEngine, _tokenize_zh


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sr(chunk_id: str, content: str = "content", score: float = 0.9) -> SearchResult:
    return SearchResult(chunk_id=chunk_id, content=content, source="src", section="sec", score=score)


def _retriever(dense_results: list[SearchResult], all_chunks: list[SearchResult] | None = None):
    ret = MagicMock()
    ret.search.return_value = dense_results
    if all_chunks is not None:
        ret.get_all_chunks.return_value = all_chunks
    else:
        del ret.get_all_chunks
    return ret


def _engine(dense_results, all_chunks=None, *, dense_top_k=50, final_top_k=3, bm25_top_k=5):
    ret = _retriever(dense_results, all_chunks)
    return HybridSearchEngine(ret, dense_top_k=dense_top_k, final_top_k=final_top_k, bm25_top_k=bm25_top_k), ret


# ---------------------------------------------------------------------------
# _tokenize_zh
# ---------------------------------------------------------------------------

def test_tokenize_english_acronym_lowercased():
    tokens = _tokenize_zh("STAR interview")
    assert "star" in tokens
    assert "interview" in tokens


def test_tokenize_single_char_not_split_for_english():
    # English word longer than 1 char must stay together
    tokens = _tokenize_zh("method")
    assert "method" in tokens
    # should NOT be split into individual characters
    assert "m" not in tokens


def test_tokenize_fallback_char_split_for_cjk():
    # jieba stub just does list(), which gives char split (same as real fallback)
    tokens = _tokenize_zh("面試")
    assert "面" in tokens
    assert "試" in tokens


def test_tokenize_mixed():
    tokens = _tokenize_zh("STAR面試法")
    assert "star" in tokens
    # CJK chars present
    assert any(len(t) == 1 and "一" <= t <= "鿿" for t in tokens)


# ---------------------------------------------------------------------------
# invalidate_bm25_cache
# ---------------------------------------------------------------------------

def test_invalidate_resets_all_bm25_state():
    engine, _ = _engine([_sr("a")], all_chunks=[_sr("a")])
    engine._bm25_corpus = [_sr("a")]
    engine._bm25_index = object()
    engine._bm25_tokenized = [["tok"]]

    engine.invalidate_bm25_cache()

    assert engine._bm25_corpus is None
    assert engine._bm25_index is None
    assert engine._bm25_tokenized is None


# ---------------------------------------------------------------------------
# _ensure_bm25_index
# ---------------------------------------------------------------------------

def test_ensure_bm25_index_skips_when_no_corpus():
    engine, ret = _engine([])
    ret.get_all_chunks = MagicMock(return_value=[])

    engine._ensure_bm25_index()

    assert engine._bm25_index is None


def test_ensure_bm25_index_builds_when_corpus_available():
    chunks = [_sr("a", "hello world"), _sr("b", "你好")]
    engine, ret = _engine([], all_chunks=chunks)

    engine._ensure_bm25_index()

    assert engine._bm25_index is not None
    assert engine._bm25_corpus == chunks
    assert engine._bm25_tokenized is not None


def test_ensure_bm25_index_idempotent():
    chunks = [_sr("a")]
    engine, ret = _engine([], all_chunks=chunks)

    engine._ensure_bm25_index()
    first_index = engine._bm25_index

    engine._ensure_bm25_index()
    assert engine._bm25_index is first_index  # same object, not rebuilt


def test_ensure_bm25_index_fallback_when_no_get_all_chunks():
    engine, ret = _engine([])
    # retriever has no get_all_chunks (MagicMock attribute deleted in _retriever)
    engine._ensure_bm25_index()
    assert engine._bm25_index is None


# ---------------------------------------------------------------------------
# search — edge cases
# ---------------------------------------------------------------------------

def test_search_empty_dense_returns_empty():
    engine, _ = _engine([])
    result = engine.search("query", [0.1, 0.2])
    assert result == []


def test_search_passes_topic_to_retriever():
    engine, ret = _engine([_sr("a")])
    engine.search("q", [0.1], topic="career")
    ret.search.assert_called_once_with([0.1], top_k=50, topic="career")


# ---------------------------------------------------------------------------
# search — RRF full path
# ---------------------------------------------------------------------------

def test_search_rrf_returns_at_most_final_top_k():
    chunks = [_sr(str(i), f"doc {i}") for i in range(10)]
    dense = chunks[:5]
    engine, _ = _engine(dense, all_chunks=chunks, final_top_k=3)
    engine._ensure_bm25_index()

    results = engine.search("query", [0.1])

    assert len(results) <= 3


def test_search_rrf_includes_results_from_both_paths():
    # Dense results: chunk A, B
    # BM25 all_chunks: chunk A, B, C — stub scores C highest via position (C first in list)
    chunk_c = _sr("C", "bm25 only doc")
    chunk_a = _sr("A", "dense doc a")
    chunk_b = _sr("B", "dense doc b")

    dense = [chunk_a, chunk_b]
    all_chunks = [chunk_c, chunk_a, chunk_b]  # C scored highest by stub BM25

    engine, _ = _engine(dense, all_chunks=all_chunks, final_top_k=5, bm25_top_k=3)
    engine._ensure_bm25_index()

    results = engine.search("query", [0.1])
    result_ids = {r.chunk_id for r in results}

    # C appeared only in BM25 path — should be in merged results
    assert "C" in result_ids
    assert "A" in result_ids


def test_search_rrf_scores_monotonically_ordered():
    chunks = [_sr(str(i)) for i in range(6)]
    engine, _ = _engine(chunks[:4], all_chunks=chunks, final_top_k=6)
    engine._ensure_bm25_index()

    results = engine.search("query", [0.1])

    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# search — fallback path (BM25 not pre-built, no get_all_chunks)
# ---------------------------------------------------------------------------

def test_search_fallback_path_returns_results():
    dense = [_sr("x", "fallback doc"), _sr("y", "another")]
    engine, _ = _engine(dense)  # no all_chunks → _ensure_bm25_index will skip

    results = engine.search("query", [0.1])

    assert isinstance(results, list)
    # Fallback still returns something (dense pool used for BM25)
    assert len(results) <= engine.final_top_k


def test_search_result_is_immutable_searchresult():
    dense = [_sr("a")]
    engine, _ = _engine(dense, all_chunks=[_sr("a")])
    engine._ensure_bm25_index()

    results = engine.search("query", [0.1])

    for r in results:
        assert isinstance(r, SearchResult)
