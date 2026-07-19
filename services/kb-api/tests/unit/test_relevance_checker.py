"""Unit tests for RelevanceChecker (src/rag/relevance_checker.py)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.domain.search_result import SearchResult
from src.rag.relevance_checker import RelevanceChecker, RelevanceResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sr(chunk_id: str, content: str = "職涯建議內容", section: str = "career") -> SearchResult:
    return SearchResult(chunk_id=chunk_id, content=content, source="src", section=section, score=0.9)


def _llm(response_text: str) -> MagicMock:
    mock = MagicMock()
    msg = MagicMock()
    msg.content = response_text
    mock.invoke.return_value = msg
    return mock


def _checker(response_text: str) -> RelevanceChecker:
    return RelevanceChecker(_llm(response_text))


# ---------------------------------------------------------------------------
# chunk count guard
# ---------------------------------------------------------------------------

def test_fewer_than_two_chunks_returns_insufficient():
    checker = _checker("SUFFICIENT")  # LLM should NOT be called
    result = checker.check("如何談薪水？", [_sr("a")])

    assert result.sufficient is False
    assert "不足" in result.missing_aspects[0]
    checker._llm.invoke.assert_not_called()


def test_zero_chunks_returns_insufficient():
    checker = _checker("SUFFICIENT")
    result = checker.check("如何談薪水？", [])

    assert result.sufficient is False
    checker._llm.invoke.assert_not_called()


# ---------------------------------------------------------------------------
# Parsing — SUFFICIENT
# ---------------------------------------------------------------------------

def test_parses_sufficient_verdict():
    result = _checker("SUFFICIENT").check("問題", [_sr("a"), _sr("b")])

    assert result.sufficient is True
    assert result.missing_aspects == []
    assert result.confidence == 0.9


def test_parses_sufficient_with_trailing_whitespace():
    result = _checker("  SUFFICIENT  \n").check("問題", [_sr("a"), _sr("b")])
    assert result.sufficient is True


# ---------------------------------------------------------------------------
# Parsing — INSUFFICIENT
# ---------------------------------------------------------------------------

def test_parses_insufficient_with_aspects():
    response = "INSUFFICIENT\n- 缺乏具體行動步驟\n- 沒有提到新人場景"
    result = _checker(response).check("問題", [_sr("a"), _sr("b")])

    assert result.sufficient is False
    assert result.missing_aspects == ["缺乏具體行動步驟", "沒有提到新人場景"]
    assert result.confidence == 0.9


def test_parses_insufficient_caps_at_three_aspects():
    response = "INSUFFICIENT\n- 面向1\n- 面向2\n- 面向3\n- 面向4"
    result = _checker(response).check("問題", [_sr("a"), _sr("b")])

    assert len(result.missing_aspects) == 3


def test_parses_insufficient_with_no_aspects():
    result = _checker("INSUFFICIENT").check("問題", [_sr("a"), _sr("b")])

    assert result.sufficient is False
    assert result.missing_aspects == []


# ---------------------------------------------------------------------------
# Parsing — <think> tag stripping
# ---------------------------------------------------------------------------

def test_strips_think_tags_before_parsing():
    response = "<think>分析一下...</think>\nSUFFICIENT"
    result = _checker(response).check("問題", [_sr("a"), _sr("b")])
    assert result.sufficient is True


def test_strips_multiline_think_tags():
    response = "<think>\n長長的推理過程\n很多行\n</think>\nINSUFFICIENT\n- 缺少範例"
    result = _checker(response).check("問題", [_sr("a"), _sr("b")])
    assert result.sufficient is False
    assert "缺少範例" in result.missing_aspects


# ---------------------------------------------------------------------------
# Fallback on LLM failure
# ---------------------------------------------------------------------------

def test_llm_exception_returns_sufficient_fallback():
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = RuntimeError("connection timeout")
    checker = RelevanceChecker(mock_llm)

    result = checker.check("問題", [_sr("a"), _sr("b"), _sr("c")])

    assert result.sufficient is True
    assert result.confidence == 0.5


def test_empty_llm_response_returns_sufficient_fallback():
    result = _checker("").check("問題", [_sr("a"), _sr("b")])
    assert result.sufficient is True
    assert result.confidence == 0.5


def test_unknown_verdict_returns_sufficient_fallback():
    result = _checker("MAYBE 不確定").check("問題", [_sr("a"), _sr("b")])
    assert result.sufficient is True
    assert result.confidence == 0.4


# ---------------------------------------------------------------------------
# _build_summary
# ---------------------------------------------------------------------------

def test_build_summary_truncates_long_content():
    long_content = "A" * 200
    chunk = _sr("a", content=long_content, section="履歷")
    summary = RelevanceChecker._build_summary([chunk])

    assert len(summary) < 200
    assert "【履歷】" in summary
    assert "…" in summary


def test_build_summary_omits_empty_section_label():
    chunk = _sr("a", content="內容", section="")
    summary = RelevanceChecker._build_summary([chunk])
    assert "【】" not in summary
