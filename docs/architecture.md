# 道輝 — 系統架構總覽

> 一貫道內部知識庫系統（yiguandao-kb）
> 基於 RAG 架構，支援本機 Ollama 或雲端 xAI Grok

---

## Tech Stack

| 層級 | 技術 | 說明 |
|------|------|------|
| API | FastAPI + Python 3.11 | 非同步 Web 框架 |
| RAG | LangChain + pymilvus | 檢索增強生成框架 |
| LLM | Ollama Gemma3:12b / xAI Grok | 語言模型，可切換 |
| Embedding | Ollama nomic-embed-text（768 維）| 向量化模型 |
| Vector DB | Milvus 2.4 | 向量儲存與 ANN 搜索 |
| Relational DB | PostgreSQL 16 | 對話紀錄 / 文件 metadata |
| Frontend | HTML + Tailwind CSS | 單頁 Web 介面 |
| Container | Docker Compose | 全棧容器化部署 |

---

## 目錄結構

```
yiguandao-kb/
├── src/
│   ├── api/                             # Phase 5：FastAPI 應用層
│   │   ├── main.py                      # 入口：CORS、Rate Limiting、路由掛載、Prometheus
│   │   ├── auth.py                      # JWT 工具函式（token 生成/驗證）
│   │   ├── dependencies.py              # 依賴注入（Service 工廠）
│   │   └── routers/
│   │       ├── auth.py                  # POST /api/auth/register, /login, /refresh
│   │       ├── chat.py                  # POST /api/chat/query（SSE 串流）、/query/sync
│   │       ├── documents.py             # POST /api/documents/ingest, GET /list, DELETE /{id}
│   │       ├── admin.py                 # POST /api/admin/users（管理員管理使用者）
│   │       └── sessions.py              # GET/POST /api/sessions（對話 Session 管理）
│   ├── application/                     # Service + DTO 層（業務邏輯）
│   │   ├── services/
│   │   │   ├── chat_service.py          # 問答服務（安全檢查、RAG、記憶管理）
│   │   │   ├── document_service.py      # 文件匯入服務
│   │   │   ├── session_service.py       # Session 管理
│   │   │   └── user_service.py          # 使用者管理
│   │   └── dto/                         # Data Transfer Objects
│   │       ├── chat_dto.py              # ChatRequest、ChatResponse、SourceDocument
│   │       ├── session_dto.py           # SessionDTO、CreateSessionDTO
│   │       └── user_dto.py              # UserDTO、CreateUserDTO
│   ├── infrastructure/                  # 資料庫 & 外部連接
│   │   ├── persistence/
│   │   │   ├── database.py              # SQLAlchemy 非同步設定
│   │   │   ├── models.py                # ORM 模型（User、Document、ChatMessage）
│   │   │   └── migrations/              # Alembic 資料庫遷移
│   │   └── repositories/                # Repository Pattern（資料存取抽象）
│   │       ├── user_repository.py       # IUserRepository 實作
│   │       ├── document_repository.py   # IDocumentRepository 實作
│   │       ├── chat_session_repository.py # IChatSessionRepository 實作
│   │       └── message_repository.py    # IChatMessageRepository 實作
│   ├── core/                            # 核心領域 & 工廠
│   │   ├── config.py                    # 設定管理（環境變數解析）
│   │   ├── llm_factory.py               # LLM / Embedding 工廠（Ollama / Grok / OpenAI）
│   │   ├── exceptions.py                # 自訂例外（SecurityError、ValidationError）
│   │   ├── interfaces/                  # 介面 / 抽象（SOLID 原則）
│   │   │   ├── repository.py            # IUserRepository、IDocumentRepository 等
│   │   │   ├── retriever.py             # IRetriever（向量搜索）
│   │   │   ├── search.py                # IHybridSearchEngine
│   │   │   ├── llm.py                   # ILLM（Language Model 介面）
│   │   │   ├── query_enhancer.py        # IQueryEnhancer
│   │   │   └── security.py              # ISecurityGuardrail
│   │   └── domain/                      # 領域模型
│   │       ├── parsed_document.py       # ParsedDocument
│   │       ├── chunk.py                 # Chunk
│   │       └── search_result.py         # SearchResult
│   ├── ingestion/                       # Phase 1：文件匯入
│   │   ├── pdf_parser.py                # PDF / DOCX 解析 → ParsedDocument
│   │   ├── chunker.py                   # 智慧分段 512 token，64 overlap
│   │   ├── embedder.py                  # Embedding + 寫入 Milvus
│   │   └── pipeline.py                  # 整合入口：parse → chunk → embed → store
│   ├── rag/                             # Phase 2：RAG 核心
│   │   ├── retriever.py                 # Milvus 向量搜索（Inner Product）
│   │   ├── hybrid_search.py             # 混合搜索（Dense Vector + BM25 + RRF）
│   │   └── pipeline.py                  # RAG 主流程（查詢強化 → 搜索 → 生成 → 記憶）
│   ├── finetuning/                      # Phase 3：Fine-tuning 輔助
│   │   ├── glossary.py                  # 一貫道領域詞彙表 + ALIAS_MAP
│   │   ├── prompt_optimizer.py          # 查詢詞正規化 + 術語定義注入
│   │   └── qa_generator.py              # 自動生成問答對（供 LoRA 微調使用）
│   └── security/                        # Phase 4：安全防護
│       ├── injection_detector.py        # Prompt Injection 偵測
│       ├── content_filter.py            # 違禁內容過濾
│       └── guardrail.py                 # 統一安全閘道（check_input + sanitize_output）
├── scripts/
│   ├── ingest_documents.py              # 批次匯入文件
│   ├── create_sample_data.py            # 生成範例典籍（4 份 DOCX）
│   ├── generate_qa_dataset.py           # 生成 QA 微調資料集
│   └── reset_knowledge_base.py          # 清空知識庫（可選擇只清向量或同時清對話）
├── tests/
│   ├── unit/                            # 單元測試：chunker、content_filter、injection_detector
│   └── integration/                     # 整合測試：API endpoints
├── docker/
│   ├── Dockerfile                       # Python 3.11 多階段構建
│   ├── docker-compose.yml               # 全棧：app + postgres + milvus + etcd + minio
│   └── nginx.conf                       # 反向代理：/ → 前端，/api → FastAPI
├── frontend/
│   ├── index.html                       # 聊天介面（Tailwind CSS）
│   ├── admin.html                       # 管理員面板（使用者管理、文件管理）
│   └── static/                          # 靜態資源（CSS、JS）
└── data/
    ├── raw/                             # 原始典籍（PDF / DOCX）
    └── processed/                       # QA 資料集等處理後產物
```

---

## 五個 Phase 概覽

| Phase | 模組 | 核心職責 |
|-------|------|---------|
| Phase 1 | `src/ingestion/` | PDF/DOCX → 分段 → 向量化 → Milvus |
| Phase 2 | `src/rag/` | 混合搜索 + LLM 生成（核心功能）|
| Phase 3 | `src/finetuning/` | 術語表 + 查詢強化 + QA 資料集生成 |
| Phase 4 | `src/security/` | Prompt Injection 防護 + 內容過濾 |
| Phase 5 | `src/api/` | FastAPI + JWT 認證 + SSE 串流輸出 |

**RAG 流程詳解請見 [rag-deep-dive.md](./rag-deep-dive.md)**

---

## 部署架構

```
Internet
    │
    ▼
[Nginx :80]
  /api/*  → [FastAPI :8000]
  /       → [前端靜態檔案]
               │
       ┌───────┴───────┐
       ▼               ▼
[PostgreSQL :5436]  [Milvus :19530]
  對話紀錄              向量資料庫
  文件 metadata           │
  使用者帳號         ┌────┴────┐
                    ▼         ▼
                 [etcd]    [MinIO]
               Milvus 元數據  Milvus 資料持久化
```

### API 路由概覽

#### 認證 & 使用者管理
| 端點 | 方法 | 用途 |
|------|------|------|
| `/api/auth/register` | POST | 建立新帳號 |
| `/api/auth/login` | POST | 登入取得 JWT Token |
| `/api/auth/refresh` | POST | 刷新 Token 有效期 |

#### 聊天 & RAG
| 端點 | 方法 | 用途 |
|------|------|------|
| `/api/chat/query` | POST | 串流問答（Server-Sent Events） |
| `/api/chat/query/sync` | POST | 同步問答（等待完整回答後一次返回） |

#### 文件管理
| 端點 | 方法 | 用途 |
|------|------|------|
| `/api/documents/ingest` | POST | 上傳文件進行匯入 |
| `/api/documents/list` | GET | 列出已匯入的文件 |
| `/api/documents/{doc_id}` | DELETE | 刪除文件 |

#### Session（對話紀錄）
| 端點 | 方法 | 用途 |
|------|------|------|
| `/api/sessions` | GET | 列出使用者的所有 Session |
| `/api/sessions` | POST | 建立新 Session |
| `/api/sessions/{session_id}` | PATCH | 重新命名 Session |
| `/api/sessions/{session_id}` | DELETE | 刪除 Session |

#### 管理員功能
| 端點 | 方法 | 用途 |
|------|------|------|
| `/api/admin/users` | GET | 列出所有使用者 |
| `/api/admin/users` | POST | 建立新使用者 |
| `/api/admin/users/{user_id}` | PATCH | 編輯使用者（密碼、角色、Session 限制） |
| `/api/admin/users/{user_id}` | DELETE | 刪除使用者 |

#### 系統監控
| 端點 | 方法 | 用途 |
|------|------|------|
| `/health` | GET | 健康檢查 |
| `/metrics` | GET | Prometheus 指標 |
| `/docs` | GET | Swagger API 文件（開發環境）|

---

## 環境變數

### LLM & Embedding 設定

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `LLM_PROVIDER` | `ollama` | `ollama` / `grok` / `openai` |
| `LLM_MODEL` | `gemma3:12b` | LLM 模型名稱 |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama 服務位址 |
| `GROK_API_KEY` | — | xAI API 金鑰（grok 模式必填）|
| `OPENAI_API_KEY` | — | OpenAI API 金鑰（openai 模式必填）|
| `EMBEDDING_PROVIDER` | `ollama` | `ollama` / `openai` |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Embedding 模型（決定向量維度）|
| `EMBEDDING_DIM` | 自動推斷 | 覆寫向量維度（換模型時使用）|

### 向量 & 關聯資料庫

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `MILVUS_HOST` | `localhost` | Milvus 向量資料庫主機 |
| `MILVUS_PORT` | `19530` | Milvus 埠號 |
| `MILVUS_COLLECTION` | `yiguandao_kb` | Milvus Collection 名稱 |
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL 連線字串 |

### 應用程式設定

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `MAX_MESSAGES_PER_SESSION` | 100 | 每個 Session 儲存的最大訊息數 |
| `ADMIN_USERNAME` | `admin` | 初始管理員帳號（啟動時自動建立） |
| `ADMIN_PASSWORD` | `changeme123` | 初始管理員密碼 |
| `SECRET_KEY` | — | JWT 簽名金鑰（**必填，請設定強密碼**）|
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 480 | JWT Token 有效期（分鐘） |
| `APP_ENV` | `development` | `production` 會關閉 /docs 端點 |
| `LOG_LEVEL` | `INFO` | 日誌等級（DEBUG / INFO / WARNING / ERROR） |
| `CORS_ORIGINS` | `http://localhost:3000,http://localhost:8080` | 允許的前端來源（逗號分隔） |

### 快速設定指令

生成 SECRET_KEY：
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## 更換 Embedding 模型注意事項

不同模型的向量維度不同，更換後**必須清空 Milvus 再重新匯入**：

```bash
# 1. 清空向量資料庫
python3.11 scripts/reset_knowledge_base.py --vectors-only --yes

# 2. 修改 .env
EMBEDDING_MODEL=mxbai-embed-large   # 1024 維
# EMBEDDING_DIM=1024                # 若自動推斷失敗才需要

# 3. 重新匯入
python3.11 scripts/ingest_documents.py --path data/raw/
```

已知模型維度對照：

| 模型 | 維度 |
|------|------|
| `nomic-embed-text` | 768 |
| `mxbai-embed-large` | 1024 |
| `bge-m3` | 1024 |
| `bge-large-zh` | 1024 |
| `text-embedding-3-large` | 3072 |
