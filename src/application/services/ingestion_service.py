"""文件匯入 Service（業務邏輯層）。

將匯入流程從 router 抽離，router 只負責接收 HTTP 上傳檔案。
IngestionService 依賴介面，不依賴具體 infrastructure 實作。
"""
from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.core.interfaces.repository import IDocumentRepository, IVectorRepository


class IngestionService:
    """文件匯入業務邏輯服務。

    職責（SRP）：
        - 解析文件（委派給 parser）
        - 切塊（委派給 chunker）
        - 向量化（委派給 embedder）
        - 儲存向量（委派給 vector_repo）
        - 儲存 metadata（委派給 document_repo）

    所有依賴透過建構子注入（DIP），可在測試中替換為 Mock。
    """

    def __init__(
        self,
        parser,
        chunker,
        embedder,
        vector_repo: IVectorRepository,
        document_repo: IDocumentRepository,
    ) -> None:
        self._parser = parser
        self._chunker = chunker
        self._embedder = embedder
        self._vector_repo = vector_repo
        self._document_repo = document_repo

    async def ingest_file(self, path: Path, uploaded_by: int) -> dict:
        """匯入單一文件並記錄 metadata。

        Args:
            path:        文件路徑
            uploaded_by: 上傳者的使用者 ID

        Returns:
            包含 filename、doc_hash、pages、chunks、stored 的統計字典
        """
        logger.info(f"[IngestionService] Ingesting: {path.name}")

        doc = self._parser.parse(path)
        chunks = self._chunker.chunk(doc)
        texts = [c.content for c in chunks]
        embeddings = self._embedder.embed_documents(texts)
        stored = self._vector_repo.store_chunks(chunks, embeddings)

        await self._document_repo.create(
            filename=path.name,
            doc_hash=doc.doc_hash,
            pages=doc.pages,
            chunk_count=len(chunks),
            uploaded_by=uploaded_by,
        )

        result = {
            "filename": path.name,
            "doc_hash": doc.doc_hash,
            "pages": doc.pages,
            "chunks": len(chunks),
            "stored": stored,
        }
        logger.success(f"[IngestionService] Done: {result}")
        return result

    async def delete_document(self, document_id: int) -> dict | None:
        """刪除文件及其在 Milvus 的所有向量。

        Args:
            document_id: DB 中的文件 ID

        Returns:
            包含 deleted_chunks（向量刪除數）的字典；
            文件不存在時回傳 None。
        """
        doc = await self._document_repo.find_by_id(document_id)
        if doc is None:
            return None

        deleted_chunks = self._vector_repo.delete_by_doc_hash(doc.doc_hash)
        await self._document_repo.delete(document_id)

        result = {
            "document_id": document_id,
            "filename": doc.filename,
            "doc_hash": doc.doc_hash,
            "deleted_chunks": deleted_chunks,
        }
        logger.success(f"[IngestionService] Deleted: {result}")
        return result
