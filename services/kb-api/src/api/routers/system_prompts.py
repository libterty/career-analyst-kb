"""System Prompts Router — 管理員管理系統提示詞端點。"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import require_role
from src.api.dependencies import get_db
from src.application.dto.system_prompt_dto import (
    SystemPromptCreateDTO,
    SystemPromptResponseDTO,
    SystemPromptUpdateDTO,
)
from src.infrastructure.persistence.models import User
from src.infrastructure.repositories.system_prompt_repository import SQLAlchemySystemPromptRepository

router = APIRouter(prefix="/api/admin/system-prompts", tags=["Admin"])

AdminUserDep = Annotated[User, Depends(require_role("admin"))]
DbDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[SystemPromptResponseDTO])
async def list_system_prompts(
    _current_user: AdminUserDep,
    db: DbDep,
):
    """列出所有系統提示詞（需 admin 權限）。"""
    repo = SQLAlchemySystemPromptRepository(db)
    return await repo.list_all()


@router.post("", response_model=SystemPromptResponseDTO, status_code=201)
async def create_system_prompt(
    body: SystemPromptCreateDTO,
    current_user: AdminUserDep,
    db: DbDep,
):
    """建立新系統提示詞（需 admin 權限）。"""
    from sqlalchemy.exc import IntegrityError
    repo = SQLAlchemySystemPromptRepository(db)
    try:
        return await repo.create(
            name=body.name,
            content=body.content,
            created_by=current_user.id,
        )
    except IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"提示詞名稱「{body.name}」已存在")


@router.put("/{prompt_id}", response_model=SystemPromptResponseDTO)
async def update_system_prompt(
    prompt_id: int,
    body: SystemPromptUpdateDTO,
    _current_user: AdminUserDep,
    db: DbDep,
):
    """更新提示詞內容（需 admin 權限）。"""
    repo = SQLAlchemySystemPromptRepository(db)
    prompt = await repo.update_content(prompt_id, body.content, name=body.name)
    if prompt is None:
        raise HTTPException(status_code=404, detail="提示詞不存在")
    return prompt


@router.post("/{prompt_id}/activate", response_model=SystemPromptResponseDTO)
async def toggle_system_prompt(
    prompt_id: int,
    _current_user: AdminUserDep,
    db: DbDep,
):
    """切換提示詞啟用狀態（需 admin 權限）。"""
    repo = SQLAlchemySystemPromptRepository(db)
    prompt = await repo.toggle_active(prompt_id)
    if prompt is None:
        raise HTTPException(status_code=404, detail="提示詞不存在")
    return prompt


@router.delete("/{prompt_id}", response_model=dict)
async def delete_system_prompt(
    prompt_id: int,
    _current_user: AdminUserDep,
    db: DbDep,
):
    """刪除提示詞（不能刪除啟用中的提示詞，需 admin 權限）。"""
    repo = SQLAlchemySystemPromptRepository(db)
    try:
        deleted = await repo.delete(prompt_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    if not deleted:
        raise HTTPException(status_code=404, detail="提示詞不存在")
    return {"message": "已刪除"}