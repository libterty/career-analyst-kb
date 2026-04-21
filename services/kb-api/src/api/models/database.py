"""向後相容的 re-export。

ORM 模型已移至 src/infrastructure/persistence/，
此檔案保留匯入路徑以維持向後相容性。

注意：新程式碼請直接引入：
    from src.infrastructure.persistence.models import User, Document, ...
    from src.infrastructure.persistence.database import get_db, create_tables
"""
from src.infrastructure.persistence.database import (  # noqa: F401
    AsyncSessionLocal,
    Base,
    create_tables,
    engine,
    get_db,
)
from src.infrastructure.persistence.models import (  # noqa: F401
    ChatMessage,
    ChatSession,
    Document,
    User,
)

__all__ = [
    "AsyncSessionLocal",
    "Base",
    "ChatMessage",
    "ChatSession",
    "Document",
    "User",
    "create_tables",
    "engine",
    "get_db",
]
