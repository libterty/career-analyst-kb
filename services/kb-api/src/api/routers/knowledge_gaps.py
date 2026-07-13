"""KnowledgeGaps Router — 接收 KB agent 回報的低品質答案記錄。"""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_role
from src.api.dependencies import get_db
from src.application.dto.knowledge_gap_dto import KnowledgeGapCreateDTO, KnowledgeGapResponseDTO
from src.infrastructure.persistence.models import User
from src.infrastructure.repositories.knowledge_gap_repository import SQLAlchemyKnowledgeGapRepository

router = APIRouter(prefix="/api/knowledge-gaps", tags=["KnowledgeGaps"])

AdminUserDep = Annotated[User, Depends(require_role("admin"))]


class KnowledgeGapStatusUpdateDTO(BaseModel):
    status: Literal["open", "reviewed", "resolved"]


@router.get("", response_model=list[KnowledgeGapResponseDTO])
async def list_knowledge_gaps(
    _: AdminUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
    status: Literal["open", "reviewed", "resolved"] | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """列出所有知識缺口記錄（僅限管理員）。按出現次數降序排列。"""
    repo = SQLAlchemyKnowledgeGapRepository(db)
    return await repo.list_all(status=status, limit=limit, offset=offset)


@router.patch("/{gap_id}/status", response_model=KnowledgeGapResponseDTO)
async def update_knowledge_gap_status(
    gap_id: int,
    body: KnowledgeGapStatusUpdateDTO,
    _: AdminUserDep,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """更新知識缺口狀態（open / reviewed / resolved）。"""
    repo = SQLAlchemyKnowledgeGapRepository(db)
    gap = await repo.update_status(gap_id, body.status)
    if gap is None:
        raise HTTPException(status_code=404, detail="Knowledge gap not found")
    await db.commit()
    await db.refresh(gap)
    return gap


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
