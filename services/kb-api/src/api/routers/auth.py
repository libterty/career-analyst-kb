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

from src.api.auth import get_current_user
from src.api.dependencies import get_auth_service
from src.application.dto.auth_dto import TokenDTO, UserCreateDTO
from src.application.services.auth_service import AuthService
from src.core.exceptions import AuthenticationError
from src.infrastructure.persistence.models import User

router = APIRouter(prefix="/api/auth", tags=["Auth"])

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]


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
):
    """使用者登入，回傳 JWT Access Token（OAuth2 Password Flow）。"""
    try:
        token = await auth_service.authenticate(
            form_data.username, form_data.password
        )
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenDTO(access_token=token)


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
