# 道輝 SOLID 架構 — Repository 與 Service 層

> 本文件說明系統如何應用 SOLID 原則，特別是 Repository Pattern 與分層架構。

**最後更新：2026-03-20**

---

## 架構分層

```
┌─────────────────────────────────────────┐
│         HTTP Layer (FastAPI Routers)    │  src/api/routers/
│    auth.py, chat.py, documents.py, ...  │
├─────────────────────────────────────────┤
│         Service Layer (Business Logic)  │  src/application/services/
│   ChatService, DocumentService, ...     │
├─────────────────────────────────────────┤
│        Repository Layer (Data Access)   │  src/infrastructure/repositories/
│   IUserRepository, IDocumentRepository  │
├─────────────────────────────────────────┤
│        ORM/Database Layer (Models)      │  src/infrastructure/persistence/
│    SQLAlchemy Models, Migrations        │
└─────────────────────────────────────────┘
```

---

## 1. 介面層（Interfaces）— 依賴倒置

位置：`src/core/interfaces/`

系統為所有主要元件定義介面，實作類別依賴於介面而非具體實作：

### IUserRepository — 使用者資料存取

```python
# src/core/interfaces/repository.py

class IUserRepository(ABC):
    """使用者資料庫存取介面。"""

    @abstractmethod
    async def find_by_id(self, user_id: int) -> User | None:
        """根據 ID 查詢使用者。"""
        pass

    @abstractmethod
    async def find_by_username(self, username: str) -> User | None:
        """根據帳號查詢使用者。"""
        pass

    @abstractmethod
    async def create(self, username: str, hashed_password: str, role: str = "user") -> User:
        """建立新使用者。"""
        pass

    @abstractmethod
    async def update(self, user_id: int, **kwargs) -> User:
        """更新使用者（支援 username, password, role 等欄位）。"""
        pass

    @abstractmethod
    async def delete(self, user_id: int) -> None:
        """刪除使用者。"""
        pass

    @abstractmethod
    async def list_all(self, page: int = 1, page_size: int = 20) -> list[User]:
        """分頁列出所有使用者。"""
        pass

    @abstractmethod
    async def count_by_role(self, role: str) -> int:
        """計算特定角色的使用者數。"""
        pass

    @abstractmethod
    async def update_password(self, user_id: int, hashed_password: str) -> User:
        """更新使用者密碼。"""
        pass

    @abstractmethod
    async def update_max_sessions(self, user_id: int, max_sessions: int) -> User:
        """更新使用者允許的最大 Session 數。"""
        pass
```

### IDocumentRepository — 文件資料存取

```python
class IDocumentRepository(ABC):
    """文件資料庫存取介面。"""

    @abstractmethod
    async def find_by_id(self, doc_id: str) -> Document | None:
        """根據 ID 查詢文件。"""
        pass

    @abstractmethod
    async def find_by_hash(self, doc_hash: str) -> Document | None:
        """根據文件指紋查詢（檢查重複）。"""
        pass

    @abstractmethod
    async def create(self, **kwargs) -> Document:
        """建立文件記錄。"""
        pass

    @abstractmethod
    async def delete(self, doc_id: str) -> None:
        """刪除文件記錄。"""
        pass

    @abstractmethod
    async def list_all(self, page: int = 1, page_size: int = 20) -> list[Document]:
        """分頁列出所有文件。"""
        pass
```

### IChatSessionRepository — Session 資料存取

```python
class IChatSessionRepository(ABC):
    """對話 Session 資料庫存取介面。"""

    @abstractmethod
    async def create(self, user_id: int, title: str) -> ChatSession:
        """建立新 Session。"""
        pass

    @abstractmethod
    async def find_by_id(self, session_id: int) -> ChatSession | None:
        """查詢 Session。"""
        pass

    @abstractmethod
    async def list_by_user(self, user_id: int, page: int = 1, page_size: int = 20) -> list[ChatSession]:
        """列出使用者的 Session。"""
        pass

    @abstractmethod
    async def update(self, session_id: int, **kwargs) -> ChatSession:
        """更新 Session（標題等）。"""
        pass

    @abstractmethod
    async def delete(self, session_id: int) -> None:
        """刪除 Session。"""
        pass
```

---

## 2. Repository 實作

位置：`src/infrastructure/repositories/`

### SQLAlchemy 實作範例

```python
# src/infrastructure/repositories/user_repository.py

from sqlalchemy import select, func
from src.core.interfaces.repository import IUserRepository
from src.infrastructure.persistence.models import User

class SQLAlchemyUserRepository(IUserRepository):
    """使用 SQLAlchemy 實作的 User Repository。"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def find_by_id(self, user_id: int) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(self, username: str, hashed_password: str, role: str = "user") -> User:
        user = User(username=username, password=hashed_password, role=role)
        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def update(self, user_id: int, **kwargs) -> User:
        user = await self.find_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        for key, value in kwargs.items():
            if hasattr(user, key):
                setattr(user, key, value)
        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def delete(self, user_id: int) -> None:
        user = await self.find_by_id(user_id)
        if user:
            await self.session.delete(user)
            await self.session.commit()

    async def list_all(self, page: int = 1, page_size: int = 20) -> list[User]:
        stmt = select(User).offset((page - 1) * page_size).limit(page_size)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def count_by_role(self, role: str) -> int:
        stmt = select(func.count(User.id)).where(User.role == role)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def update_password(self, user_id: int, hashed_password: str) -> User:
        return await self.update(user_id, password=hashed_password)

    async def update_max_sessions(self, user_id: int, max_sessions: int) -> User:
        return await self.update(user_id, max_sessions=max_sessions)
```

---

## 3. Service 層

位置：`src/application/services/`

Service 層為業務邏輯與 HTTP 層之間的媒介。它：
- 依賴於 Repository 介面（不依賴具體實作）
- 協調多個 Repository 的操作
- 處理驗證、轉換、例外
- 保持 HTTP 層簡潔

### ChatService 結構

```python
# src/application/services/chat_service.py

class ChatService:
    """聊天服務 — 協調 RAG 管道、安全檢查、Session 管理。"""

    def __init__(
        self,
        chat_session_repo: IChatSessionRepository,
        message_repo: IChatMessageRepository,
        rag_pipeline: RAGPipeline,
        security_guardrail: ISecurityGuardrail,
    ):
        self._chat_session_repo = chat_session_repo
        self._message_repo = message_repo
        self._rag_pipeline = rag_pipeline
        self._security_guardrail = security_guardrail

    async def stream_answer(
        self,
        question: str,
        session_id: str,
        user_id: int,
    ) -> AsyncIterator[str]:
        """串流問答。

        Steps:
        1. 驗證 Session 所有權
        2. 安全檢查輸入
        3. 執行 RAG 查詢
        4. 輸出消毒
        5. 儲存訊息歷史
        """
        # 驗證 Session
        session = await self._chat_session_repo.find_by_id(session_id)
        if not session or session.user_id != user_id:
            raise HTTPException(status_code=403, detail="Session not found or unauthorized")

        # 安全檢查
        clean_question = self._security_guardrail.check_input(question)

        # 串流生成
        full_response = ""
        async for token in self._rag_pipeline.query(clean_question, session_id=session_id):
            safe_token = self._security_guardrail.sanitize_output(token)
            full_response += safe_token
            yield safe_token

        # 儲存訊息
        await self._message_repo.create(
            session_id=session_id,
            role="user",
            content=question,
        )
        await self._message_repo.create(
            session_id=session_id,
            role="assistant",
            content=full_response,
        )
```

### DocumentService 結構

```python
class DocumentService:
    """文件服務 — 協調文件匯入、去重、Milvus 索引。"""

    def __init__(
        self,
        document_repo: IDocumentRepository,
        ingestion_pipeline: IngestionPipeline,
    ):
        self._document_repo = document_repo
        self._ingestion_pipeline = ingestion_pipeline

    async def ingest_document(self, file_path: str) -> Document:
        """匯入文件。

        Steps:
        1. 解析文件
        2. 計算 doc_hash 檢查重複
        3. 分段、向量化、存入 Milvus
        4. 儲存 Document 記錄
        """
        # 解析、分段、向量化
        chunks = await self._ingestion_pipeline.run(file_path)

        # 檢查重複
        doc_hash = await self._ingestion_pipeline.compute_hash(file_path)
        existing = await self._document_repo.find_by_hash(doc_hash)
        if existing:
            raise ValueError(f"Document already imported: {existing.id}")

        # 儲存 Document 記錄
        document = await self._document_repo.create(
            file_path=file_path,
            doc_hash=doc_hash,
            chunk_count=len(chunks),
        )
        return document
```

---

## 4. HTTP 層（Router）— 精簡化

得益於 Service 層，Router 變得非常簡潔：

```python
# src/api/routers/chat.py

@router.post("/query")
async def chat_query(
    request: ChatRequestDTO,
    current_user=Depends(get_current_user),
    chat_service: ChatServiceDep = None,
):
    """串流問答。"""
    session_id = request.session_id or str(uuid.uuid4())

    async def event_stream():
        try:
            async for token in chat_service.stream_answer(
                request.question,
                session_id,
                user_id=current_user.id
            ):
                yield f"data: {token}\n\n"
            yield "data: [DONE]\n\n"
        except SecurityError as e:
            yield f"data: [ERROR] {e}\n\n"
        except Exception as exc:
            logger.exception(f"[Chat] Stream error: {exc}")
            yield "data: [ERROR] 系統發生錯誤，請稍後再試\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

**優點：**
- Router 只負責 HTTP 協議（驗證、反序列化、序列化、響應格式）
- 業務邏輯完全在 Service 層
- 容易測試（mock Service）
- 容易重用（同一 Service 可供多個 Router 使用）

---

## 5. 依賴注入（DI）

位置：`src/api/dependencies.py`

使用 FastAPI 的 `Depends()` 機制進行依賴注入：

```python
# src/api/dependencies.py

@lru_cache
def get_settings() -> Settings:
    return Settings()

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """提供 AsyncSession。"""
    async with AsyncSessionLocal() as session:
        yield session

async def get_user_repository(db: AsyncSession = Depends(get_db)) -> IUserRepository:
    """提供 UserRepository 實作。"""
    return SQLAlchemyUserRepository(db)

async def get_document_repository(db: AsyncSession = Depends(get_db)) -> IDocumentRepository:
    """提供 DocumentRepository 實作。"""
    return SQLAlchemyDocumentRepository(db)

async def get_chat_service(
    chat_session_repo: IChatSessionRepository = Depends(get_chat_session_repository),
    message_repo: IChatMessageRepository = Depends(get_message_repository),
    rag_pipeline: RAGPipeline = Depends(get_rag_pipeline),
    security_guardrail: ISecurityGuardrail = Depends(get_security_guardrail),
) -> ChatService:
    """提供 ChatService，自動注入所有依賴。"""
    return ChatService(
        chat_session_repo=chat_session_repo,
        message_repo=message_repo,
        rag_pipeline=rag_pipeline,
        security_guardrail=security_guardrail,
    )
```

---

## 6. ORM 模型（SQLAlchemy）

位置：`src/infrastructure/persistence/models.py`

```python
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import declarative_base
from datetime import datetime, timezone

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password = Column(String, nullable=False)  # hashed
    role = Column(String, default="user", nullable=False)
    max_sessions = Column(Integer, default=5)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class Document(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True)
    file_path = Column(String, nullable=False)
    doc_hash = Column(String, unique=True, index=True, nullable=False)
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String, default="新對話")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"), nullable=False, index=True)
    role = Column(String, nullable=False)  # "user" or "assistant"
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
```

---

## 7. 資料庫遷移（Alembic）

位置：`src/infrastructure/persistence/migrations/`

使用 Alembic 進行資料庫版本控制：

```bash
# 檢查待執行的遷移
alembic upgrade head

# 建立新遷移（自動檢測模型變更）
alembic revision --autogenerate -m "Add chat_sessions table"

# 檢視遷移歷史
alembic history
```

---

## 8. SOLID 原則應用總結

| 原則 | 實作方式 |
|------|--------|
| **S** - Single Responsibility | Repository 只負責資料存取；Service 只負責業務邏輯；Router 只負責 HTTP 協議 |
| **O** - Open/Closed | 定義 `IUserRepository` 介面，擴展新 Repository 實作無需修改既有代碼 |
| **L** - Liskov Substitution | `SQLAlchemyUserRepository` 可完全替代 `IUserRepository` |
| **I** - Interface Segregation | 定義細粒度介面（`IRetriever`、`IHybridSearchEngine`、`ISecurityGuardrail`），避免臃腫 |
| **D** - Dependency Inversion | Service 依賴於 `IUserRepository`，不依賴 `SQLAlchemyUserRepository` |

---

## 9. 測試策略

由於 Repository Pattern 與 DI，測試變得簡單：

```python
# 單元測試 — mock Repository

class MockUserRepository(IUserRepository):
    async def find_by_id(self, user_id: int) -> User | None:
        return User(id=user_id, username="test_user")

    # ... 其他方法實作

async def test_chat_service():
    """測試 ChatService，mock 所有依賴。"""
    mock_session_repo = MockChatSessionRepository()
    mock_rag_pipeline = MockRAGPipeline()

    service = ChatService(
        chat_session_repo=mock_session_repo,
        rag_pipeline=mock_rag_pipeline,
        # ...
    )

    # 測試邏輯
    tokens = []
    async for token in service.stream_answer("test", "session_1", user_id=1):
        tokens.append(token)

    assert "".join(tokens) == "expected response"
```

---

## 10. 參考資源

- **Repository Pattern**: Martin Fowler - *Catalog of Patterns of Enterprise Application Architecture*
- **Clean Architecture**: Uncle Bob - *Clean Code* & *Clean Architecture*
- **SOLID Principles**: Robert C. Martin (Uncle Bob)
- **FastAPI DI**: https://fastapi.tiangolo.com/tutorial/dependencies/
- **SQLAlchemy 非同步**: https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html
