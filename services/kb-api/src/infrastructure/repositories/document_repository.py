"""SQLAlchemy 文件 Repository 實作。"""
from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.interfaces.repository import IDocumentRepository
from src.infrastructure.persistence.models import Document


class SQLAlchemyDocumentRepository(IDocumentRepository):
    """以 SQLAlchemy 實作的文件 metadata 資料存取層。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        filename: str,
        doc_hash: str,
        pages: int,
        chunk_count: int,
        uploaded_by: int,
    ) -> Document:
        doc = Document(
            filename=filename,
            doc_hash=doc_hash,
            pages=pages,
            chunk_count=chunk_count,
            uploaded_by=uploaded_by,
        )
        self._session.add(doc)
        await self._session.commit()
        await self._session.refresh(doc)
        return doc

    async def list_all(self) -> Sequence[Document]:
        result = await self._session.execute(
            select(Document).order_by(Document.uploaded_at.desc())
        )
        return result.scalars().all()

    async def find_by_hash(self, doc_hash: str) -> Document | None:
        result = await self._session.execute(
            select(Document).where(Document.doc_hash == doc_hash)
        )
        return result.scalar_one_or_none()

    async def find_by_id(self, document_id: int) -> Document | None:
        result = await self._session.execute(
            select(Document).where(Document.id == document_id)
        )
        return result.scalar_one_or_none()

    async def delete(self, document_id: int) -> bool:
        result = await self._session.execute(
            select(Document).where(Document.id == document_id)
        )
        doc = result.scalar_one_or_none()
        if doc is None:
            return False
        await self._session.delete(doc)
        await self._session.commit()
        return True
