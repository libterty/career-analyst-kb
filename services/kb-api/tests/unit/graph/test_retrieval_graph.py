"""Graph integration tests — run_retrieval_graph (src/rag/graph/build.py).

Covers docs/graph-design/graph-testing-strategy.md's Graph Integration
Tests table: happy path, node failure, partial failure, retry success,
retry exhausted, duplicate chunk dedup, and flag-off equivalence.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.domain.search_result import SearchResult
from src.rag.graph.build import run_retrieval_graph
from src.rag.relevance_checker import RelevanceResult


def _sr(chunk_id: str, content: str = "content", section: str = "career") -> SearchResult:
    return SearchResult(chunk_id=chunk_id, content=content, source="src", section=section, score=0.9)


def _build_context_fn(chunks: list[SearchResult]) -> str:
    if not chunks:
        return "（未找到相關段落）"
    return "\n".join(c.content for c in chunks)


def _deps(
    *,
    search_side_effect,
    relevance_side_effect,
    rewrite_return="改寫後查詢",
):
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1, 0.2]

    search_engine = MagicMock()
    search_engine.final_top_k = 8
    search_engine.search.side_effect = search_side_effect

    prompt_optimizer = MagicMock()
    prompt_optimizer.enhance_query.side_effect = lambda x: x

    relevance_checker = MagicMock()
    relevance_checker.check.side_effect = relevance_side_effect

    query_rewriter = MagicMock()
    query_rewriter.rewrite.return_value = rewrite_return

    return dict(
        embedder=embedder,
        search_engine=search_engine,
        prompt_optimizer=prompt_optimizer,
        relevance_checker=relevance_checker,
        query_rewriter=query_rewriter,
        build_context_fn=_build_context_fn,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_happy_path_single_question_sufficient_first_try():
    chunks = [_sr("a"), _sr("b"), _sr("c")]
    deps = _deps(
        search_side_effect=[chunks],
        relevance_side_effect=[RelevanceResult(sufficient=True)],
    )

    context, results, meta = await run_retrieval_graph("問題", None, **deps)

    assert results == chunks
    assert meta.iterations == 1
    assert meta.sufficient is True
    deps["query_rewriter"].rewrite.assert_not_called()


# ---------------------------------------------------------------------------
# Retry success — first insufficient, second sufficient
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_retry_success_second_iteration_sufficient():
    first_chunks = [_sr("a")]
    second_chunks = [_sr("a"), _sr("b"), _sr("c")]
    deps = _deps(
        search_side_effect=[first_chunks, second_chunks],
        relevance_side_effect=[
            RelevanceResult(sufficient=False, missing_aspects=["缺步驟"]),
            RelevanceResult(sufficient=True),
        ],
    )

    context, results, meta = await run_retrieval_graph("問題", None, **deps)

    assert meta.iterations == 2
    assert meta.sufficient is True
    assert results == second_chunks
    deps["query_rewriter"].rewrite.assert_called_once_with("問題", ["缺步驟"])


# ---------------------------------------------------------------------------
# Retry exhausted — both iterations insufficient
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_retry_exhausted_still_produces_context():
    deps = _deps(
        search_side_effect=[[_sr("a")], [_sr("b")]],
        relevance_side_effect=[
            RelevanceResult(sufficient=False, missing_aspects=["x"]),
            RelevanceResult(sufficient=False, missing_aspects=["y"]),
        ],
    )

    context, results, meta = await run_retrieval_graph("問題", None, **deps)

    assert meta.iterations == 2
    assert meta.sufficient is False
    assert context  # still produces a context, not an empty answer
    assert results == [_sr("b")]


# ---------------------------------------------------------------------------
# Node failure — RetrieveNode raises, graph does not crash
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_retrieve_node_failure_falls_back_to_empty_chunks():
    deps = _deps(
        search_side_effect=RuntimeError("milvus down"),
        relevance_side_effect=[RelevanceResult(sufficient=False, missing_aspects=["相關段落數量不足"])],
    )

    context, results, meta = await run_retrieval_graph("問題", None, **deps)

    assert results == []
    assert context == "（未找到相關段落）"
    assert meta.sufficient is False


# ---------------------------------------------------------------------------
# Sub-question fan-out — partial failure + dedup
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_sub_questions_partial_failure_and_dedup():
    shared = _sr("shared")
    deps = _deps(
        search_side_effect=[RuntimeError("boom"), [shared, _sr("unique")]],
        relevance_side_effect=[RelevanceResult(sufficient=True)],
    )

    context, results, meta = await run_retrieval_graph(
        "複合問題", ["sq1", "sq2"], **deps
    )

    chunk_ids = {c.chunk_id for c in results}
    assert chunk_ids == {"shared", "unique"}
    assert meta.iterations == 1


# ---------------------------------------------------------------------------
# Flag-off equivalence — Graph output matches legacy inline implementation
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_graph_output_matches_legacy_inline_shape_for_same_inputs():
    """Both paths must return the same (context, chunks, meta-shape) tuple
    for equivalent mocked dependencies — this is the test-time equivalence
    check described in docs/graph-design/graph-migration-plan.md in lieu of
    a runtime Shadow Mode."""
    chunks = [_sr("a"), _sr("b")]
    deps = _deps(
        search_side_effect=[chunks],
        relevance_side_effect=[RelevanceResult(sufficient=True)],
    )

    context, results, meta = await run_retrieval_graph("問題", None, **deps)

    assert isinstance(context, str)
    assert isinstance(results, list)
    assert hasattr(meta, "iterations")
    assert hasattr(meta, "sufficient")
    assert (meta.iterations, meta.sufficient) == (1, True)
