"""Agentic RAG Retrieval Graph — Node 實作。

每個 Node 是既有物件（PromptOptimizer/HybridSearchEngine/RelevanceChecker/
QueryRewriter）的薄 adapter，不重新實作業務邏輯（見
docs/graph-design/graph-node-contracts.md）。

Node 簽名統一為 `async def xxx_node(state, **deps) -> dict[str, Any]`，
回傳要寫回 state 的欄位 dict；例外由 GraphRunner.step() 統一捕捉分類，
Node 本身不需要 try/except 包住「非預期程式錯誤」，只需要包住
「已知的、有 fallback 策略的」情況（如 LLM 呼叫失敗）。
"""
from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from src.core.domain.search_result import SearchResult
from src.rag.relevance_checker import RelevanceChecker
from src.rag.query_rewriter import QueryRewriter

from .state import RetrievalGraphState

MAX_ITERATIONS = 2
FINAL_TOP_K_DEFAULT = 8


async def enhance_query_node(state: RetrievalGraphState, *, prompt_optimizer) -> dict[str, Any]:
    """術語正規化。失敗時 fallback 回原始問題，不阻斷主流程。"""
    try:
        normalized = prompt_optimizer.enhance_query(state.question)
    except Exception as exc:  # noqa: BLE001 — 有明確 fallback，不視為 non-recoverable
        logger.warning(f"[EnhanceQueryNode] fallback to raw question: {exc}")
        normalized = state.question
    return {"normalized_input": normalized}


async def retrieve_node(
    query: str,
    *,
    embedder,
    search_engine,
    topic: str | None = None,
) -> list[SearchResult]:
    """對單一 query 執行 embed + hybrid search（純函式，不寫 state）。

    平行分支（sub-question fan-out）呼叫此函式時各自傳入獨立的 query，
    結果由呼叫端的 merge_chunks_node 統一寫回 state，避免平行寫入衝突
    （見 docs/graph-design/graph-state-schema.md「平行 Node 如何合併 State」）。
    """
    loop = asyncio.get_running_loop()
    embedding = await loop.run_in_executor(None, embedder.embed_query, query)
    return search_engine.search(query, embedding, topic=topic)


async def fanout_retrieve_node(
    state: RetrievalGraphState,
    *,
    embedder,
    search_engine,
    prompt_optimizer,
    topic: str | None = None,
) -> dict[str, Any]:
    """Sub-question 平行檢索 + Join（合併去重，截斷至 final_top_k）。

    對應 target-graph-design.md 的 `N2P1/N2P2/N2P3 → J1`：多個 RetrieveNode
    平行執行（asyncio.gather），結果只在這個單一 coroutine 內合併寫入
    chunk_pool，天然避免 concurrent update。
    """
    final_top_k = getattr(search_engine, "final_top_k", FINAL_TOP_K_DEFAULT)

    async def _one(sub_q: str) -> list[SearchResult]:
        try:
            enhanced = prompt_optimizer.enhance_query(sub_q)
            return await retrieve_node(enhanced, embedder=embedder, search_engine=search_engine, topic=topic)
        except Exception as exc:  # noqa: BLE001 — 單一分支失敗不應拖垮整個 fan-out
            logger.warning(f"[fanout_retrieve_node] sub-question retrieve failed: {exc}")
            return []

    results_per_branch = await asyncio.gather(*(_one(sq) for sq in state.sub_questions))

    chunk_map: dict[str, SearchResult] = {}
    for branch_results in results_per_branch:
        for r in branch_results:
            chunk_map.setdefault(r.chunk_id, r)

    merged = list(chunk_map.values())[:final_top_k]
    return {"chunk_pool": tuple(merged)}


async def single_retrieve_node(
    state: RetrievalGraphState,
    *,
    embedder,
    search_engine,
    query: str | None = None,
    topic: str | None = None,
) -> dict[str, Any]:
    """單一問題（主問題或改寫後查詢）的檢索 Node。"""
    target_query = query if query is not None else state.normalized_input
    results = await retrieve_node(target_query, embedder=embedder, search_engine=search_engine, topic=topic)
    return {"chunk_pool": tuple(results)}


async def relevance_check_node(
    state: RetrievalGraphState,
    *,
    relevance_checker: RelevanceChecker,
) -> dict[str, Any]:
    """委派既有 RelevanceChecker.check()；不在此層重試（既有物件內部已有 fallback）。"""
    result = relevance_checker.check(state.question, list(state.chunk_pool))
    return {
        "relevance_sufficient": result.sufficient,
        "missing_aspects": tuple(result.missing_aspects),
    }


async def rewrite_query_node(
    state: RetrievalGraphState,
    *,
    query_rewriter: QueryRewriter,
) -> dict[str, Any]:
    """委派既有 QueryRewriter.rewrite()；retry_count 單向遞增。"""
    rewritten = query_rewriter.rewrite(state.question, list(state.missing_aspects))
    return {
        "normalized_input": rewritten,
        "retry_count": state.retry_count + 1,
    }


async def build_context_node(state: RetrievalGraphState, *, build_context_fn) -> dict[str, Any]:
    """委派既有 _build_context() 格式化函式。"""
    context = build_context_fn(list(state.chunk_pool))
    return {"final_context": context, "status": "succeeded"}
