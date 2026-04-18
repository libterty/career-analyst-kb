"""向後相容的 re-export。

Pydantic 資料結構已移至 src/application/dto/，
此檔案保留匯入路徑以維持向後相容性。

注意：新程式碼請直接引入：
    from src.application.dto.auth_dto import UserCreateDTO, TokenDTO
    from src.application.dto.chat_dto import ChatRequestDTO, ChatResponseDTO
    from src.application.dto.document_dto import UploadResponseDTO
"""
from src.application.dto.auth_dto import TokenDTO, UserCreateDTO  # noqa: F401
from src.application.dto.chat_dto import (  # noqa: F401
    ChatRequestDTO,
    ChatResponseDTO,
    SourceDocumentDTO,
)
from src.application.dto.document_dto import UploadResponseDTO  # noqa: F401

# 舊名稱別名（維持向後相容）
ChatRequest = ChatRequestDTO
ChatResponse = ChatResponseDTO
SourceDocument = SourceDocumentDTO
UploadResponse = UploadResponseDTO
Token = TokenDTO
UserCreate = UserCreateDTO

__all__ = [
    "ChatRequest",
    "ChatRequestDTO",
    "ChatResponse",
    "ChatResponseDTO",
    "SourceDocument",
    "SourceDocumentDTO",
    "Token",
    "TokenDTO",
    "UploadResponse",
    "UploadResponseDTO",
    "UserCreate",
    "UserCreateDTO",
]
