"""Unit tests for Agentic RAG Retrieval Graph nodes (src/rag/graph/nodes.py).

All infrastructure (embedder, search engine, relevance checker, query
rewriter) is mocked — these tests only verify each Node's adapter
behaviour (delegation, fallback, error handling), not the business
logic already covered by test_relevance_checker.py / test_query_rewriter.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.core.domain.search_result import SearchResult
from src.rag.graph import nodes
from src.rag.graph.state import RetrievalGraphState
from src.rag.relevance_checker import RelevanceResult


def _sr(chunk_id: str, content: str = "content", section: str = "career") -> SearchResult:
    return SearchResult(chunk_id=chunk_id, content=content, source="src", section=section, score=0.9)


# ---------------------------------------------------------------------------
# enhance_query_node
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_enhance_query_node_delegates_to_prompt_optimizer():
    state = RetrievalGraphState.new("原始問題")
    optimizer = MagicMock()
    optimizer.enhance_query.return_value = "強化後的問題"

    updates = await nodes.enhance_query_node(state, prompt_optimizer=optimizer)

    assert updates == {"normalized_input": "強化後的問題"}
    optimizer.enhance_query.assert_called_once_with("原始問題")


@pytest.mark.anyio
async def test_enhance_query_node_fallback_on_error():
    state = RetrievalGraphState.new("原始問題")
    optimizer = MagicMock()
    optimizer.enhance_query.side_effect = RuntimeError("boom")

    updates = await nodes.enhance_query_node(state, prompt_optimizer=optimizer)

    assert updates == {"normalized_input": "原始問題"}


# ---------------------------------------------------------------------------
# single_retrieve_node / retrieve_node
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_single_retrieve_node_returns_chunks():
    chunks = [_sr("a"), _sr("b")]
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1, 0.2]
    search_engine = MagicMock()
    search_engine.search.return_value = chunks

    state_with_norm = RetrievalGraphState.new("問題")
    object.__setattr__(state_with_norm, "normalized_input", "強化後")

    updates = await nodes.single_retrieve_node(
        state_with_norm, embedder=embedder, search_engine=search_engine
    )

    assert updates["chunk_pool"] == tuple(chunks)
    search_engine.search.assert_called_once_with("強化後", [0.1, 0.2], topic=None)


@pytest.mark.anyio
async def test_single_retrieve_node_explicit_query_overrides_state():
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1]
    search_engine = MagicMock()
    search_engine.search.return_value = []

    state = RetrievalGraphState.new("問題")
    await nodes.single_retrieve_node(state, embedder=embedder, search_engine=search_engine, query="改寫後查詢")

    search_engine.search.assert_called_once_with("改寫後查詢", [0.1], topic=None)


# ---------------------------------------------------------------------------
# fanout_retrieve_node — sub-question parallel retrieval + merge
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_fanout_retrieve_node_merges_and_dedupes():
    shared = _sr("shared")
    unique_a = _sr("a")
    unique_b = _sr("b")

    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1]
    search_engine = MagicMock()
    search_engine.final_top_k = 8
    # sub-question 1 → [shared, a]; sub-question 2 → [shared, b]
    search_engine.search.side_effect = [[shared, unique_a], [shared, unique_b]]

    optimizer = MagicMock()
    optimizer.enhance_query.side_effect = lambda x: x

    state = RetrievalGraphState.new("複合問題", sub_questions=["sq1", "sq2"])

    updates = await nodes.fanout_retrieve_node(
        state, embedder=embedder, search_engine=search_engine, prompt_optimizer=optimizer
    )

    chunk_ids = [c.chunk_id for c in updates["chunk_pool"]]
    assert chunk_ids.count("shared") == 1
    assert set(chunk_ids) == {"shared", "a", "b"}
    assert search_engine.search.call_count == 2


@pytest.mark.anyio
async def test_fanout_retrieve_node_partial_failure_does_not_fail_whole_node():
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1]
    search_engine = MagicMock()
    search_engine.final_top_k = 8
    search_engine.search.side_effect = [RuntimeError("boom"), [_sr("ok")]]

    optimizer = MagicMock()
    optimizer.enhance_query.side_effect = lambda x: x

    state = RetrievalGraphState.new("複合問題", sub_questions=["sq1", "sq2"])

    updates = await nodes.fanout_retrieve_node(
        state, embedder=embedder, search_engine=search_engine, prompt_optimizer=optimizer
    )

    chunk_ids = [c.chunk_id for c in updates["chunk_pool"]]
    assert chunk_ids == ["ok"]


@pytest.mark.anyio
async def test_fanout_retrieve_node_truncates_to_final_top_k():
    embedder = MagicMock()
    embedder.embed_query.return_value = [0.1]
    search_engine = MagicMock()
    search_engine.final_top_k = 2
    search_engine.search.side_effect = [
        [_sr("a"), _sr("b"), _sr("c")],
        [],
    ]
    optimizer = MagicMock()
    optimizer.enhance_query.side_effect = lambda x: x

    state = RetrievalGraphState.new("問題", sub_questions=["sq1", "sq2"])
    updates = await nodes.fanout_retrieve_node(
        state, embedder=embedder, search_engine=search_engine, prompt_optimizer=optimizer
    )

    assert len(updates["chunk_pool"]) == 2


# ---------------------------------------------------------------------------
# relevance_check_node
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_relevance_check_node_sufficient():
    checker = MagicMock()
    checker.check.return_value = RelevanceResult(sufficient=True)

    state = RetrievalGraphState.new("問題")
    object.__setattr__(state, "chunk_pool", (_sr("a"), _sr("b")))

    updates = await nodes.relevance_check_node(state, relevance_checker=checker)

    assert updates == {"relevance_sufficient": True, "missing_aspects": ()}
    checker.check.assert_called_once_with("問題", [state.chunk_pool[0], state.chunk_pool[1]])


@pytest.mark.anyio
async def test_relevance_check_node_insufficient_with_missing_aspects():
    checker = MagicMock()
    checker.check.return_value = RelevanceResult(sufficient=False, missing_aspects=["缺具體步驟"])

    state = RetrievalGraphState.new("問題")

    updates = await nodes.relevance_check_node(state, relevance_checker=checker)

    assert updates["relevance_sufficient"] is False
    assert updates["missing_aspects"] == ("缺具體步驟",)


# ---------------------------------------------------------------------------
# rewrite_query_node
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_rewrite_query_node_increments_retry_count():
    rewriter = MagicMock()
    rewriter.rewrite.return_value = "改寫後查詢"

    state = RetrievalGraphState.new("問題")
    object.__setattr__(state, "missing_aspects", ("缺步驟",))

    updates = await nodes.rewrite_query_node(state, query_rewriter=rewriter)

    assert updates == {"normalized_input": "改寫後查詢", "retry_count": 1}
    rewriter.rewrite.assert_called_once_with("問題", ["缺步驟"])


# ---------------------------------------------------------------------------
# build_context_node
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_build_context_node_delegates_and_sets_status():
    state = RetrievalGraphState.new("問題")
    object.__setattr__(state, "chunk_pool", (_sr("a"),))

    build_fn = MagicMock(return_value="組裝後的 context")
    updates = await nodes.build_context_node(state, build_context_fn=build_fn)

    assert updates == {"final_context": "組裝後的 context", "status": "succeeded"}
    build_fn.assert_called_once_with([state.chunk_pool[0]])
