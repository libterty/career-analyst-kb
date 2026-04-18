"""Sessions Router — 對話 Session 管理端點。

使用者可管理自己的 Session；所有端點需要登入。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import get_current_user
from src.api.dependencies import get_db, get_session_service
from src.application.dto.session_dto import (
    CreateSessionDTO,
    RenameSessionDTO,
    SessionDetailDTO,
    SessionListItemDTO,
)
from src.application.services.session_service import SessionService
from src.infrastructure.persistence.models import User

router = APIRouter(prefix="/api/sessions", tags=["Sessions"])

SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]


@router.get("", response_model=list[SessionListItemDTO])
async def list_sessions(
    current_user: CurrentUserDep,
    session_service: SessionServiceDep,
    page: int = 1,
    page_size: int = 20,
):
    """列出目前使用者的所有 Session（依更新時間倒序）。"""
    return await session_service.list_sessions(
        user_id=current_user.id,
        page=page,
        page_size=page_size,
    )


@router.post("", response_model=SessionListItemDTO, status_code=201)
async def create_session(
    body: CreateSessionDTO,
    current_user: CurrentUserDep,
    session_service: SessionServiceDep,
):
    """建立新的對話 Session。"""
    return await session_service.create_session(
        user_id=current_user.id,
        title=body.title,
        max_sessions=current_user.max_sessions,
    )


@router.get("/{session_id}", response_model=SessionDetailDTO)
async def get_session(
    session_id: str,
    current_user: CurrentUserDep,
    session_service: SessionServiceDep,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """取得指定 Session 的詳細資訊（含訊息列表）。

    若 Session 不屬於目前使用者，回傳 403。
    """
    from src.infrastructure.repositories.feedback_repository import SQLAlchemyFeedbackRepository
    feedback_repo = SQLAlchemyFeedbackRepository(db)
    ratings = await feedback_repo.get_ratings_by_session_user(session_id, current_user.id)
    return await session_service.get_session(
        session_id=session_id,
        user_id=current_user.id,
        ratings=ratings,

    )


@router.patch("/{session_id}", response_model=dict)
async def rename_session(
    session_id: str,
    body: RenameSessionDTO,
    current_user: CurrentUserDep,
    session_service: SessionServiceDep,
):
    """重新命名指定 Session。"""
    success = await session_service.rename_session(
        session_id=session_id,
        user_id=current_user.id,
        title=body.title,
    )
    return {"success": success}


@router.delete("/{session_id}", response_model=dict)
async def delete_session(
    session_id: str,
    current_user: CurrentUserDep,
    session_service: SessionServiceDep,
):
    """刪除指定 Session（連同所有訊息）。"""
    success = await session_service.delete_session(
        session_id=session_id,
        user_id=current_user.id,
    )
    return {"success": success}
