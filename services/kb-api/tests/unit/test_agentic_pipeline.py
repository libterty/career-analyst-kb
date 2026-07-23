"""Unit tests for AgenticRAGPipeline (src/rag/agentic_pipeline.py).

Infrastructure (Milvus, LLM, embedder) is fully mocked.
Tests cover the self-reflection loop logic and sub_questions merging.
"""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub heavy dependencies before importing the pipeline
# ---------------------------------------------------------------------------
for _mod in [
    "src.core.llm_factory",
    "src.ingestion.embedder",
    "src.core.tracing",
    "src.finetuning.prompt_optimizer",
]:
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

sys.modules["src.core.llm_factory"].build_llm = MagicMock(return_value=MagicMock())
sys.modules["src.core.llm_factory"].build_fast_llm = MagicMock(return_value=MagicMock())
sys.modules["src.core.tracing"].langfuse_trace_id_var = MagicMock(get=MagicMock(return_value=None))
sys.modules["src.core.tracing"].langfuse_client = MagicMock(return_value=None)
sys.modules["src.finetuning.prompt_optimizer"].PromptOptimizer = MagicMock(
    return_value=MagicMock(enhance_query=MagicMock(side_effect=lambda x: x))
)

from src.core.domain.search_result import SearchResult
from src.rag.agentic_pipeline import AgenticRAGPipeline, RetrievalMeta, _build_context
from src.rag.relevance_checker import RelevanceResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sr(chunk_id: str, content: str = "職涯建議", section: str = "career") -> SearchResult:
    return SearchResult(chunk_id=chunk_id, content=content, source="src", section=section, score=0.9)


def _make_pipeline(
    chunks: list[SearchResult],
    *,
    relevant: bool = True,
    missing_aspects: list[str] | None = None,
    rewritten_query: str | None = None,
    llm_tokens: list[str] | None = None,
) -> AgenticRAGPipeline:
    """Build AgenticRAGPipeline with all infra mocked."""
    pipeline = object.__new__(AgenticRAGPipeline)

    # Embedder
    pipeline._embedder = MagicMock()
    pipeline._embedder.embed_query.return_value = [0.1, 0.2]

    # HybridSearchEngine
    pipeline._search = MagicMock()
    pipeline._search.final_top_k = 8
    pipeline._search.search.return_value = chunks

    # PromptOptimizer
    pipeline._prompt_optimizer = MagicMock()
    pipeline._prompt_optimizer.enhance_query.side_effect = lambda x: x

    # RelevanceChecker — first call uses `relevant`, subsequent calls return sufficient=True
    relevance_result = RelevanceResult(
        sufficient=relevant,
        missing_aspects=missing_aspects or [],
    )
    sufficient_result = RelevanceResult(sufficient=True)
    pipeline._relevance_checker = MagicMock()
    pipeline._relevance_checker.check.side_effect = [relevance_result, sufficient_result]

    # QueryRewriter
    pipeline._query_rewriter = MagicMock()
    pipeline._query_rewriter.rewrite.return_value = rewritten_query or "改寫後的查詢"

    # LLM — async generator
    tokens = llm_tokens or ["回答", "內容"]

    async def _fake_astream(messages):
        chunk = MagicMock()
        for t in tokens:
            chunk.content = t
            yield chunk

    pipeline._llm = MagicMock()
    pipeline._llm.astream = _fake_astream

    # Memory
    pipeline._memory = MagicMock()
    pipeline._memory.load_memory_variables.return_value = {"history": ""}
    pipeline._memory.save_context = MagicMock()

    pipeline._last_meta = RetrievalMeta(iterations=1, sufficient=True)

    return pipeline


# ---------------------------------------------------------------------------
# _build_context (static)
# ---------------------------------------------------------------------------

def test_build_context_empty():
    assert _build_context([]) == "（未找到相關段落）"


def test_build_context_with_section():
    result = _build_context([_sr("a", "content", section="薪資")])
    assert "[1]" in result
    assert "【薪資】" in result
    assert "content" in result


def test_build_context_no_section():
    result = _build_context([_sr("a", "content", section="")])
    assert "【】" not in result


# ---------------------------------------------------------------------------
# Self-Reflection Loop — single iteration (sufficient on first check)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_query_sufficient_on_first_check():
    chunks = [_sr(str(i)) for i in range(3)]
    pipeline = _make_pipeline(chunks, relevant=True)

    tokens = [t async for t in pipeline.query("如何談薪水？")]

    assert tokens == ["回答", "內容"]
    meta = pipeline.get_last_retrieval_meta()
    assert meta.iterations == 1
    assert meta.sufficient is True
    pipeline._relevance_checker.check.assert_called_once()
    pipeline._query_rewriter.rewrite.assert_not_called()


# ---------------------------------------------------------------------------
# Self-Reflection Loop — two iterations (insufficient → rewrite → sufficient)
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_query_insufficient_triggers_rewrite_and_second_iteration():
    chunks = [_sr(str(i)) for i in range(3)]
    pipeline = _make_pipeline(
        chunks,
        relevant=False,
        missing_aspects=["具體行動步驟"],
        rewritten_query="新的改寫查詢",
    )

    tokens = [t async for t in pipeline.query("如何談薪水？")]

    assert tokens == ["回答", "內容"]
    meta = pipeline.get_last_retrieval_meta()
    assert meta.iterations == 2
    # RelevanceChecker called twice (first: insufficient, second: sufficient)
    assert pipeline._relevance_checker.check.call_count == 2
    pipeline._query_rewriter.rewrite.assert_called_once_with("如何談薪水？", ["具體行動步驟"])
    assert pipeline._search.search.call_count == 2


# ---------------------------------------------------------------------------
# get_last_retrieval_meta
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_get_last_retrieval_meta_reflects_last_query():
    pipeline = _make_pipeline([_sr("a"), _sr("b"), _sr("c")], relevant=True)
    _ = [t async for t in pipeline.query("問題")]
    meta = pipeline.get_last_retrieval_meta()
    assert isinstance(meta, RetrievalMeta)
    assert meta.iterations >= 1


# ---------------------------------------------------------------------------
# sub_questions — chunk pool merging
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_sub_questions_calls_search_per_sub_question():
    chunks = [_sr("a"), _sr("b")]
    pipeline = _make_pipeline(chunks, relevant=True)

    sub_qs = ["sub question 1", "sub question 2"]
    _ = [t async for t in pipeline.query("複合問題", sub_questions=sub_qs)]

    # search called once per sub-question (not for main question)
    assert pipeline._search.search.call_count == len(sub_qs)


@pytest.mark.anyio
async def test_sub_questions_deduplicates_chunks():
    # Both sub-questions return the same chunk — it should appear only once in pool
    shared_chunk = _sr("shared", "共用段落")
    pipeline = _make_pipeline([shared_chunk], relevant=True)

    _ = [t async for t in pipeline.query("問題", sub_questions=["sq1", "sq2"])]

    # RelevanceChecker receives deduplicated pool
    call_args = pipeline._relevance_checker.check.call_args
    chunks_passed = call_args[0][1]
    chunk_ids = [c.chunk_id for c in chunks_passed]
    assert chunk_ids.count("shared") == 1


# ---------------------------------------------------------------------------
# Memory — conversation context saved after response
# ---------------------------------------------------------------------------

@pytest.mark.anyio
async def test_memory_saved_after_response():
    pipeline = _make_pipeline([_sr("a"), _sr("b"), _sr("c")], relevant=True)
    _ = [t async for t in pipeline.query("問題", session_id="s1")]
    pipeline._memory.save_context.assert_called_once()
    saved_input = pipeline._memory.save_context.call_args[0][0]
    assert saved_input["input"] == "問題"


# ---------------------------------------------------------------------------
# ChatResponseDTO defaults — agentic=False path unaffected
# ---------------------------------------------------------------------------

def test_chat_response_dto_defaults():
    from src.application.dto.chat_dto import ChatResponseDTO
    dto = ChatResponseDTO(answer="答案", session_id="s1")
    assert dto.retrieval_iterations == 1
    assert dto.relevance_sufficient is True


def test_chat_request_dto_agentic_default_false():
    from src.application.dto.chat_dto import ChatRequestDTO
    dto = ChatRequestDTO(question="問題")
    assert dto.agentic is False
    assert dto.sub_questions == []
