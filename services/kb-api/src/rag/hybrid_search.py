"""Phase 2 — Hybrid Search (Dense Vector + BM25 Sparse)
使用 Reciprocal Rank Fusion (RRF) 合併兩路結果。

實作 ISearchEngine 介面，ChatService 透過介面依賴此類別。
"""
from __future__ import annotations

from collections import defaultdict

from rank_bm25 import BM25Okapi
from loguru import logger

from src.core.domain.search_result import SearchResult
from src.core.interfaces.retriever import IVectorRetriever
from src.core.interfaces.search import ISearchEngine


def _tokenize_zh(text: str) -> list[str]:
    """中文分詞函式。

    優先使用 jieba 做詞語切分（如「修行方法」→ [「修行」,「方法」]），
    若 jieba 未安裝則 fallback 到字元切分（每個漢字獨立）。
    jieba 分詞能讓 BM25 更準確地匹配詞語而非單字。

    特別處理：
    - 英文大寫縮寫（STAR、SHARE、BM25 等）保留為單一 token
    - 英文小寫單詞（method、interview 等）保留為整個 token，
      避免 jieba/字元切分將其拆成單個字母降低 BM25 精準度
    """
    import re
    tokens: list[str] = []
    # Split on ASCII word sequences (uppercase acronyms, lowercase words, numbers) to preserve them
    _EN_WORD = re.compile(r"([A-Za-z]{2,}\d*|\d+[A-Za-z]{2,})")
    parts = _EN_WORD.split(text)
    try:
        import jieba  # type: ignore
        for part in parts:
            if _EN_WORD.fullmatch(part):
                tokens.append(part.lower())
            elif part:
                tokens.extend(jieba.cut(part))
    except ImportError:
        for part in parts:
            if _EN_WORD.fullmatch(part):
                tokens.append(part.lower())
            elif part:
                tokens.extend(list(part))
    return tokens


class HybridSearchEngine(ISearchEngine):
    """混合搜索引擎，結合向量搜索（Dense）與全語料庫 BM25 關鍵字搜索（Sparse）。

    工作流程：
        1. 向量搜索：取 dense_top_k 筆語意相近的候選
        2. 全語料庫 BM25：對全部切塊做 BM25 關鍵字評分，取 bm25_top_k 筆（首次查詢時建立快取）
        3. RRF 融合：合併兩路結果，取 final_top_k 筆

    全語料庫 BM25 vs 只在 Dense 候選上做 BM25：
        只在 Dense 候選上做 BM25 會受 Dense 召回品質限制——若向量模型對短查詢
        的判斷力不足（分數壓縮），關鍵字完全匹配的切塊可能落在 Dense top-K 之外，
        導致 BM25 無法發揮作用。全語料庫 BM25 則不受此限制，直接以關鍵字找到
        精確匹配的切塊，再與 Dense 結果融合。

    RRF 公式：score = Σ 1 / (k + rank_i)，k=20 為平滑係數
    """

    RRF_K = 20  # RRF 平滑係數：嵌入模型分數壓縮時（如 nomic-embed 對短中文查詢）
    # 降低 K 使 BM25 精確匹配能有效覆蓋向量排名偏低的切塊。

    def __init__(
        self,
        retriever: IVectorRetriever,
        dense_top_k: int = 50,
        final_top_k: int = 5,
        bm25_top_k: int = 20,
    ) -> None:
        """
        Args:
            retriever:    Milvus 向量搜索器（須有 get_all_chunks() 方法以支援全語料庫 BM25）
            dense_top_k:  向量搜索初始召回數
            final_top_k:  最終輸入 LLM 的結果數量
            bm25_top_k:   BM25 搜索的候選數量（取分數最高的前 N 筆與 Dense 合併）
        """
        self._retriever = retriever
        self.dense_top_k = dense_top_k
        self.final_top_k = final_top_k
        self.bm25_top_k = bm25_top_k
        # 全語料庫 BM25 索引（首次查詢時 lazy 載入，避免啟動時阻塞）
        self._bm25_corpus: list[SearchResult] | None = None
        self._bm25_index: BM25Okapi | None = None
        self._bm25_tokenized: list[list[str]] | None = None
    
    def invalidate_bm25_cache(self) -> None:
        """在重新匯入文件後呼叫此方法，強制下次查詢時重建 BM25 索引。"""
        self._bm25_corpus = None
        self._bm25_index = None
        self._bm25_tokenized = None
        logger.info("[HybridSearch] BM25 cache invalidated")

    def _ensure_bm25_index(self) -> None:
        """Lazy 載入全語料庫並建立 BM25 索引（執行緒安全性由呼叫端保證）。"""
        if self._bm25_index is not None:
            return
        corpus = getattr(self._retriever, "get_all_chunks", lambda: [])()
        if not corpus:
            logger.warning("[HybridSearch] Full corpus unavailable, BM25 index skipped")
            return
        self._bm25_corpus = corpus
        tokenized = [_tokenize_zh(c.content) for c in corpus]
        self._bm25_index = BM25Okapi(tokenized)
        self._bm25_tokenized = tokenized
        logger.info(f"[HybridSearch] BM25 index built over {len(corpus)} chunks")

    def search(self, query: str, query_embedding: list[float], topic: str | None = None) -> list[SearchResult]:
        """執行混合搜索，回傳 RRF 融合後的最終結果。

        Args:
            query:           使用者查詢文字（用於 BM25 關鍵字比對）
            query_embedding: 查詢文字的向量（用於 Milvus 向量搜索）

        Returns:
            依 RRF 分數排序的前 final_top_k 筆結果
        """
        # 1. 向量搜索（Dense），若指定 topic 則傳入 Milvus filter expr
        dense_results = self._retriever.search(query_embedding, top_k=self.dense_top_k, topic=topic)
        if not dense_results:
            return []

        # 2. 全語料庫 BM25 搜索（不限 topic，讓關鍵字精確匹配可跨 section 召回）
        # Dense 已做 topic 過濾（精準），BM25 覆蓋全語料庫（召回），RRF 融合兩路優勢。
        self._ensure_bm25_index()
        if self._bm25_index is not None and self._bm25_corpus:
            active_corpus: list[SearchResult] = self._bm25_corpus
            tokenized_query = _tokenize_zh(query)
            bm25_scores = self._bm25_index.get_scores(tokenized_query)
            bm25_top_indices = sorted(
                range(len(bm25_scores)), key=lambda i: -bm25_scores[i]
            )[: self.bm25_top_k]
            bm25_top_results = [active_corpus[i] for i in bm25_top_indices]
        else:
            # Fallback：BM25 僅在 Dense 候選上計算（舊行為）
            corpus_texts = [r.content for r in dense_results]
            tokenized_corpus = [_tokenize_zh(doc) for doc in corpus_texts]
            bm25 = BM25Okapi(tokenized_corpus)
            tokenized_query = _tokenize_zh(query)
            bm25_scores_arr = bm25.get_scores(tokenized_query)
            bm25_top_indices = sorted(
                range(len(bm25_scores_arr)), key=lambda i: -bm25_scores_arr[i]
            )[: self.bm25_top_k]
            bm25_top_results = [dense_results[i] for i in bm25_top_indices]

        # 3. 合併候選池（Dense ∪ BM25 Top-K）
        chunk_map: dict[str, SearchResult] = {r.chunk_id: r for r in dense_results}
        chunk_map.update({r.chunk_id: r for r in bm25_top_results})

        # 4. 建立各路排名（chunk_id → 排名，從 1 開始）
        dense_rank = {r.chunk_id: rank for rank, r in enumerate(dense_results, start=1)}
        # BM25 排名：依 BM25 分數從高到低排序後建立排名
        bm25_rank = {r.chunk_id: rank for rank, r in enumerate(bm25_top_results, start=1)}

        # 5. RRF 融合：分數 = 向量貢獻 + BM25 貢獻
        #    對稱懲罰：未出現在某路的切塊以 max(dense, bm25)+1 作為懲罰排名。
        #    這讓 BM25-only 跨 section 結果（如 STAR 在 resume section）
        #    能與 Dense-only 結果公平競爭，而非被 corpus_size=14K 的巨大懲罰壓死。
        path_penalty = max(len(dense_results), len(bm25_top_results)) + 1

        rrf_scores: dict[str, float] = defaultdict(float)
        for chunk_id in chunk_map:
            dr = dense_rank.get(chunk_id, path_penalty)
            br = bm25_rank.get(chunk_id, path_penalty)
            rrf_scores[chunk_id] = 1.0 / (self.RRF_K + dr) + 1.0 / (self.RRF_K + br)

        # 6. 依 RRF 分數排序，取前 final_top_k 筆
        ranked = sorted(rrf_scores.items(), key=lambda x: -x[1])

        results = []
        for chunk_id, score in ranked[: self.final_top_k]:
            result = chunk_map[chunk_id]
            results.append(SearchResult(
                chunk_id=result.chunk_id,
                content=result.content,
                source=result.source,
                section=result.section,
                score=score,
                page_number=result.page_number,
                video_title=result.video_title,
                upload_date=result.upload_date,
                url=result.url,
            ))

        logger.debug(f"Hybrid search: {len(results)} final results after RRF fusion")
        return results
