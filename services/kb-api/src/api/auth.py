"""JWT 認證工具函式。"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.infrastructure.persistence.models import User
from src.api.dependencies import get_db

# JWT 簽名密鑰（務必在正式環境中替換為隨機 32 字元以上的字串）
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME_IN_PRODUCTION_USE_RANDOM_32_CHARS")
ALGORITHM = "HS256"  # JWT 簽名演算法
# Token 有效期（分鐘），預設 480 分鐘（8 小時）
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))

# bcrypt 密碼雜湊器（自動處理 salt 與多輪雜湊）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# OAuth2 Bearer Token 解析器，指定取得 token 的端點
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def verify_password(plain: str, hashed: str) -> bool:
    """驗證明文密碼是否與雜湊值相符。"""
    return pwd_context.verify(plain, hashed)


def hash_password(password: str) -> str:
    """將明文密碼進行 bcrypt 雜湊（註冊時使用）。"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """建立 JWT Access Token。

    Args:
        data:          要編碼的 Payload（通常含 sub=username、role=角色）
        expires_delta: 自訂有效期，None 則使用預設值

    Returns:
        簽名後的 JWT 字串
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode["exp"] = expire  # JWT 標準的過期時間欄位
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI Dependency：從請求的 Bearer Token 解析並驗證當前使用者。

    Args:
        token: Authorization Header 中的 JWT Token
        db:    資料庫 Session（由 FastAPI DI 注入）

    Returns:
        驗證成功的 User ORM 物件

    Raises:
        HTTPException 401: Token 無效、過期或使用者不存在
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="無效的認證憑證",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        # 解碼 JWT，驗證簽名與過期時間
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")  # sub 欄位存放使用者名稱
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # 從資料庫確認使用者存在
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None:
        raise credentials_exception
    return user


def require_role(*roles: str):
    """FastAPI Dependency 工廠：建立角色權限檢查 Dependency。

    用法：
        @router.post("/upload")
        async def upload(current_user=Depends(require_role("editor", "admin"))):
            ...

    Args:
        *roles: 允許存取的角色列表

    Returns:
        FastAPI Dependency 函式，通過則回傳 User，否則拋出 403
    """
    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要 {'/'.join(roles)} 權限",
            )
        return current_user
    return dependency
