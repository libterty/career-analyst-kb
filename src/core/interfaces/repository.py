"""Repository 介面（Repository Pattern + DIP）。

高階服務只依賴這些介面，不依賴 SQLAlchemy 具體實作。
可在測試時替換為 InMemory 實作，無需真實資料庫。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from src.core.domain.chunk import Chunk


class IUserRepository(ABC):
    """使用者資料存取介面。"""

    @abstractmethod
    async def find_by_username(self, username: str) -> Any | None:
        """依使用者名稱查詢，找不到回傳 None。"""

    @abstractmethod
    async def create(
        self,
        username: str,
        hashed_password: str,
        role: str,
    ) -> Any:
        """建立新使用者並回傳 ORM 實例。"""

    @abstractmethod
    async def find_by_id(self, user_id: int) -> Any | None:
        """依 ID 查詢使用者，找不到回傳 None。"""

    @abstractmethod
    async def list_all(self) -> Sequence[Any]:
        """取得所有使用者（依建立時間排序）。"""

    @abstractmethod
    async def delete(self, user_id: int) -> bool:
        """刪除指定使用者，成功回傳 True。"""

    @abstractmethod
    async def update_max_sessions(self, user_id: int, max_sessions: int) -> None:
        """更新使用者的 Session 數量上限。"""

    @abstractmethod
    async def update_password(self, user_id: int, hashed_password: str) -> None:
        """更新使用者密碼（已雜湊）。"""

    @abstractmethod
    async def count_by_role(self, role: str) -> int:
        """計算指定角色的使用者數量。"""


class IDocumentRepository(ABC):
    """文件 metadata 資料存取介面。"""

    @abstractmethod
    async def create(
        self,
        filename: str,
        doc_hash: str,
        pages: int,
        chunk_count: int,
        uploaded_by: int,
    ) -> Any:
        """新增文件紀錄。"""

    @abstractmethod
    async def list_all(self) -> Sequence[Any]:
        """取得所有文件（依上傳時間倒序）。"""

    @abstractmethod
    async def find_by_hash(self, doc_hash: str) -> Any | None:
        """依 SHA-256 指紋查詢，避免重複匯入。"""

    @abstractmethod
    async def find_by_id(self, document_id: int) -> Any | None:
        """依 ID 查詢文件，找不到回傳 None。"""

    @abstractmethod
    async def delete(self, document_id: int) -> bool:
        """刪除指定文件紀錄，成功回傳 True。"""


class IVectorRepository(ABC):
    """向量資料庫寫入介面（Milvus）。

    與 IVectorRetriever（讀取）分開，符合 ISP。
    """

    @abstractmethod
    def store_chunks(
        self,
        chunks: list["Chunk"],
        embeddings: list[list[float]],
    ) -> int:
        """批次儲存切塊向量，回傳成功寫入數量。"""

    @abstractmethod
    def delete_by_doc_hash(self, doc_hash: str) -> int:
        """刪除指定文件的所有向量，回傳刪除數量。"""


class IChatSessionRepository(ABC):
    """聊天 Session 資料存取介面。"""

    @abstractmethod
    async def create_session(
        self,
        session_id: str,
        user_id: int,
        title: str | None = None,
    ) -> Any:
        """建立新 session。"""

    @abstractmethod
    async def find_by_session_id(self, session_id: str) -> Any | None:
        """依 session_id 查詢，找不到回傳 None。"""

    @abstractmethod
    async def list_by_user(
        self,
        user_id: int,
        limit: int,
        offset: int,
    ) -> Sequence[Any]:
        """取得指定使用者的 session 列表（依更新時間倒序）。"""

    @abstractmethod
    async def update_title(self, session_id: str, title: str) -> None:
        """更新 session 標題。"""

    @abstractmethod
    async def delete_session(self, session_id: str) -> bool:
        """刪除指定 session，成功回傳 True。"""

    @abstractmethod
    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
    ) -> Any:
        """新增訊息到 session。"""

    @abstractmethod
    async def get_messages(
        self,
        session_id: str,
        limit: int = 100,
    ) -> Sequence[Any]:
        """取得 session 訊息列表。"""

    @abstractmethod
    async def get_message_count(self, session_id: str) -> int:
        """取得 session 訊息數量。"""

    @abstractmethod
    async def count_by_user(self, user_id: int) -> int:
        """取得指定使用者的 session 數量。"""

    @abstractmethod
    async def increment_message_count(self, session_id: str) -> None:
        """將 session 訊息計數加一。"""
