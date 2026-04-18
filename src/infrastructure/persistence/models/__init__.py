"""PostgreSQL ORM 模型。

各 model 拆分於獨立檔案，此 __init__.py 統一 re-export，
讓現有的 `from src.infrastructure.persistence.models import User` 等 import 無需修改。
Alembic autogenerate 只需 import 此 package 即可掃描所有 model。
"""
from src.infrastructure.persistence.models.user import User
from src.infrastructure.persistence.models.chat import ChatSession, ChatMessage
from src.infrastructure.persistence.models.document import Document
from src.infrastructure.persistence.models.feedback import MessageFeedback
from src.infrastructure.persistence.models.system_prompt import SystemPrompt
from src.infrastructure.persistence.models.semantic_cache import SemanticCacheEntry

__all__ = [
    "User", "ChatSession", "ChatMessage", "Document",
    "MessageFeedback", "SystemPrompt", "SemanticCacheEntry",
]

