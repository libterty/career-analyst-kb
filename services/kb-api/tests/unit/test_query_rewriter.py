"""Unit tests for QueryRewriter (src/rag/query_rewriter.py)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.rag.query_rewriter import QueryRewriter, _cosine_similarity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _llm(response_text: str) -> MagicMock:
    mock = MagicMock()
    msg = MagicMock()
    msg.content = response_text
    mock.invoke.return_value = msg
    return mock


def _embedder(vectors: dict[str, list[float]] | None = None) -> MagicMock:
    """Mock embedder that returns preset vectors or orthogonal defaults."""
    mock = MagicMock()
    if vectors:
        mock.embed_query.side_effect = lambda text: vectors.get(text, [0.0, 1.0])
    else:
        # Default: original=[1,0], rewritten=[0,1] → cosine=0, always different
        mock.embed_query.side_effect = lambda text: [1.0, 0.0] if text == "original" else [0.0, 1.0]
    return mock


def _rewriter(response_text: str, embedder=None) -> QueryRewriter:
    return QueryRewriter(_llm(response_text), embedder or _embedder())


# ---------------------------------------------------------------------------
# _cosine_similarity
# ---------------------------------------------------------------------------

def test_cosine_identical_vectors():
    assert _cosine_similarity([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)


def test_cosine_orthogonal_vectors():
    assert _cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)


def test_cosine_zero_vector_returns_zero():
    assert _cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


# ---------------------------------------------------------------------------
# No missing aspects → skip rewrite
# ---------------------------------------------------------------------------

def test_no_missing_aspects_returns_original():
    rewriter = _rewriter("改寫後的查詢")
    result = rewriter.rewrite("如何談薪水？", missing_aspects=[])

    assert result == "如何談薪水？"
    rewriter._llm.invoke.assert_not_called()


# ---------------------------------------------------------------------------
# Successful rewrite
# ---------------------------------------------------------------------------

def test_rewrite_returns_llm_output():
    rewriter = _rewriter("如何在新人階段透過具體行動建立主管信任")
    result = rewriter.rewrite("original", missing_aspects=["具體行動步驟"])

    assert result == "如何在新人階段透過具體行動建立主管信任"


def test_rewrite_strips_quotes():
    rewriter = _rewriter("「改寫後的查詢」")
    result = rewriter.rewrite("original", missing_aspects=["某面向"])

    assert result == "改寫後的查詢"


# ---------------------------------------------------------------------------
# Cosine similarity protection
# ---------------------------------------------------------------------------

def test_cosine_too_similar_returns_original():
    original = "如何談薪水"
    rewritten = "薪水如何談"
    similar_vec = [1.0, 0.0]  # same vector → cosine=1.0 > 0.85

    embedder = MagicMock()
    embedder.embed_query.return_value = similar_vec

    rewriter = QueryRewriter(_llm(rewritten), embedder)
    result = rewriter.rewrite(original, missing_aspects=["某面向"])

    assert result == original


def test_cosine_different_enough_returns_rewritten():
    original = "original"
    rewritten = "新的不同查詢方向"

    # original → [1,0], rewritten → [0,1] → cosine=0.0 < 0.85
    embedder = _embedder({original: [1.0, 0.0], rewritten: [0.0, 1.0]})

    rewriter = QueryRewriter(_llm(rewritten), embedder)
    result = rewriter.rewrite(original, missing_aspects=["某面向"])

    assert result == rewritten


# ---------------------------------------------------------------------------
# Fallback on LLM failure
# ---------------------------------------------------------------------------

def test_llm_exception_returns_original():
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = RuntimeError("connection timeout")
    rewriter = QueryRewriter(mock_llm, _embedder())

    result = rewriter.rewrite("如何談薪水？", missing_aspects=["具體步驟"])

    assert result == "如何談薪水？"


def test_llm_returns_empty_string_returns_original():
    rewriter = _rewriter("   ")
    result = rewriter.rewrite("如何談薪水？", missing_aspects=["具體步驟"])

    assert result == "如何談薪水？"


def test_llm_returns_same_as_original_returns_original():
    original = "如何談薪水？"
    rewriter = _rewriter(original)
    result = rewriter.rewrite(original, missing_aspects=["某面向"])

    assert result == original


# ---------------------------------------------------------------------------
# Embed failure during similarity check
# ---------------------------------------------------------------------------

def test_embed_failure_still_returns_rewritten():
    """embed 失敗時不阻斷，仍使用改寫結果。"""
    mock_embedder = MagicMock()
    mock_embedder.embed_query.side_effect = RuntimeError("ollama down")

    rewriter = QueryRewriter(_llm("改寫後的查詢"), mock_embedder)
    result = rewriter.rewrite("original", missing_aspects=["某面向"])

    assert result == "改寫後的查詢"
