"""Semantic Cache Service — 語意快取業務邏輯層。

原理：
    1. 新問題進來時，先用 Embedding 向量在 Milvus 的 semantic_cache 集合中搜尋相似問題
    2. 若相似度 >= threshold（預設 0.95），視為快取命中，直接回傳儲存的回答
    3. 快取未命中時，正常執行 RAG 流程，並在得到回答後將結果存入快取
    4. 快取可設 TTL，過期後下次查詢時會重新生成

快取帶來的好處：
    - 相同或高度相似的問題（FAQ 場景）無須重複呼叫 LLM，降低推論成本
    - 回應速度更快（不須等待 LLM 生成）
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

from loguru import logger
from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, connections, utility

CACHE_COLLECTION = "semantic_cache"


class SemanticCacheService:
    """語意快取服務。

    維護一個獨立的 Milvus collection（semantic_cache）專門用於問題向量的 ANN 搜尋，
    PostgreSQL 表格儲存對應的回答文字與 metadata。
    """

    def __init__(
        self,
        db_session_factory,
        embed_query_fn,
        milvus_host: str = "localhost",
        milvus_port: int = 19530,
        embedding_dim: int = 768,
        similarity_threshold: float = 0.95,
        ttl_hours: int = 24,
    ) -> None:
        self._db_session_factory = db_session_factory
        self._embed_query = embed_query_fn
        self._threshold = similarity_threshold
        self._ttl_hours = ttl_hours

        # 連線 Milvus 並取得或建立快取集合
        connections.connect("default", host=milvus_host, port=milvus_port)
        self._collection = self._get_or_create_cache_collection(embedding_dim)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def lookup(self, query_text: str) -> tuple[str, list[dict]] | None:
        """查詢語意快取。

        Args:
            query_text: 原始問題文字

        Returns:
            (answer, sources) 若快取命中；None 若快取未命中
        """
        query_embedding = self._embed_query(query_text)
        results = self._collection.search(
            data=[query_embedding],
            anns_field="embedding",
            param={"metric_type": "IP", "params": {"nprobe": 8}},
            limit=1,
            output_fields=["cache_key"],
        )

        if not results or not results[0]:
            return None

        hit = results[0][0]
        if float(hit.score) < self._threshold:
            return None

        cache_key = hit.entity.get("cache_key")
        return await self._fetch_from_db(cache_key)

    async def store(
        self,
        query_text: str,
        answer: str,
        sources: list[dict],
    ) -> None:
        """將問答結果存入語意快取。"""
        cache_key = str(uuid.uuid4()).replace("-", "")[:32]
        query_embedding = self._embed_query(query_text)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=self._ttl_hours)

        # 寫入 Milvus（向量 + cache_key）
        self._collection.insert([[cache_key], [query_embedding]])
        self._collection.flush()

        # 寫入 PostgreSQL（完整的問答 metadata）
        from src.infrastructure.persistence.models.semantic_cache import SemanticCacheEntry

        entry = SemanticCacheEntry(
            cache_key=cache_key,
            query_text=query_text,
            answer=answer,
            sources_json=json.dumps(sources, ensure_ascii=False),
            expires_at=expires_at,
        )
        async with self._db_session_factory() as db:
            db.add(entry)
            await db.commit()

        logger.debug(f"[SemanticCache] Stored: key={cache_key} q={query_text[:50]}")

    async def evict_expired(self) -> int:
        """清除已過期的快取條目。"""
        from sqlalchemy import select, delete as sa_delete
        from src.infrastructure.persistence.models.semantic_cache import SemanticCacheEntry

        now = datetime.now(timezone.utc)
        async with self._db_session_factory() as db:
            result = await db.execute(
                select(SemanticCacheEntry.cache_key).where(
                    SemanticCacheEntry.expires_at < now
                )
            )
            expired_keys = [row.cache_key for row in result.all()]

            if not expired_keys:
                return 0

            # 從 Milvus 刪除
            keys_expr = ", ".join(f'"{k}"' for k in expired_keys)
            self._collection.delete(f"cache_key in [{keys_expr}]")
            self._collection.flush()

            # 從 PostgreSQL 刪除
            await db.execute(
                sa_delete(SemanticCacheEntry).where(
                    SemanticCacheEntry.cache_key.in_(expired_keys)
                )
            )
            await db.commit()

        logger.info(f"[SemanticCache] Evicted {len(expired_keys)} expired entries")
        return len(expired_keys)

    # ------------------------------------------------------------------

    async def _fetch_from_db(self, cache_key: str) -> tuple[str, list[dict]] | None:
        """從 PostgreSQL 取得快取回答，並更新命中次數。"""
        from sqlalchemy import select
        from src.infrastructure.persistence.models.semantic_cache import SemanticCacheEntry

        async with self._db_session_factory() as db:
            result = await db.execute(
                select(SemanticCacheEntry).where(SemanticCacheEntry.cache_key == cache_key)
            )
            entry = result.scalar_one_or_none()

            if entry is None:
                return None

            # 檢查是否已過期
            if entry.expires_at and entry.expires_at < datetime.now(timezone.utc):
                return None

            entry.hit_count += 1
            await db.commit()

            logger.debug(f"[SemanticCache] Hit: key={cache_key} hits={entry.hit_count}")
            return entry.answer, entry.get_sources()

    def _get_or_create_cache_collection(self, embedding_dim: int) -> Collection:
        """取得或建立 semantic_cache Milvus collection。"""
        if utility.has_collection(CACHE_COLLECTION):
            col = Collection(CACHE_COLLECTION)
            col.load()
            return col

        fields = [
            FieldSchema("cache_key", DataType.VARCHAR, max_length=64, is_primary=True),
            FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=embedding_dim),
        ]
        schema = CollectionSchema(fields, description="語意快取向量索引")
        col = Collection(CACHE_COLLECTION, schema)
        col.create_index(
            "embedding",
            {"index_type": "IVF_FLAT", "metric_type": "IP", "params": {"nlist": 64}},
        )
        col.load()
        logger.info(f"Created Milvus cache collection: {CACHE_COLLECTION}")
        return col
