# 道輝 — 一貫道內部知識庫系統

基於 RAG（Retrieval-Augmented Generation）架構的一貫道典籍智慧問答系統，支援 PDF/DOCX/PPTX 解析、混合向量搜索（Dense + BM25）、安全防護與 Web 介面。
預設使用本機 **Ollama + Gemma3:12b**，無需雲端 API 金鑰即可運行。也支援切換至 xAI Grok 等雲端 LLM。

![道輝知識庫介面](static/images/截圖%202026-04-15%20晚上10.11.44.png)

---

## 核心特性

- **零配置 RAG**：一鍵啟動，預設本機 Ollama，無需 API 金鑰
- **混合搜索**：結合向量搜索（語意相似）+ BM25（精確關鍵字）+ RRF 融合
- **生產級安全**：Prompt Injection 偵測、PII 匿名化、速率限制、管理員控制
- **多 LLM 支援**：Ollama / xAI Grok 無縫切換
- **對話管理**：具名 Session、訊息上限控制、持久化儲存
- **直覺化界面**：Claude 風格側邊欄、Session 列表、「新對話」按鈕
- **SOLID 設計**：清潔架構、依賴反向、易於擴展
- **文件回饋**：支援訊息讚/踩回饋與統計

---

## 前置需求

- [Ollama](https://ollama.com) 已安裝並執行
- Docker + Docker Compose
- Python 3.11+

---

## Step 1 — 安裝 Ollama 並拉取模型

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# 啟動 Ollama 服務（背景執行）
ollama serve &

# 拉取 LLM：Gemma3 12B（約 8 GB）
ollama pull gemma3:12b

# 拉取 Embedding 模型：nomic-embed-text（約 274 MB）
ollama pull nomic-embed-text

# 確認模型已就緒
ollama list
```

> **記憶體建議**：gemma3:12b 需約 10 GB RAM（或 VRAM）。
> 記憶體不足可改用較輕量的 `gemma3:4b`（約 4 GB）或 `gemma2:2b`（約 2 GB），
> 只需在 `.env` 中調整 `LLM_MODEL`。

---

## Step 2 — 設定環境變數

```bash
cp .env.example .env
```

`.env` 預設值即為 Ollama + Gemma3:12b，以下列出關鍵變數：

```dotenv
# ── LLM ────────────────────────────
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=gemma3:12b

EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text

# ── Sessions ───────────────────────
MAX_MESSAGES_PER_SESSION=100     # 每個 Session 最多訊息數（預設 100）

# ── Admin Seed ─────────────────────
ADMIN_USERNAME=admin              # 預設管理員帳號名稱
ADMIN_PASSWORD=changeme123        # 設定後，啟動時自動建立管理員帳號
```

> **重要**：設定 `ADMIN_PASSWORD` 後，首次啟動時將自動建立一個管理員帳號。請將密碼改為安全的字串。

---

## Step 3 — 啟動所有服務

```bash
cd docker
docker compose up -d
```

啟動的容器：

| 容器 | 用途 | Port |
|------|------|------|
| `app` | FastAPI 應用 | 8000 |
| `postgres` | 對話紀錄 / metadata | 5436 |
| `milvus-standalone` | 向量資料庫 | 19530 |
| `etcd` / `minio` | Milvus 依賴 | — |
| `nginx` | 反向代理 | 80 |

確認服務健康：

```bash
docker compose ps
curl http://localhost/health
```

---

## Step 3.5 — 資料庫 Migration 設定

服務啟動時會自動執行 `alembic upgrade head`，無需手動操作。若需手動管理 migration：

```bash
# 安裝依賴（若尚未安裝）
python3.11 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# 查看目前 migration 版本
alembic current

# 手動套用所有待執行的 migration
alembic upgrade head

# 新增 migration（修改 ORM model 後）
./scripts/make_migration.sh "描述這次變更"
# 範例：./scripts/make_migration.sh "add email column to users"
# 會同時產生 migrations/versions/*.py 與 migrations/sql/*.sql
```

詳細說明見 [migrations/migration.md](./migrations/migration.md)。

---

## Step 4 — 匯入典籍文件

```bash
python3.11 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"

# 先生成範例典籍（4 份 DOCX，含教義、十條大願、修行方法、道場規範）
python3.11 scripts/create_sample_data.py

# 批次匯入 data/raw/ 下所有文件
python3.11 scripts/ingest_documents.py --path data/raw/

# 或匯入單一檔案
python3.11 scripts/ingest_documents.py --file data/raw/典籍.pdf
```

### 更新已匯入的文件（Reingest）

當文件內容修改後，直接重新 `ingest` 會造成新舊向量並存、查詢結果重複。有兩種方式處理：

**方式一：透過 CLI（`--reingest` 旗標）**

```bash
# 更新單一文件（先刪除舊向量，再匯入新版本）
python3.11 scripts/ingest_documents.py --file data/raw/典籍.pdf --reingest

# 批次更新目錄（只重匯內容有變動的文件，未變動的自動略過）
python3.11 scripts/ingest_documents.py --path data/raw/ --reingest
```

> **何時用 `--reingest`？**
> 當你修改了已匯入的文件內容後，加上 `--reingest` 旗標，系統會先以檔名清除
> Milvus 中所有舊向量，再匯入更新後的版本，避免新舊重複。

**方式二：透過 API（精確更新單一文件）**

先取得文件 ID，再呼叫 reingest 端點：

```bash
# 列出已匯入文件，取得 doc_id
curl -H "Authorization: Bearer <token>" http://localhost/api/documents/list

# 以新版文件取代舊版（刪舊向量 + 重新匯入）
curl -X POST http://localhost/api/documents/<doc_id>/reingest \
  -H "Authorization: Bearer <token>"
```

> **注意**：更換 Embedding 模型（例如從 `nomic-embed-text` 換成 `mxbai-embed-large`）時，
> 因向量維度不同，**必須先清空再重新匯入**，否則 Milvus 會報維度錯誤。

範例典籍說明：

| 檔案 | 內容 |
|------|------|
| `基礎教義總覽.docx` | 天道概說、三寶要義、求道儀式、五教同源 |
| `十條大願詳解.docx` | 十條大願逐條說明與修行意義 |
| `修行方法指引.docx` | 日課功課、清口素食、五常實踐、三省吾身 |
| `道場規範手冊.docx` | 佛堂禮儀、道場活動規範、壇主職責 |

---

## Step 5 — 開啟 Web 介面

```bash
# 聊天介面
open http://localhost

# 管理員面板（建立使用者、管理文件）
open http://localhost/admin

# API 文件（Swagger UI）
open http://localhost:8000/docs
```

**登入帳號**：

- **管理員帳號**：若 `.env` 中設定 `ADMIN_PASSWORD`，首次啟動時將自動建立管理員帳號。
  - 帳號：`ADMIN_USERNAME`（預設 `admin`）
  - 密碼：`ADMIN_PASSWORD` 值
  - 訪問 `http://localhost/admin` 進入管理後台

- **普通使用者**：透過 Web 界面註冊，或透過 API：
  ```bash
  curl -X POST http://localhost/api/auth/register \
    -H "Content-Type: application/json" \
    -d '{"username": "user1", "password": "Password123"}'
  ```

---

## 切換至 xAI Grok

如需使用雲端 Grok，修改 `.env`：

```dotenv
LLM_PROVIDER=grok
LLM_MODEL=grok-beta
GROK_API_KEY=xai-...

# Embedding 仍可維持本機 Ollama
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
```

---

## 新特性：管理員管理、對話 Sessions 與側邊欄

### 1. 管理員後台

系統支援**管理員帳號**，具以下功能：

- **使用者管理**：列出、建立、刪除、重設密碼、調整 Session 上限
- **自動初始化**：設定 `ADMIN_PASSWORD` 環境變數後，首次啟動時自動建立管理員帳號

**配置**：

```dotenv
ADMIN_USERNAME=admin              # 管理員帳號名稱（預設 admin）
ADMIN_PASSWORD=changeme123        # 設定後自動建立；首次啟動必填
```

**管理員 API 端點**（需 admin 角色）：

```bash
# 列出所有使用者
curl -H "Authorization: Bearer <token>" http://localhost/api/admin/users

# 建立新使用者
curl -X POST http://localhost/api/admin/users \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"username": "user1", "password": "Pass123", "role": "user"}'

# 刪除使用者
curl -X DELETE http://localhost/api/admin/users/2 \
  -H "Authorization: Bearer <token>"

# 重設使用者密碼
curl -X PATCH http://localhost/api/admin/users/2/password \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"new_password": "NewPass456"}'

# 調整使用者最大 Session 數
curl -X PATCH http://localhost/api/admin/users/2/max-sessions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"max_sessions": 20}'
```

### 2. 對話 Sessions（具名對話）

使用者的所有對話現已組織成具名的 **Session**，具以下特性：

- **Session 隔離**：每個 Session 獨立儲存訊息歷史
- **命名與管理**：支援建立、重新命名、刪除 Session
- **訊息上限**：每個 Session 最多儲存 `MAX_MESSAGES_PER_SESSION` 條訊息（預設 100）
- **持久化**：所有 Session 與訊息存儲在 PostgreSQL

**Session API 端點**（需登入）：

```bash
# 列出使用者的所有 Session
curl -H "Authorization: Bearer <token>" http://localhost/api/sessions

# 建立新 Session
curl -X POST http://localhost/api/sessions \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "修行問答"}'

# 取得 Session 詳細資訊（含訊息）
curl -H "Authorization: Bearer <token>" http://localhost/api/sessions/abc-def-123

# 重新命名 Session
curl -X PATCH http://localhost/api/sessions/abc-def-123 \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"title": "三寶相關問題"}'

# 刪除 Session
curl -X DELETE http://localhost/api/sessions/abc-def-123 \
  -H "Authorization: Bearer <token>"
```

### 3. 訊息回饋

支援對每則回答進行讚/踩回饋：

```bash
# 提交回饋（thumbs_up / thumbs_down）
curl -X POST http://localhost/api/feedback \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message_id": "msg-123", "feedback_type": "thumbs_up"}'

# 查看 Session 的回饋統計
curl -H "Authorization: Bearer <token>" \
  http://localhost/api/feedback/stats/abc-def-123
```

---

## 系統架構

本系統遵循 **Clean Architecture + SOLID 原則**，分為五層：

```
┌─────────────────────────────────────────────┐
│ Phase 5: API Layer (FastAPI + JWT + SSE)    │  HTTP 協議
├─────────────────────────────────────────────┤
│ Phase 4: Application (ChatService + DTO)    │  業務邏輯協調
├─────────────────────────────────────────────┤
│ Phase 0: Core (Interfaces + Domain Models)  │  抽象層 (DIP 原則)
├─────────────────────────────────────────────┤
│ Phase 2: Infrastructure (Repositories)      │  資料庫 / LLM 實作
├─────────────────────────────────────────────┤
│ Phase 1: Ingestion (Parser → Chunker → DB)  │  文件匯入
└─────────────────────────────────────────────┘
```

```
Phase 1 — Data Ingestion
  PDF/DOCX → DocumentParser → SmartChunker → EmbeddingService (Ollama) → Milvus

Phase 2 — RAG Pipeline
  Query → HybridSearch (Vector + BM25 + RRF) → Gemma3:12b (Ollama) → Response

Phase 3 — Fine-tuning Strategy
  Glossary Injection + QADatasetGenerator → LoRA Fine-tuning（預留接口）

Phase 4 — Security
  SecurityGuardrail → InjectionDetector + ContentFilter → PII Anonymizer

Phase 5 — Deployment
  FastAPI + PostgreSQL + Milvus + Nginx → Docker Compose
```

詳細架構說明見 **[docs/architecture.md](./docs/architecture.md)**

---

## Tech Stack

| 層級 | 技術 | 說明 |
|------|------|------|
| **Web Framework** | FastAPI + Python 3.11 | 非同步 Web 框架 |
| **RAG** | LangChain + LlamaIndex | RAG 框架 |
| **LLM** | Ollama Gemma3:12b（本機）/ xAI Grok（可選）| 主要推理模型 |
| **Embedding** | Ollama nomic-embed-text | 768 維向量模型 |
| **Vector DB** | Milvus 2.4 | 向量資料庫 |
| **Relational DB** | PostgreSQL 16（port 5436）| 對話紀錄 / 文件 metadata |
| **Search** | rank-bm25 | BM25 關鍵字搜索 |
| **Frontend** | HTML + Tailwind CSS | 單頁 Web 介面 |
| **Container** | Docker Compose | 全棧容器化部署 |

---

## API 文件與主要端點

啟動後訪問 Swagger UI：`http://localhost:8000/docs`

### 認證

| 方法 | 端點 | 說明 |
|------|------|------|
| POST | `/api/auth/register` | 新使用者註冊 |
| POST | `/api/auth/token` | 帳密登入（返回 JWT） |

### 對話

| 方法 | 端點 | 說明 |
|------|------|------|
| POST | `/api/chat/query` | **SSE 串流問答**（推薦） |
| POST | `/api/chat/query/sync` | 同步問答 |

### Sessions（需登入）

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/api/sessions` | 列出目前使用者的所有 Session |
| POST | `/api/sessions` | 建立新 Session |
| GET | `/api/sessions/{session_id}` | 取得 Session 詳細資訊（含訊息） |
| PATCH | `/api/sessions/{session_id}` | 重新命名 Session |
| DELETE | `/api/sessions/{session_id}` | 刪除 Session |

### 文件管理（需登入）

| 方法 | 端點 | 說明 |
|------|------|------|
| POST | `/api/documents/upload` | 上傳並匯入文件 |
| GET | `/api/documents/list` | 列出已匯入文件 |
| DELETE | `/api/documents/{doc_id}` | 刪除文件及其向量 |
| POST | `/api/documents/{doc_id}/reingest` | 以新版文件取代舊版（刪舊向量 + 重新匯入） |

### 回饋（需登入）

| 方法 | 端點 | 說明 |
|------|------|------|
| POST | `/api/feedback` | 提交訊息回饋（讚/踩） |
| GET | `/api/feedback/stats/{session_id}` | 取得 Session 回饋統計 |

### 管理員（需 admin 角色）

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/api/admin/users` | 列出所有使用者 |
| POST | `/api/admin/users` | 建立新使用者 |
| DELETE | `/api/admin/users/{user_id}` | 刪除使用者 |
| PATCH | `/api/admin/users/{user_id}/password` | 更新使用者密碼 |
| PATCH | `/api/admin/users/{user_id}/max-sessions` | 調整使用者 Session 上限 |

### 系統

| 方法 | 端點 | 說明 |
|------|------|------|
| GET | `/health` | 健康檢查 |

---

## 清空已匯入的典籍

```bash
# 互動確認模式（會提示確認）
python3.11 scripts/reset_knowledge_base.py

# 靜默模式（直接執行，適合 CI）
python3.11 scripts/reset_knowledge_base.py --yes

# 只清向量資料庫（Milvus），保留 PostgreSQL 文件紀錄
python3.11 scripts/reset_knowledge_base.py --vectors-only

# 同時清空對話紀錄
python3.11 scripts/reset_knowledge_base.py --yes --include-chat-history
```

清空後重新匯入：

```bash
python3.11 scripts/ingest_documents.py --path data/raw/
```

---

## 生成 QA 資料集

```bash
python3.11 scripts/generate_qa_dataset.py \
  --file data/raw/典籍.pdf \
  --output data/processed/qa_dataset.json \
  --pairs-per-chunk 5
```

---

## 開發與貢獻

### 專案結構

```
yiguandao-kb/
├── src/                      # 主要程式碼（遵循 Clean Architecture）
│   ├── api/                  # FastAPI 路由與中間件
│   ├── application/          # 業務邏輯服務層
│   ├── core/                 # 抽象介面與領域模型
│   ├── infrastructure/       # 資料庫、LLM、儲存庫實作
│   ├── ingestion/            # 文件解析與匯入管道
│   ├── rag/                  # RAG 搜索與檢索
│   └── security/             # 安全防護模組
├── tests/                    # 單元測試與整合測試
├── scripts/                  # 批次工作與工具腳本
│   └── make_migration.sh     # 新增 migration 並自動產生 SQL
├── migrations/               # Alembic DB migration
│   ├── versions/             # Python migration 檔案
│   ├── sql/                  # 每版對應的純 SQL 檔案
│   └── migration.md          # Migration 操作指南
├── docker/                   # Docker 容器定義
├── frontend/                 # Web 介面（HTML + Tailwind）
└── docs/                     # 文件（架構、RAG 說明）
```

### 測試

```bash
# 運行所有測試
pytest tests/ -v

# 運行特定測試
pytest tests/unit/test_chunker.py -v

# 覆蓋率報告
pytest tests/ --cov=src --cov-report=html
```

### 設定開發環境

```bash
# 建立虛擬環境
python3.11 -m venv venv
source venv/bin/activate

# 安裝開發依賴
pip install -e ".[dev]"
```

### 設計原則

本專案遵循 **SOLID 原則** 與 **Clean Architecture**：

- **S** — Single Responsibility：每個類別只有一個變更理由
- **O** — Open/Closed：對擴展開放（新 LLM），對修改關閉
- **L** — Liskov Substitution：所有實現可互相替換
- **I** — Interface Segregation：細粒度介面，避免不必要依賴
- **D** — Dependency Inversion：高層依賴抽象而非實作

詳見 [docs/architecture-solid.md](./docs/architecture-solid.md)

---

## 常見問題

### Q: 沒有 GPU，能否運行？

**A:** 能。Ollama 在 CPU 上也能運行，但速度會慢。推薦配置：

- CPU 模式：8+ GB RAM（Gemma3:12b）
- GPU 模式：6+ GB VRAM（推薦）

若記憶體不足，改用 Gemma3:4b 或 Gemma2:2b：

```bash
ollama pull gemma3:4b
# .env 中修改 LLM_MODEL=gemma3:4b
```

### Q: 修改了已匯入的典籍，如何更新？

**A:** 有兩種方法：

1. **透過 API（精確更新單一文件）**：先取得文件 ID，呼叫 `POST /api/documents/{doc_id}/reingest`
2. **透過 CLI（整批重新匯入）**：執行 `reset_knowledge_base.py --vectors-only --yes` 清空後再批次匯入

### Q: 更換 Embedding 模型後無法查詢？

**A:** 不同模型的向量維度不同，必須先清空再重新匯入：

```bash
python3.11 scripts/reset_knowledge_base.py --vectors-only --yes
python3.11 scripts/ingest_documents.py --path data/raw/
```

### Q: 如何在生產環境部署？

**A:** 生產建議：

1. 使用 `APP_ENV=production`（關閉 Swagger UI）
2. 設定強密碼的 `SECRET_KEY`：
   ```bash
   python3 -c "import secrets; print(secrets.token_hex(32))"
   ```
3. 配置 HTTPS / SSL（透過 Nginx）
4. 設定資料庫備份（PostgreSQL 定時備份）
5. 修改 `ADMIN_PASSWORD` 為安全密碼

### Q: 支援多語言嗎？

**A:** System Prompt 目前為繁體中文。要支援其他語言：

1. 修改 `src/application/services/chat_service.py` 的 System Prompt
2. 更換 Embedding 模型（如 `multilingual-e5-large`）
