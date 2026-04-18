"""認證 Service（業務邏輯層）。

將登入/註冊的業務邏輯從 router 抽離，router 只負責 HTTP 協議層。
AuthService 依賴 IUserRepository 介面，不依賴 SQLAlchemy。
"""
from __future__ import annotations

from src.core.exceptions import AuthenticationError
from src.core.interfaces.repository import IUserRepository


class AuthService:
    """認證業務邏輯服務。

    職責（SRP）：
        - 驗證帳號密碼
        - 產生 JWT Token
        - 建立新使用者（含密碼雜湊）
        - 檢查使用者名稱重複
    """

    def __init__(
        self,
        user_repo: IUserRepository,
        secret_key: str,
        algorithm: str = "HS256",
        expire_minutes: int = 480,
    ) -> None:
        self._user_repo = user_repo
        self._secret_key = secret_key
        self._algorithm = algorithm
        self._expire_minutes = expire_minutes

    async def authenticate(self, username: str, password: str) -> str:
        """驗證帳號密碼，成功回傳 JWT Token。

        故意使用相同的錯誤訊息，防止帳號枚舉攻擊。

        Raises:
            AuthenticationError: 帳號不存在或密碼錯誤
        """
        from src.api.auth import create_access_token, verify_password

        user = await self._user_repo.find_by_username(username)
        if not user or not verify_password(password, user.hashed_password):
            raise AuthenticationError("用戶名或密碼錯誤")

        from datetime import timedelta

        return create_access_token(
            {"sub": user.username, "role": user.role},
            expires_delta=timedelta(minutes=self._expire_minutes),
        )

    async def register(
        self,
        username: str,
        password: str,
        role: str = "viewer",
    ) -> dict:
        """建立新使用者。

        Raises:
            AuthenticationError: 使用者名稱已存在
        """
        from src.api.auth import hash_password

        existing = await self._user_repo.find_by_username(username)
        if existing:
            raise AuthenticationError("用戶名已存在")

        hashed = hash_password(password)
        await self._user_repo.create(username, hashed, role)
        return {"message": f"用戶 {username} 建立成功", "role": role}
