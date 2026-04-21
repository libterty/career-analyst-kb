"""Phase 2 — RAG Pipeline
整合 Hybrid Search + LLM 生成，支援多輪對話記憶。
"""
from __future__ import annotations

import os
from typing import AsyncIterator, Optional

from langchain.memory import ConversationBufferWindowMemory
from langchain.schema import HumanMessage, SystemMessage, AIMessage
from loguru import logger

from ..core.llm_factory import build_llm
from ..ingestion.embedder import EmbeddingService
from ..finetuning.prompt_optimizer import PromptOptimizer
from .hybrid_search import HybridSearchEngine
from .retriever import MilvusRetriever, SearchResult

# System Prompt 定義助理角色與行為約束
# {context} 會在每次查詢時替換為 top-5 典籍段落
_SYSTEM_PROMPT = """你是一位專業的職涯分析師，根據職涯顧問的影片內容協助使用者解決職涯問題。
請依據以下從影片逐字稿擷取的參考段落回答問題，內容包含履歷撰寫、面試技巧、職涯規劃與薪資談判等主題。
若參考段落中未包含相關資訊，請誠實說明，切勿自行捏造建議。
回答應以繁體中文撰寫，語調專業而親切。引用影片內容時請附上影片標題。

【參考段落】
{context}
"""


class RAGPipeline:
    """RAG 主管線，整合查詢強化、向量搜索、混合搜索與 LLM 串流生成。

    依序執行：
        1. 查詢強化  — 術語正規化
        2. 混合搜索  — 向量搜索 + BM25，RRF 融合取 top-5
        3. LLM 生成  — 帶著典籍段落串流生成回答
        4. 記憶儲存  — 保留最近 N 輪對話供後續參考
    """

    def __init__(
        self,
        milvus_host: str | None = None,
        milvus_port: int | None = None,
        llm_model: Optional[str] = None,
        memory_window: int = 10,
    ) -> None:
        """初始化 RAG Pipeline。

        Args:
            milvus_host:   Milvus 主機位址
            milvus_port:   Milvus 連接埠
            llm_model:     LLM 模型名稱（None 表示使用環境變數設定）
            memory_window: 對話記憶保留的輪數（預設 10 輪）
        """
        host = milvus_host or os.getenv("MILVUS_HOST", "localhost")
        port = milvus_port or int(os.getenv("MILVUS_PORT", "19530"))
        retriever = MilvusRetriever(host=host, port=port)
        embedder = EmbeddingService(milvus_host=host, milvus_port=port)

        # dense_top_k=50：向量搜索多取 50 筆供 BM25 重排序（小型知識庫可取更多候選）
        # final_top_k=5：最終進入 LLM 的段落數（context 長度與準確度的平衡）
        self._search = HybridSearchEngine(retriever, dense_top_k=50, final_top_k=5)
        self._embedder = embedder
        self._prompt_optimizer = PromptOptimizer()
        # temperature=0.3：較低溫度讓回答更穩定，不亂發揮
        self._llm = build_llm(model=llm_model, temperature=0.3, streaming=True)
        # ConversationBufferWindowMemory：只保留最近 k 輪，防止 context 過長
        self._memory = ConversationBufferWindowMemory(k=memory_window)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def query(self, question: str, session_id: str = "default") -> AsyncIterator[str]:
        """執行 RAG 問答並以 async generator 串流回傳 LLM 輸出。

        Args:
            question:   使用者問題（已通過安全檢查的乾淨輸入）
            session_id: 對話 session 識別碼（用於日誌）

        Yields:
            LLM 逐 token 輸出的字串片段
        """
        # 1. 查詢強化：將俗稱別名替換為標準術語（如「老母」→「無極老母」）
        enhanced_query = self._prompt_optimizer.enhance_query(question)

        # 2. 混合搜索：先向量化查詢，再執行 Hybrid Search
        query_embedding = self._embedder.embed_query(enhanced_query)
        search_results = self._search.search(enhanced_query, query_embedding)

        # 3. 組裝 Context：將 top-5 段落格式化為 LLM 可讀的文字
        context = self._build_context(search_results)

        # 4. 組裝訊息列表：System（角色+典籍段落）→ 歷史對話 → 使用者問題
        history = self._memory.load_memory_variables({}).get("history", "")
        messages = [
            SystemMessage(content=_SYSTEM_PROMPT.format(context=context)),
        ]
        if history:
            # 將對話歷史插入，讓 LLM 理解多輪對話的脈絡
            messages.append(AIMessage(content=history))
        messages.append(HumanMessage(content=question))

        # 5. LLM 串流生成：逐 token yield，讓前端即時顯示
        full_response = ""
        async for chunk in self._llm.astream(messages):
            token = chunk.content
            full_response += token
            yield token

        # 6. 儲存本輪對話記憶，供下一輪參考
        self._memory.save_context({"input": question}, {"output": full_response})
        logger.info(f"[RAG] session={session_id} q_len={len(question)} a_len={len(full_response)}")

    def get_sources(self, question: str) -> list[dict]:
        """取得問題的相關典籍來源（不生成回答，用於顯示引用資訊）。

        Returns:
            每筆來源包含 source（文件）、section（章節）、score（相似度分數）
        """
        query_embedding = self._embedder.embed_query(question)
        results = self._search.search(question, query_embedding)
        return [
            {"source": r.source, "section": r.section, "score": round(r.score, 4)}
            for r in results
        ]

    # ------------------------------------------------------------------

    @staticmethod
    def _build_context(results: list[SearchResult]) -> str:
        """將搜索結果格式化為 System Prompt 中的參考段落文字。

        格式：[序號] 【章節】原文內容
        LLM 看到這個格式後能清楚辨識每段的來源章節。
        """
        if not results:
            return "（未找到相關段落）"
        parts = []
        for i, r in enumerate(results, start=1):
            section_label = f"【{r.section}】" if r.section else ""
            parts.append(f"[{i}] {section_label}{r.content}")
        return "\n\n".join(parts)
