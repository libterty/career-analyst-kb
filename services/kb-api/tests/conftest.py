"""Shared pytest fixtures and sys.modules stubs for packages unavailable in the host venv."""
from __future__ import annotations

import sys
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Stub packages installed inside Docker but not in the host venv.
# Must be registered BEFORE any module that imports them is loaded.
# ---------------------------------------------------------------------------

class _FakeConversationBufferWindowMemory:
    def __init__(self, **kwargs):
        pass

    def load_memory_variables(self, inputs):
        return {"history": []}

    def save_context(self, inputs, outputs):
        pass


class _FakeMessage:
    def __init__(self, content: str = ""):
        self.content = content


# --- langchain stubs ---
_langchain_memory = MagicMock()
_langchain_memory.ConversationBufferWindowMemory = _FakeConversationBufferWindowMemory

_langchain_schema = MagicMock()
_langchain_schema.HumanMessage = _FakeMessage
_langchain_schema.SystemMessage = _FakeMessage
_langchain_schema.AIMessage = _FakeMessage

# --- fastapi stubs ---
class _FakeHTTPException(Exception):
    def __init__(self, status_code: int = 500, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)

class _FakeStatus:
    HTTP_200_OK = 200
    HTTP_429_TOO_MANY_REQUESTS = 429
    HTTP_500_INTERNAL_SERVER_ERROR = 500

_fastapi_mod = MagicMock()
_fastapi_mod.HTTPException = _FakeHTTPException
_fastapi_mod.status = _FakeStatus

# --- SQLAlchemy stub (thin — only what chat_session_repository needs at import) ---
_sqlalchemy_mod = MagicMock()
_sqlalchemy_mod.func = MagicMock()
_sqlalchemy_mod.select = MagicMock()
_sqlalchemy_mod.text = MagicMock()
_sqlalchemy_mod.update = MagicMock()
_sqlalchemy_mod.Integer = MagicMock()
_sqlalchemy_mod.String = MagicMock()
_sqlalchemy_mod.Column = MagicMock()

_sqlalchemy_ext_asyncio = MagicMock()
_sqlalchemy_orm = MagicMock()

# Fake SQLAlchemyChatSessionRepository (avoids importing the real infra module)
class _FakeSQLAlchemyChatSessionRepository:
    def __init__(self, session):
        self._session = session

_chat_session_repo_mod = MagicMock()
_chat_session_repo_mod.SQLAlchemyChatSessionRepository = _FakeSQLAlchemyChatSessionRepository

for _name, _mod in [
    ("langchain.memory", _langchain_memory),
    ("langchain.schema", _langchain_schema),
    ("fastapi", _fastapi_mod),
    ("fastapi.security", MagicMock()),
    ("fastapi.responses", MagicMock()),
    ("sqlalchemy", _sqlalchemy_mod),
    ("sqlalchemy.ext", MagicMock()),
    ("sqlalchemy.ext.asyncio", _sqlalchemy_ext_asyncio),
    ("sqlalchemy.orm", _sqlalchemy_orm),
    ("src.infrastructure.repositories.chat_session_repository", _chat_session_repo_mod),
]:
    if _name not in sys.modules:
        sys.modules[_name] = _mod
