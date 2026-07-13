"""Auth Router（精簡 HTTP 層）。

Router 只負責：
    - 接收 HTTP 請求
    - 呼叫 AuthService（業務邏輯）
    - 格式化 HTTP 回應與錯誤碼

業務邏輯（帳號驗證、密碼雜湊、Token 產生）已移至 AuthService。
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.auth import (
    create_access_token,
    create_refresh_token,
    get_current_user,
    revoke_all_refresh_tokens,
    verify_and_rotate_refresh_token,
)
from src.api.dependencies import get_auth_service, get_db
from src.application.dto.auth_dto import TokenDTO, UserCreateDTO
from src.application.services.auth_service import AuthService
from src.core.config import get_settings
from src.core.exceptions import AuthenticationError
from src.infrastructure.persistence.models import User

router = APIRouter(prefix="/api/auth", tags=["Auth"])

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
DbDep = Annotated[AsyncSession, Depends(get_db)]


class RefreshRequest(BaseModel):
    refresh_token: str


@router.get("/me")
async def me(current_user: User = Depends(get_current_user)):
    """回傳目前登入的使用者資訊。"""
    return {
        "id": current_user.id,
        "username": current_user.username,
        "role": current_user.role,
        "max_sessions": current_user.max_sessions,
    }


@router.post("/token", response_model=TokenDTO)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthServiceDep = None,
    db: DbDep = None,
):
    """使用者登入，回傳 short-lived JWT Access Token 與 Refresh Token。"""
    try:
        access_token = await auth_service.authenticate(
            form_data.username, form_data.password
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

    result = await db.execute(select(User).where(User.username == form_data.username))
    user = result.scalar_one()
    settings = get_settings()
    refresh_token = await create_refresh_token(db, user.id, settings.refresh_token_expire_days)

    return TokenDTO(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenDTO)
async def refresh(body: RefreshRequest, db: DbDep = None):
    """使用 Refresh Token 換發新的 Access Token（token rotation）。"""
    user = await verify_and_rotate_refresh_token(db, body.refresh_token)
    settings = get_settings()
    new_refresh = await create_refresh_token(db, user.id, settings.refresh_token_expire_days)
    from datetime import timedelta
    access_token = create_access_token(
        {"sub": user.username, "role": user.role},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return TokenDTO(access_token=access_token, refresh_token=new_refresh)


@router.post("/logout", status_code=204)
async def logout(
    db: DbDep = None,
    current_user: User = Depends(get_current_user),
):
    """登出：撤銷目前使用者的所有 Refresh Token。"""
    await revoke_all_refresh_tokens(db, current_user.id)


@router.post("/register", response_model=dict, status_code=201)
async def register(
    user_in: UserCreateDTO,
    auth_service: AuthServiceDep = None,
):
    """註冊新使用者。

    注意：正式部署前應加上管理員驗證保護此端點。
    """
    try:
        return await auth_service.register(
            user_in.username, user_in.password, user_in.role
        )
    except AuthenticationError as e:
        raise HTTPException(status_code=409, detail=str(e))
