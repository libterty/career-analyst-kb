"""Phase 1 — Ingestion Pipeline
orchestrates: parse → chunk → embed → store
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

from .chunker import SmartChunker
from .embedder import EmbeddingService
from .pdf_parser import DocumentParser


class IngestionPipeline:
    """文件匯入管線的統一入口。

    依序執行：解析 → 切塊 → 向量化 → 寫入 Milvus
    對外只需呼叫 ingest_file() 或 ingest_directory()，內部細節完全封裝。
    """

    def __init__(
        self,
        milvus_host: str = "localhost",
        milvus_port: int = 19530,
    ) -> None:
        self._parser = DocumentParser()
        # max_tokens=512：每塊最多 512 token（約 600-800 中文字）
        # chunk_overlap=64：相鄰塊重疊 64 token，防止答案被切斷
        self._chunker = SmartChunker(max_tokens=512, chunk_overlap=64)
        self._embedder = EmbeddingService(milvus_host=milvus_host, milvus_port=milvus_port)

    def ingest_file(self, path: str | Path) -> dict:
        """匯入單一文件並回傳匯入統計。

        Args:
            path: 文件路徑（支援 .pdf / .docx / .doc）

        Returns:
            包含 filename、doc_hash、pages、chunks、stored 的統計字典
        """
        path = Path(path)
        logger.info(f"[Pipeline] Ingesting: {path.name}")

        # Step 1：解析文件 → 取得純文字與 metadata
        doc = self._parser.parse(path)
        # Step 2：切塊 → 依章節與 token 上限分割
        chunks = self._chunker.chunk(doc)
        # Step 3：向量化 + 寫入 Milvus
        stored = self._embedder.embed_and_store(chunks)

        result = {
            "filename": path.name,
            "doc_hash": doc.doc_hash,
            "pages": doc.pages,
            "chunks": len(chunks),
            "stored": stored,
        }
        logger.success(f"[Pipeline] Done: {result}")
        return result

    def reingest_file(self, path: str | Path) -> dict:
        """重新匯入文件：若內容未變則跳過，否則刪除舊向量後重新匯入。

        流程：
            1. 解析文件取得 doc_hash
            2. 查詢 Milvus：相同 source + doc_hash 是否已存在
            3. 已存在（內容未變） → 跳過，回傳 skipped=True
            4. 不存在（新檔或已更新） → 刪除舊向量，重新匯入

        Args:
            path: 文件路徑

        Returns:
            統計字典，包含 filename、doc_hash、pages、chunks、stored、deleted、skipped
        """
        path = Path(path)
        doc = self._parser.parse(path)

        if self._embedder.exists_by_hash_and_source(doc.doc_hash, path.name):
            logger.info(f"[Pipeline] Skipped (unchanged): {path.name}")
            return {
                "filename": path.name,
                "doc_hash": doc.doc_hash,
                "pages": doc.pages,
                "chunks": 0,
                "stored": 0,
                "deleted": 0,
                "skipped": True,
            }

        logger.info(f"[Pipeline] Re-ingesting: {path.name}")
        deleted = self._embedder.delete_by_source(path.name)
        chunks = self._chunker.chunk(doc)
        stored = self._embedder.embed_and_store(chunks)

        result = {
            "filename": path.name,
            "doc_hash": doc.doc_hash,
            "pages": doc.pages,
            "chunks": len(chunks),
            "stored": stored,
            "deleted": deleted,
            "skipped": False,
        }
        logger.success(f"[Pipeline] Re-ingested: {result}")
        return result

    def reingest_directory(self, directory: str | Path) -> list[dict]:
        """批次重新匯入目錄內所有支援格式的文件。"""
        directory = Path(directory)
        supported = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".txt",
                     ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp",
                     ".md", ".markdown"}
        files = [f for f in directory.iterdir() if f.suffix.lower() in supported]
        logger.info(f"[Pipeline] Re-ingesting {len(files)} documents in {directory}")
        return [self.reingest_file(f) for f in files]

    def ingest_directory(self, directory: str | Path) -> list[dict]:
        """批次匯入目錄內所有支援格式的文件。

        Args:
            directory: 目標目錄路徑

        Returns:
            每個文件的匯入統計列表
        """
        directory = Path(directory)
        supported = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".txt",
                     ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp",
                     ".md", ".markdown"}
        files = [f for f in directory.iterdir() if f.suffix.lower() in supported]
        logger.info(f"[Pipeline] Found {len(files)} documents in {directory}")
        return [self.ingest_file(f) for f in files]
