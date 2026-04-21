"""Milvus 向量 Repository 實作（寫入側）。

與 MilvusRetriever（讀取側）分開，符合 Interface Segregation Principle。
"""
from __future__ import annotations

from loguru import logger

from src.core.domain.chunk import Chunk
from src.core.interfaces.repository import IVectorRepository


class MilvusVectorRepository(IVectorRepository):
    """以 Milvus 實作的向量資料存取層（寫入）。

    Args:
        collection: 已連線的 Milvus Collection 實例
        batch_size: 每次批次寫入的切塊數量（記憶體與速度的平衡）
    """

    def __init__(self, collection, batch_size: int = 32) -> None:
        self._collection = collection
        self._batch_size = batch_size

    def store_chunks(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> int:
        """批次儲存切塊向量至 Milvus。

        Args:
            chunks:     切塊列表
            embeddings: 對應的向量列表（順序需與 chunks 一致）

        Returns:
            成功寫入的切塊數量
        """
        if len(chunks) != len(embeddings):
            raise ValueError(
                f"chunks({len(chunks)}) and embeddings({len(embeddings)}) must have same length"
            )

        stored = 0
        for i in range(0, len(chunks), self._batch_size):
            batch_c = chunks[i : i + self._batch_size]
            batch_e = embeddings[i : i + self._batch_size]

            data = [
                [c.chunk_id for c in batch_c],
                [c.doc_hash for c in batch_c],
                [c.source for c in batch_c],
                [c.section for c in batch_c],
                [c.content[:4090] for c in batch_c],
                [c.token_count for c in batch_c],
                [c.page_hint or 0 for c in batch_c],
                [getattr(c, "video_title", "")[:510] for c in batch_c],
                [getattr(c, "upload_date", "")[:14] for c in batch_c],
                [getattr(c, "url", "")[:126] for c in batch_c],
                batch_e,
            ]
            self._collection.insert(data)
            stored += len(batch_c)
            logger.debug(f"[VectorRepo] Stored batch {i//self._batch_size + 1}: {len(batch_c)} chunks")

        self._collection.flush()
        logger.info(f"[VectorRepo] Total stored: {stored} chunks")
        return stored

    def delete_by_doc_hash(self, doc_hash: str) -> int:
        """刪除指定文件的所有向量。"""
        expr = f'doc_hash == "{doc_hash}"'
        result = self._collection.delete(expr)
        count = result.delete_count if hasattr(result, "delete_count") else 0
        logger.info(f"[VectorRepo] Deleted {count} chunks for doc_hash={doc_hash}")
        return count
