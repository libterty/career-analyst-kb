"""KnowledgeGap repository — upsert by question_hash (same question seen again → increment occurrences)."""
from __future__ import annotations

from typing import Literal

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.persistence.models.knowledge_gap import KnowledgeGap

KnowledgeGapStatus = Literal["open", "reviewed", "resolved"]


class SQLAlchemyKnowledgeGapRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_all(
        self,
        status: KnowledgeGapStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[KnowledgeGap]:
        q = select(KnowledgeGap).order_by(desc(KnowledgeGap.occurrences), desc(KnowledgeGap.last_seen_at))
        if status is not None:
            q = q.where(KnowledgeGap.status == status)
        q = q.limit(limit).offset(offset)
        result = await self._db.execute(q)
        return list(result.scalars().all())

    async def update_status(self, gap_id: int, status: KnowledgeGapStatus) -> KnowledgeGap | None:
        result = await self._db.execute(select(KnowledgeGap).where(KnowledgeGap.id == gap_id))
        gap = result.scalar_one_or_none()
        if gap is None:
            return None
        await self._db.execute(update(KnowledgeGap).where(KnowledgeGap.id == gap_id).values(status=status))
        await self._db.refresh(gap)
        return gap

    async def upsert(
        self,
        question_hash: str,
        redacted_question: str,
        agent_name: str,
        trigger: str,
        quality_score: float | None,
    ) -> KnowledgeGap:
        result = await self._db.execute(
            select(KnowledgeGap).where(KnowledgeGap.question_hash == question_hash)
        )
        existing = result.scalar_one_or_none()

        if existing is not None:
            await self._db.execute(
                update(KnowledgeGap)
                .where(KnowledgeGap.id == existing.id)
                .values(
                    occurrences=KnowledgeGap.occurrences + 1,
                    quality_score=quality_score,
                )
            )
            await self._db.refresh(existing)
            return existing

        gap = KnowledgeGap(
            question_hash=question_hash,
            redacted_question=redacted_question,
            agent_name=agent_name,
            trigger=trigger,
            quality_score=quality_score,
        )
        self._db.add(gap)
        await self._db.flush()
        return gap
