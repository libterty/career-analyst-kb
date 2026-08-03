"""Agentic RAG Pipeline

Self-Reflection Loop 版本的 RAG Pipeline。
對外介面與 RAGPipeline.query() 相同（AsyncIterator[str]），
額外提供 get_last_retrieval_meta() 回傳本輪的迭代次數與相關性結果。

流程：
    1. 查詢強化（術語正規化）
    2. [Iteration Loop, max=MAX_ITERATIONS]
       a. Hybrid Search（Dense + BM25 + RRF）
       b. RelevanceChecker：chunk 夠不夠？
          - SUFFICIENT 或已達上限 → 跳出迴圈
          - INSUFFICIENT → QueryRewriter 改寫 query → 下一輪
    3. LLM 串流生成
    4. 記憶儲存

sub_questions 支援（複合問題）：
    若傳入 sub_questions，各 sub-question 獨立 retrieve，
    chunk pool 合併後再進入 self-reflection loop。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import AsyncIterator, Optional

from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import AIMessage, HumanMessage, SystemMessage
from loguru import logger

from ..core.llm_factory import build_llm, build_fast_llm
from ..core.tracing import langfuse_trace_id_var, langfuse_client
from ..ingestion.embedder import EmbeddingService
from ..rag.hybrid_search import HybridSearchEngine
from ..rag.retriever import MilvusRetriever, SearchResult
from ..finetuning.prompt_optimizer import PromptOptimizer
from ..rag.relevance_checker import RelevanceChecker
from ..rag.query_rewriter import QueryRewriter

MAX_ITERATIONS = 2

# Phase 1 Graph 化開關；預設 None 時建構子會讀取 AppSettings.mode。
# 見 docs/graph-design/graph-migration-plan.md 的漸進式 migration 步驟。
def _default_use_graph_retrieval() -> bool:
    try:
        from ..core.config import get_settings
        return get_settings().mode == "Graph"
    except Exception:
        return False

_SYSTEM_PROMPT = """你是一位專業的職涯分析師，根據職涯顧問的影片內容協助使用者解決職涯問題。
請依據以下從影片逐字稿擷取的參考段落回答問題，內容包含履歷撰寫、面試技巧、職涯規劃與薪資談判等主題。
若參考段落中未包含相關資訊，請誠實說明，切勿自行捏造建議。
回答應以繁體中文撰寫，語調專業而親切。引用影片內容時請附上影片標題。

【參考段落】
{context}
"""


@dataclass
class RetrievalMeta:
    iterations: int
    sufficient: bool


class AgenticRAGPipeline:
    """Self-Reflection Loop RAG Pipeline。

    初始化較昂貴（Milvus 連線 + BM25 index），請使用 Singleton 模式。
    """

    def __init__(
        self,
        milvus_host: str | None = None,
        milvus_port: int | None = None,
        llm_model: Optional[str] = None,
        memory_window: int = 10,
        use_graph_retrieval: bool | None = None,
    ) -> None:
        self._use_graph_retrieval = (
            use_graph_retrieval if use_graph_retrieval is not None else _default_use_graph_retrieval()
        )
        host = milvus_host or os.getenv("MILVUS_HOST", "localhost")
        port = milvus_port or int(os.getenv("MILVUS_PORT", "19530"))

        retriever = MilvusRetriever(host=host, port=port)
        self._embedder = EmbeddingService(milvus_host=host, milvus_port=port)
        self._search = HybridSearchEngine(retriever, dense_top_k=50, final_top_k=8, bm25_top_k=25)
        self._prompt_optimizer = PromptOptimizer()

        self._llm = build_llm(model=llm_model, temperature=0.3, streaming=True)
        fast_llm = build_fast_llm()
        self._relevance_checker = RelevanceChecker(fast_llm)
        self._query_rewriter = QueryRewriter(fast_llm, self._embedder)

        self._memory = ConversationBufferWindowMemory(k=memory_window)
        self._last_meta = RetrievalMeta(iterations=1, sufficient=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def query(
        self,
        question: str,
        session_id: str = "default",
        sub_questions: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """執行 Agentic RAG 問答，以 async generator 串流回傳 LLM 輸出。

        Args:
            question:      使用者問題
            session_id:    對話 session 識別碼（用於日誌）
            sub_questions: 複合問題拆解後的 sub-questions（由 QueryDecomposer 注入）

        Yields:
            LLM 逐 token 輸出
        """
        if getattr(self, "_use_graph_retrieval", False):
            context, results, meta = await self._retrieve_graph(question, sub_questions)
        else:
            context, results, meta = self._retrieve(question, sub_questions)
        self._last_meta = meta

        history = self._memory.load_memory_variables({}).get("history", "")
        messages = [SystemMessage(content=_SYSTEM_PROMPT.format(context=context))]
        if history:
            messages.append(AIMessage(content=history))
        messages.append(HumanMessage(content=question))

        full_response = ""
        async for chunk in self._llm.astream(messages):
            token = chunk.content
            full_response += token
            yield token

        self._memory.save_context({"input": question}, {"output": full_response})
        logger.info(
            f"[AgenticRAG] session={session_id} iterations={meta.iterations} "
            f"sufficient={meta.sufficient} sources={len(results)}"
        )

    def get_last_retrieval_meta(self) -> RetrievalMeta:
        """回傳最近一次 query() 的 retrieval metadata。"""
        return self._last_meta

    def get_sources(self, question: str, topic: str | None = None) -> list[dict]:
        """取得問題的相關來源（不生成回答）。"""
        embedding = self._embedder.embed_query(question)
        results = self._search.search(question, embedding, topic=topic)
        return [
            {
                "source": r.source,
                "section": r.section,
                "score": round(r.score, 4),
                "page_number": r.page_number,
                "video_title": r.video_title,
                "upload_date": r.upload_date,
                "url": r.url,
            }
            for r in results
        ]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _retrieve_graph(
        self,
        question: str,
        sub_questions: list[str] | None,
    ) -> tuple[str, list[SearchResult], RetrievalMeta]:
        """Graph 化版本（feature-flagged, see AppSettings.mode == "Graph"）。

        委派給 src/rag/graph/build.py::run_retrieval_graph()，回傳型別與
        既有 _retrieve() 完全相同，供 query() 二選一呼叫（Adapter 模式，
        見 docs/graph-design/graph-migration-plan.md）。
        """
        from .graph import run_retrieval_graph

        context, results, graph_meta = await run_retrieval_graph(
            question,
            sub_questions,
            embedder=self._embedder,
            search_engine=self._search,
            prompt_optimizer=self._prompt_optimizer,
            relevance_checker=self._relevance_checker,
            query_rewriter=self._query_rewriter,
            build_context_fn=_build_context,
        )
        return context, results, RetrievalMeta(iterations=graph_meta.iterations, sufficient=graph_meta.sufficient)

    def _retrieve(
        self,
        question: str,
        sub_questions: list[str] | None,
    ) -> tuple[str, list[SearchResult], RetrievalMeta]:
        """Self-Reflection Loop：retrieve → check → rewrite → repeat（最多 MAX_ITERATIONS 輪）。"""
        lf = langfuse_client()
        parent_trace_id = langfuse_trace_id_var.get()
        trace_ctx = None
        if lf and parent_trace_id:
            try:
                from langfuse.types import TraceContext
                trace_ctx = TraceContext(trace_id=parent_trace_id)
            except ImportError:
                pass

        def _do_retrieve() -> tuple[str, list[SearchResult], RetrievalMeta]:
            enhanced = self._prompt_optimizer.enhance_query(question)

            # 複合問題：先收集各 sub-question 的 chunk pool
            if sub_questions:
                chunk_map: dict[str, SearchResult] = {}
                for sq in sub_questions:
                    sq_enhanced = self._prompt_optimizer.enhance_query(sq)
                    sq_emb = self._embedder.embed_query(sq_enhanced)
                    for r in self._search.search(sq_enhanced, sq_emb):
                        chunk_map[r.chunk_id] = r
                initial_chunks = list(chunk_map.values())[: self._search.final_top_k]
            else:
                embedding = self._embedder.embed_query(enhanced)
                initial_chunks = self._search.search(enhanced, embedding)

            # Self-Reflection Loop
            current_query = enhanced
            current_chunks = initial_chunks
            iterations = 0

            for i in range(MAX_ITERATIONS):
                iterations = i + 1
                relevance = self._relevance_checker.check(question, current_chunks)

                if relevance.sufficient or i == MAX_ITERATIONS - 1:
                    context = _build_context(current_chunks)
                    return context, current_chunks, RetrievalMeta(
                        iterations=iterations,
                        sufficient=relevance.sufficient,
                    )

                # 不足 → 改寫 query，進下一輪
                rewritten = self._query_rewriter.rewrite(question, relevance.missing_aspects)
                new_embedding = self._embedder.embed_query(rewritten)
                current_chunks = self._search.search(rewritten, new_embedding)
                logger.debug(f"[AgenticRAG] iteration {i+1}: rewritten={rewritten!r}")

            # 理論上不會走到這裡，但作為安全 fallback
            context = _build_context(current_chunks)
            return context, current_chunks, RetrievalMeta(iterations=iterations, sufficient=False)

        if lf:
            with lf.start_as_current_observation(
                name="agentic-rag-retrieve",
                as_type="retriever",
                trace_context=trace_ctx,
                input={"question": question, "sub_questions": sub_questions},
            ) as obs:
                result = _do_retrieve()
                obs.update(output={
                    "chunk_count": len(result[1]),
                    "iterations": result[2].iterations,
                    "sufficient": result[2].sufficient,
                })
            lf.flush()
            return result

        return _do_retrieve()


def _build_context(results: list[SearchResult]) -> str:
    if not results:
        return "（未找到相關段落）"
    parts = []
    for i, r in enumerate(results, start=1):
        section_label = f"【{r.section}】" if r.section else ""
        parts.append(f"[{i}] {section_label}{r.content}")
    return "\n\n".join(parts)
