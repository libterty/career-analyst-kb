"""Feedback Router — 回覆品質評分端點。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user, require_role
from src.api.dependencies import get_db
from src.application.dto.feedback_dto import FeedbackCreateDTO, FeedbackResponseDTO, FeedbackStatsDTO
from src.infrastructure.persistence.models import User
from src.infrastructure.persistence.models.chat import ChatMessage
from src.infrastructure.repositories.feedback_repository import SQLAlchemyFeedbackRepository
from sqlalchemy import select

router = APIRouter(prefix="/api/feedback", tags=["Feedback"])


async def _verify_message_ownership(
    message_id: int,
    user_id: int,
    db: AsyncSession,
) -> ChatMessage:
    """確認訊息屬於該使用者的 session。"""
    from src.infrastructure.persistence.models.chat import ChatSession

    result = await db.execute(
        select(ChatMessage)
        .join(ChatSession, ChatSession.session_id == ChatMessage.session_id)
        .where(ChatMessage.id == message_id, ChatSession.user_id == user_id)
    )
    msg = result.scalar_one_or_none()
    if msg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="訊息不存在或無權限評分",
        )
    return msg


@router.post("", response_model=FeedbackResponseDTO, status_code=201)
async def submit_feedback(
    body: FeedbackCreateDTO,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """提交或更新訊息評分（每位使用者對每則訊息只保留最新評分）。"""
    await _verify_message_ownership(body.message_id, current_user.id, db)
    repo = SQLAlchemyFeedbackRepository(db)
    feedback = await repo.upsert(
        message_id=body.message_id,
        user_id=current_user.id,
        rating=body.rating,
        comment=body.comment,
    )
    return feedback


@router.get("/stats/{session_id}", response_model=FeedbackStatsDTO)
async def get_session_feedback_stats(
    session_id: str,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """取得指定 session 的評分統計（只能查自己的 session）。"""
    from src.infrastructure.persistence.models.chat import ChatSession

    result = await db.execute(
        select(ChatSession).where(
            ChatSession.session_id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Session 不存在")

    repo = SQLAlchemyFeedbackRepository(db)
    return await repo.get_stats_by_session(session_id)