"""Phase 2 — Milvus Vector Retriever

實作 IVectorRetriever 介面，HybridSearchEngine 透過介面依賴此類別。

SearchResult 值物件已移至 src/core/domain/search_result.py，
此處保留 re-export 以維持向後相容。
"""
from __future__ import annotations

import os

from pymilvus import Collection, connections, utility
from loguru import logger

from src.core.domain.search_result import SearchResult  # noqa: F401（re-export）
from src.core.interfaces.retriever import IVectorRetriever

COLLECTION_NAME = os.getenv("MILVUS_COLLECTION", "career_kb")
DEFAULT_TOP_K = 10
OUTPUT_FIELDS = ["chunk_id", "doc_hash", "source", "section", "content", "token_count", "page_number"]


class MilvusRetriever(IVectorRetriever):
    """Milvus 向量搜索器，負責密集向量（Dense）檢索。

    查詢時將問題向量與所有已存切塊比對，回傳最相似的 top-k 筆。
    """

    def __init__(self, host: str = "localhost", port: int = 19530) -> None:
        connections.connect("default", host=host, port=port)
        self._ready = utility.has_collection(COLLECTION_NAME)
        if self._ready:
            self._collection = Collection(COLLECTION_NAME)
            self._collection.load()  # 將 Collection 載入記憶體，加速查詢
        else:
            self._collection = None
            logger.warning(f"Milvus collection '{COLLECTION_NAME}' 尚未建立，請先匯入文件。")

    def search(self, query_embedding: list[float], top_k: int = DEFAULT_TOP_K) -> list[SearchResult]:
        """執行向量相似度搜索。

        Args:
            query_embedding: 查詢問題的向量表示
            top_k: 回傳結果數量（HybridSearch 會要求取 20 筆供後續 BM25 重排序）

        Returns:
            依相似度排序的 SearchResult 列表

        搜索參數說明：
            metric_type=IP : 用內積（Inner Product）計算相似度
            nprobe=16       : 搜索向量空間中最近的 16 個 cluster（越大越準但越慢）
        """
        if not self._ready:
            # 嘗試重新連接（文件匯入後 collection 可能已建立）
            if utility.has_collection(COLLECTION_NAME):
                self._collection = Collection(COLLECTION_NAME)
                self._collection.load()
                self._ready = True
                logger.info(f"Milvus collection '{COLLECTION_NAME}' 已就緒（延遲載入）。")
            else:
                return []
        try:
            results = self._collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param={"metric_type": "IP", "params": {"nprobe": 64}},
                limit=top_k,
                output_fields=OUTPUT_FIELDS,
            )
        except Exception as e:
            logger.warning(f"Milvus search failed, resetting collection state: {e}")
            self._ready = False
            self._collection = None
            return []
        hits = []
        for hit in results[0]:
            entity = hit.entity
            raw_page = entity.get("page_number")
            page_number = int(raw_page) if raw_page and int(raw_page) > 0 else None

            hits.append(
                SearchResult(
                    chunk_id=str(entity.get("chunk_id") or ""),
                    content=str(entity.get("content") or ""),
                    source=str(entity.get("source") or ""),
                    section=str(entity.get("section") or ""),
                    score=float(hit.score),
                    page_number=page_number,
                )
            )
        logger.debug(f"Vector search returned {len(hits)} results")
        return hits
    
    def get_all_chunks(self) -> list[SearchResult]:
        """從 Milvus 取出全部切塊，供全語料庫 BM25 索引使用。

        Returns:
            集合中所有切塊的 SearchResult 列表（score=0）
        """
        if not self._ready:
            return []
        results: list[SearchResult] = []
        offset = 0
        batch_size = 200
        while True:
            batch = self._collection.query(
                expr="chunk_id != \"\"",
                output_fields=OUTPUT_FIELDS,
                limit=batch_size,
                offset=offset,
            )
            if not batch:
                break
            for entity in batch:
                raw_page = entity.get("page_number")
                page_number = int(raw_page) if raw_page and int(raw_page) > 0 else None
                results.append(SearchResult(
                    chunk_id=str(entity.get("chunk_id") or ""),
                    content=str(entity.get("content") or ""),
                    source=str(entity.get("source") or ""),
                    section=str(entity.get("section") or ""),
                    score=0.0,
                    page_number=page_number,
                ))
            if len(batch) < batch_size:
                break
            offset += batch_size
        logger.debug(f"Loaded {len(results)} chunks for full-corpus BM25")
        return results
