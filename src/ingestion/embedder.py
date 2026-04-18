"""Phase 1 — Embedding Service
支援 Ollama（nomic-embed-text 等）及 OpenAI Embeddings。
Provider 由 EMBEDDING_PROVIDER 環境變數決定（ollama | openai）。
寫入 Milvus 向量資料庫，並在 PostgreSQL 記錄 metadata。
"""
from __future__ import annotations

import os
from typing import Optional

from loguru import logger
from pymilvus import (
    Collection,
    CollectionSchema,
    DataType,
    FieldSchema,
    connections,
    utility,
)

from ..core.llm_factory import build_embedder, get_embedding_dim
from .chunker import Chunk

# Milvus Collection 名稱，可透過環境變數覆寫
COLLECTION_NAME = os.getenv("MILVUS_COLLECTION", "yiguandao_kb")


def _build_schema(embedding_dim: int) -> CollectionSchema:
    """建立 Milvus Collection 的欄位定義。

    Args:
        embedding_dim: 向量維度（依 Embedding 模型而定，如 nomic-embed-text 為 768）

    欄位說明：
        chunk_id    - 主鍵，唯一識別每個切塊
        doc_hash    - 文件指紋，用於追溯文件來源
        source      - 文件路徑
        section     - 章節名稱（如「第三章」）
        content     - 切塊原文（最多 4096 字）
        token_count - token 數量（用於統計）
        embedding   - 浮點數向量（向量搜索的核心欄位）
    """
    fields = [
        FieldSchema("chunk_id", DataType.VARCHAR, max_length=64, is_primary=True),
        FieldSchema("doc_hash", DataType.VARCHAR, max_length=32),
        FieldSchema("source", DataType.VARCHAR, max_length=512),
        FieldSchema("section", DataType.VARCHAR, max_length=128),
        FieldSchema("content", DataType.VARCHAR, max_length=4096),
        FieldSchema("token_count", DataType.INT32),
        FieldSchema("page_number", DataType.INT32),   # 來源頁碼（0 表示未知
        FieldSchema("embedding", DataType.FLOAT_VECTOR, dim=embedding_dim),
    ]
    return CollectionSchema(fields, description="一貫道知識庫向量索引")


class EmbeddingService:
    """批次 Embedding + Milvus 寫入服務。

    將文本切塊轉換為向量並存入 Milvus，支援分批處理以避免記憶體溢出。
    """

    def __init__(
        self,
        milvus_host: str | None = None,
        milvus_port: int | None = None,
        batch_size: int = 32,
        embedding_model: Optional[str] = None,
    ) -> None:
        """初始化 Embedding 服務並連線至 Milvus。

        Args:
            milvus_host: Milvus 主機位址（預設讀取 MILVUS_HOST 環境變數）
            milvus_port: Milvus 連接埠（預設 19530）
            batch_size: 每批次處理的切塊數量（32 是記憶體與效率的平衡點）
            embedding_model: 指定 Embedding 模型名稱（None 表示使用環境變數設定）
        """
        host = milvus_host or os.getenv("MILVUS_HOST", "localhost")
        port = milvus_port or int(os.getenv("MILVUS_PORT", "19530"))
        self.batch_size = batch_size
        self._embedder = build_embedder(model=embedding_model)
        self._embedding_dim = get_embedding_dim()
        connections.connect("default", host=host, port=port)
        self._collection = self._get_or_create_collection()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed_and_store(self, chunks: list[Chunk]) -> int:
        """將切塊列表向量化後批次寫入 Milvus。

        Args:
            chunks: 要寫入的切塊列表

        Returns:
            實際寫入的切塊數量

        流程：
            1. 依 batch_size 分批取出切塊
            2. 對每批的文字內容呼叫 Embedding 模型
            3. 將向量與 metadata 一起 insert 進 Milvus
        """
        stored = 0
        for i in range(0, len(chunks), self.batch_size):
            batch = chunks[i : i + self.batch_size]
            texts = [c.content for c in batch]
            # 呼叫 Embedding 模型，回傳 list[list[float]]
            embeddings = self._embedder.embed_documents(texts)

            # Milvus insert 要求每個欄位是獨立的 list（列優先格式）
            data = [
                [c.chunk_id for c in batch],
                [c.doc_hash for c in batch],
                [c.source for c in batch],
                [c.section for c in batch],
                [c.content[:4090] for c in batch],  # 截斷以符合欄位長度上限
                [c.token_count for c in batch],
                [c.page_hint or 0 for c in batch],  # page_number（0 表示未知）
                embeddings,
            ]
            self._collection.insert(data)
            stored += len(batch)
            logger.info(f"Embedded & stored batch {i // self.batch_size + 1}: {len(batch)} chunks")

        # flush 確保資料落盤，查詢前必須呼叫
        self._collection.flush()
        return stored

    def embed_query(self, text: str) -> list[float]:
        """將查詢文字轉換為向量（用於查詢時，與 embed_documents 略有不同）。"""
        return self._embedder.embed_query(text)

    # ------------------------------------------------------------------

    def _get_or_create_collection(self) -> Collection:
        """取得已存在的 Collection，或建立新 Collection 並設定索引。

        索引類型：IVF_FLAT（Inverted File Index）
            - 將向量空間分成 nlist=128 個 cluster
            - 查詢時只搜索最近的 nprobe 個 cluster，大幅加速搜索
        距離度量：IP（Inner Product，內積）
            - 向量已歸一化的情況下，IP ≈ cosine similarity
            - nomic-embed-text 輸出的向量預設已歸一化
        """
        if utility.has_collection(COLLECTION_NAME):
            # Collection 已存在，直接載入到記憶體供查詢
            col = Collection(COLLECTION_NAME)
            col.load()
            return col

        schema = _build_schema(self._embedding_dim)
        col = Collection(COLLECTION_NAME, schema)

        # 建立向量索引（IVF_FLAT + Inner Product）
        col.create_index(
            "embedding",
            {
                "index_type": "IVF_FLAT",
                "metric_type": "IP",  # Inner Product ≈ cosine on normalised vectors
                "params": {"nlist": 128},  # 將向量空間分成 128 個群組
            },
        )
        col.load()
        logger.info(f"Created Milvus collection: {COLLECTION_NAME}")
        return col
