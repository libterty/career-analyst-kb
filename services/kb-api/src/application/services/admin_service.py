"""Admin Service — 管理員使用者管理業務邏輯。

職責（SRP）：
    - 列出所有使用者
    - 建立新使用者（admin 角色限制只允許一個）
    - 刪除使用者（防止刪除唯一管理員）
    - 更新使用者密碼
"""
from __future__ import annotations

from fastapi import HTTPException, status

from src.application.dto.auth_dto import UserListItemDTO, UserUpdateMaxSessionsDTO
from src.core.interfaces.repository import IUserRepository


class AdminService:
    """管理員使用者管理服務。"""

    def __init__(self, user_repo: IUserRepository) -> None:
        self._user_repo = user_repo

    async def list_users(self) -> list[UserListItemDTO]:
        """列出所有使用者。"""
        users = await self._user_repo.list_all()
        return [
            UserListItemDTO(
                id=u.id,
                username=u.username,
                role=u.role,
                max_sessions=u.max_sessions,
                created_at=u.created_at,
            )
            for u in users
        ]

    async def create_user(
        self, username: str, password: str, role: str = "viewer"
    ) -> dict:
        """建立新使用者。

        規則：admin 角色只允許一個；帳號不能重複。

        Raises:
            HTTPException 400: 試圖建立第二個 admin
            HTTPException 409: 使用者名稱已存在
        """
        from src.api.auth import hash_password

        if role == "admin":
            admin_count = await self._user_repo.count_by_role("admin")
            if admin_count > 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="系統已有管理員帳號，不允許建立第二個 admin",
                )

        existing = await self._user_repo.find_by_username(username)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"用戶名 '{username}' 已存在",
            )

        hashed = hash_password(password)
        user = await self._user_repo.create(username, hashed, role)
        return {"id": user.id, "username": user.username, "role": user.role}

    async def delete_user(self, user_id: int) -> dict:
        """刪除指定使用者。

        規則：不允許刪除唯一的管理員帳號。

        Raises:
            HTTPException 404: 使用者不存在
            HTTPException 400: 試圖刪除唯一管理員
        """
        user = await self._user_repo.find_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"使用者 ID={user_id} 不存在",
            )

        if user.role == "admin":
            admin_count = await self._user_repo.count_by_role("admin")
            if admin_count <= 1:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="無法刪除唯一的管理員帳號",
                )

        await self._user_repo.delete(user_id)
        return {"message": f"使用者 '{user.username}' 已刪除"}

    async def update_max_sessions(self, user_id: int, max_sessions: int) -> dict:
        """更新使用者的 Session 數量上限。

        Raises:
            HTTPException 404: 使用者不存在
        """
        user = await self._user_repo.find_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"使用者 ID={user_id} 不存在",
            )
        await self._user_repo.update_max_sessions(user_id, max_sessions)
        return {"message": f"使用者 '{user.username}' 的對話上限已更新為 {max_sessions}"}

    async def update_password(self, user_id: int, new_password: str) -> dict:
        """更新使用者密碼。

        Raises:
            HTTPException 404: 使用者不存在
        """
        from src.api.auth import hash_password

        user = await self._user_repo.find_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"使用者 ID={user_id} 不存在",
            )

        hashed = hash_password(new_password)
        await self._user_repo.update_password(user_id, hashed)
        return {"message": f"使用者 '{user.username}' 密碼已更新"}
