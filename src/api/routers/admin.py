"""Admin Router — 管理員使用者管理端點。

所有端點需要 admin 角色才可存取。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from src.api.auth import require_role
from src.api.dependencies import get_admin_service
from src.application.dto.auth_dto import UserCreateDTO, UserListItemDTO, UserUpdateMaxSessionsDTO, UserUpdatePasswordDTO
from src.application.services.admin_service import AdminService
from src.infrastructure.persistence.models import User

router = APIRouter(prefix="/api/admin", tags=["Admin"])

AdminServiceDep = Annotated[AdminService, Depends(get_admin_service)]
AdminUserDep = Annotated[User, Depends(require_role("admin"))]


@router.get("/users", response_model=list[UserListItemDTO])
async def list_users(
    _current_user: AdminUserDep,
    admin_service: AdminServiceDep,
):
    """列出所有使用者（需 admin 權限）。"""
    return await admin_service.list_users()


@router.post("/users", response_model=dict, status_code=201)
async def create_user(
    user_in: UserCreateDTO,
    _current_user: AdminUserDep,
    admin_service: AdminServiceDep,
):
    """建立新使用者（需 admin 權限）。

    admin 角色限制只允許一個；建立第二個 admin 會回傳 400。
    """
    return await admin_service.create_user(
        username=user_in.username,
        password=user_in.password,
        role=user_in.role,
    )


@router.delete("/users/{user_id}", response_model=dict)
async def delete_user(
    user_id: int,
    _current_user: AdminUserDep,
    admin_service: AdminServiceDep,
):
    """刪除指定使用者（需 admin 權限）。

    不允許刪除唯一的管理員帳號。
    """
    return await admin_service.delete_user(user_id)


@router.patch("/users/{user_id}/password", response_model=dict)
async def update_user_password(
    user_id: int,
    body: UserUpdatePasswordDTO,
    _current_user: AdminUserDep,
    admin_service: AdminServiceDep,
):
    """更新指定使用者的密碼（需 admin 權限）。"""
    return await admin_service.update_password(user_id, body.new_password)


@router.patch("/users/{user_id}/max-sessions", response_model=dict)
async def update_user_max_sessions(
    user_id: int,
    body: UserUpdateMaxSessionsDTO,
    _current_user: AdminUserDep,
    admin_service: AdminServiceDep,
):
    """更新指定使用者的對話數量上限（需 admin 權限）。"""
    return await admin_service.update_max_sessions(user_id, body.max_sessions)
