"""組裝 Agentic RAG Retrieval Graph。

`run_retrieval_graph()` 對外簽名與既有
`AgenticRAGPipeline._do_retrieve()` 完全相同：
    (question, sub_questions) -> (context, chunks, RetrievalMeta)

這是 Adapter 模式的關鍵——AgenticRAGPipeline 只需要在
`_retrieve()` 內以 feature flag 二選一呼叫，兩條路徑回傳型別相同，
下游（LLM 生成、memory 儲存）完全不需要修改。
"""
from __future__ import annotations

from dataclasses import dataclass

from loguru import logger

from src.core.domain.search_result import SearchResult
from src.graph.errors import ErrorCategory
from src.graph.runner import GraphRunner

from . import nodes
from .routing import route_after_relevance_check
from .state import RetrievalGraphState


@dataclass(frozen=True)
class GraphRetrievalMeta:
    """與既有 agentic_pipeline.RetrievalMeta 欄位相容的回傳型別。"""

    iterations: int
    sufficient: bool


async def run_retrieval_graph(
    question: str,
    sub_questions: list[str] | None,
    *,
    embedder,
    search_engine,
    prompt_optimizer,
    relevance_checker,
    query_rewriter,
    build_context_fn,
    topic: str | None = None,
) -> tuple[str, list[SearchResult], GraphRetrievalMeta]:
    """執行完整 retrieval graph（Enhance → Retrieve(s)/Join → Self-Reflection Loop → BuildContext）。"""
    state = RetrievalGraphState.new(question, sub_questions)
    runner = GraphRunner(state.execution_id)

    state, _ = await runner.step(
        state,
        "EnhanceQueryNode",
        lambda s: nodes.enhance_query_node(s, prompt_optimizer=prompt_optimizer),
    )

    if state.sub_questions:
        state, _ = await runner.step(
            state,
            "FanoutRetrieveNode",
            lambda s: nodes.fanout_retrieve_node(
                s,
                embedder=embedder,
                search_engine=search_engine,
                prompt_optimizer=prompt_optimizer,
                topic=topic,
            ),
            error_category=ErrorCategory.INFRA,
        )
    else:
        state, _ = await runner.step(
            state,
            "RetrieveNode",
            lambda s: nodes.single_retrieve_node(
                s, embedder=embedder, search_engine=search_engine, topic=topic
            ),
            error_category=ErrorCategory.INFRA,
            max_attempts=2,
        )

    while True:
        state, _ = await runner.step(
            state,
            "RelevanceCheckNode",
            lambda s: nodes.relevance_check_node(s, relevance_checker=relevance_checker),
            error_category=ErrorCategory.MODEL_FALLBACK,
        )

        decision = route_after_relevance_check(state)
        if decision == "build_context":
            break

        state, _ = await runner.step(
            state,
            "RewriteQueryNode",
            lambda s: nodes.rewrite_query_node(s, query_rewriter=query_rewriter),
            error_category=ErrorCategory.MODEL_FALLBACK,
        )
        state, _ = await runner.step(
            state,
            "RetrieveNode",
            lambda s: nodes.single_retrieve_node(
                s, embedder=embedder, search_engine=search_engine, topic=topic
            ),
            error_category=ErrorCategory.INFRA,
            max_attempts=2,
        )

    state, _ = await runner.step(
        state,
        "BuildContextNode",
        lambda s: nodes.build_context_node(s, build_context_fn=build_context_fn),
    )

    logger.info(
        f"[Graph:{state.execution_id}] retrieval graph done "
        f"iterations={state.retry_count + 1} sufficient={state.relevance_sufficient} "
        f"chunks={len(state.chunk_pool)}"
    )

    meta = GraphRetrievalMeta(iterations=state.retry_count + 1, sufficient=state.relevance_sufficient)
    return state.final_context, list(state.chunk_pool), meta
