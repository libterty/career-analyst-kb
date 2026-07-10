"""KnowledgeGaps Router — 接收 KB agent 回報的低品質答案記錄。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.application.dto.knowledge_gap_dto import KnowledgeGapCreateDTO, KnowledgeGapResponseDTO
from src.infrastructure.repositories.knowledge_gap_repository import SQLAlchemyKnowledgeGapRepository

router = APIRouter(prefix="/api/knowledge-gaps", tags=["KnowledgeGaps"])


@router.post("", response_model=KnowledgeGapResponseDTO, status_code=201)
async def record_knowledge_gap(
    body: KnowledgeGapCreateDTO,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """記錄一筆知識缺口（由 KB agent 的 answer-quality middleware 呼叫）。

    相同 question_hash 的記錄會累加 occurrences，而非建立新記錄。
    此端點不需要使用者認證（由內部 agent 呼叫）。
    """
    repo = SQLAlchemyKnowledgeGapRepository(db)
    gap = await repo.upsert(
        question_hash=body.question_hash,
        redacted_question=body.redacted_question,
        agent_name=body.agent_name,
        trigger=body.trigger,
        quality_score=body.quality_score,
    )
    await db.commit()
    await db.refresh(gap)
    return gap
