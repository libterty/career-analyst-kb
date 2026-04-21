"""Documents Router（精簡 HTTP 層）。

Router 只負責：
    - 接收 HTTP 上傳檔案
    - 串流寫入臨時檔案（防止大檔案耗盡記憶體）
    - 呼叫 IngestionService（業務邏輯）
    - 格式化回應 DTO

DB 寫入、向量化等業務邏輯已移至 IngestionService。
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from loguru import logger

from src.api.auth import require_role
from src.api.dependencies import get_document_repo, get_ingestion_service
from src.application.dto.document_dto import (
    DeleteDocumentResponseDTO,
    DocumentListItemDTO,
    ReingestResponseDTO,
    UploadResponseDTO,
)
from src.application.services.ingestion_service import IngestionService
from src.infrastructure.repositories.document_repository import SQLAlchemyDocumentRepository

router = APIRouter(prefix="/api/documents", tags=["Documents"])

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".pptx"}
MAX_FILE_SIZE_MB = 50

IngestionServiceDep = Annotated[IngestionService, Depends(get_ingestion_service)]
DocumentRepoDep = Annotated[SQLAlchemyDocumentRepository, Depends(get_document_repo)]


@router.post("/upload", response_model=UploadResponseDTO)
async def upload_document(
    file: UploadFile = File(...),
    current_user=Depends(require_role("editor", "admin")),
    ingestion_service: IngestionServiceDep = None,
):
    """上傳文件並匯入知識庫。

    流程：
        1. 驗證檔案格式
        2. 串流寫入臨時檔案（防止大檔案耗盡記憶體）
        3. 呼叫 IngestionService（解析 → 切塊 → 向量化 → 儲存）
        4. 刪除臨時檔案
    """
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支援的檔案格式: {suffix}")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        size = 0
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_FILE_SIZE_MB * 1024 * 1024:
                raise HTTPException(
                    status_code=413,
                    detail=f"檔案超過 {MAX_FILE_SIZE_MB}MB 限制",
                )
            tmp.write(chunk)
        tmp_path = Path(tmp.name)

    try:
        result = await ingestion_service.ingest_file(tmp_path, current_user.id)
    except Exception as exc:
        logger.exception(f"Ingestion failed: {exc}")
        raise HTTPException(status_code=500, detail=f"文件處理失敗: {str(exc)}")
    finally:
        tmp_path.unlink(missing_ok=True)

    return UploadResponseDTO(
        filename=file.filename,
        doc_hash=result["doc_hash"],
        pages=result["pages"],
        chunks=result["chunks"],
        stored=result["stored"],
    )


@router.get("/list", response_model=list[DocumentListItemDTO])
async def list_documents(
    current_user=Depends(require_role("viewer", "editor", "admin")),
    document_repo: DocumentRepoDep = None,
):
    """列出所有已匯入的文件（依上傳時間倒序排列）。"""
    docs = await document_repo.list_all()
    return [
        DocumentListItemDTO(
            id=d.id,
            filename=d.filename,
            doc_hash=d.doc_hash,
            pages=d.pages,
            chunk_count=d.chunk_count,
            uploaded_at=d.uploaded_at,
        )
        for d in docs
    ]


@router.delete("/{doc_id}", response_model=DeleteDocumentResponseDTO)
async def delete_document(
    doc_id: int,
    current_user=Depends(require_role("editor", "admin")),
    ingestion_service: IngestionServiceDep = None,
):
    """刪除指定文件及其在向量資料庫中的所有向量。"""
    result = await ingestion_service.delete_document(doc_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"文件 ID {doc_id} 不存在")
    return DeleteDocumentResponseDTO(**result)


@router.post("/{doc_id}/reingest", response_model=ReingestResponseDTO)
async def reingest_document(
    doc_id: int,
    file: UploadFile = File(...),
    current_user=Depends(require_role("editor", "admin")),
    ingestion_service: IngestionServiceDep = None,
):
    """以新版文件取代舊版：先刪除舊向量，再匯入新文件。"""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支援的檔案格式: {suffix}")

    delete_result = await ingestion_service.delete_document(doc_id)
    if delete_result is None:
        raise HTTPException(status_code=404, detail=f"文件 ID {doc_id} 不存在")

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        size = 0
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_FILE_SIZE_MB * 1024 * 1024:
                raise HTTPException(
                    status_code=413,
                    detail=f"檔案超過 {MAX_FILE_SIZE_MB}MB 限制",
                )
            tmp.write(chunk)
        tmp_path = Path(tmp.name)

    try:
        ingest_result = await ingestion_service.ingest_file(tmp_path, current_user.id)
    except Exception as exc:
        logger.exception(f"Reingest failed: {exc}")
        raise HTTPException(status_code=500, detail=f"文件處理失敗: {str(exc)}")
    finally:
        tmp_path.unlink(missing_ok=True)

    return ReingestResponseDTO(
        document_id=doc_id,
        filename=file.filename,
        doc_hash=ingest_result["doc_hash"],
        pages=ingest_result["pages"],
        chunks=ingest_result["chunks"],
        stored=ingest_result["stored"],
        deleted_chunks=delete_result["deleted_chunks"],
    )
