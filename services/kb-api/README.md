# Career KB API

Python FastAPI 後端，提供 RAG 問答、YouTube 知識庫匯入與管理員功能。

---

## 架構

```
src/
├── api/              # FastAPI routers (auth, chat, sessions, documents, ingestion, admin)
├── application/      # Use-case services (ChatService, AuthService, SessionService...)
│   └── dto/          # Pydantic request/response DTOs
├── core/             # Domain layer (interfaces, domain models, exceptions, config)
├── rag/              # RAG pipeline (HybridSearchEngine, MilvusRetriever)
├── ingestion/        # Ingestion pipeline (CareerChunker, CareerClassifier, EmbeddingService)
├── infrastructure/   # Concrete implementations (repositories, LLM providers)
└── security/         # Input validation, injection detection, PII anonymization
```

**搜索流程：**  
Query → Embed → Milvus top-50（Dense）+ BM25 → RRF fusion → top-5 → Ollama LLM → SSE stream

---

## 本地開發

```bash
cd services/kb-api

python3.11 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

確認 Docker 服務已啟動（Milvus + PostgreSQL）：

```bash
cd ../../docker && docker compose up -d postgres milvus-standalone etcd minio
```

啟動開發伺服器：

```bash
uvicorn src.api.main:app --reload --port 8000
```

---

## 環境變數

從 repo root 的 `.env` 載入（`services/kb-api/src/core/config.py`）：

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `LLM_PROVIDER` | `ollama` | `ollama` / `grok` / `openai` |
| `LLM_MODEL` | `gemma3:12b` | 模型名稱 |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama 服務位址 |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Embedding 模型（768 dim）|
| `DATABASE_URL` | — | PostgreSQL asyncpg URL |
| `MILVUS_HOST` | `localhost` | Milvus 主機 |
| `MILVUS_COLLECTION` | `career_kb` | Milvus collection 名稱 |
| `SECRET_KEY` | — | JWT 簽名金鑰（32+ chars）|
| `ADMIN_PASSWORD` | — | 首次啟動自動建立管理員帳號 |

---

## YouTube 知識庫匯入

```bash
cd services/kb-api

# 增量匯入（跳過已匯入影片）
python3.11 scripts/ingest_youtube.py --incremental >> /tmp/ingest_log.txt 2>&1 &

# 監控進度
while true; do echo "$(date +%H:%M) done: $(grep 'Stored' /tmp/ingest_log.txt | wc -l)/1035"; sleep 60; done

# 等候完成通知
wait <PID> && echo "done"

# Dry run（只切塊，不寫入 Milvus）
python3.11 scripts/ingest_youtube.py --dry-run
```

字幕來源：`data/processed/transcripts/*.txt`（1,035 部影片）  
Milvus schema 欄位：`chunk_id`, `source`, `section`（topic）, `content`, `video_title`, `upload_date`, `url`, `embedding`

---

## PDF 文件匯入

```bash
# 匯入目錄下所有 PDF/DOCX
python3.11 scripts/ingest_documents.py --path data/raw/

# 匯入單一文件
python3.11 scripts/ingest_documents.py --file data/raw/report.pdf

# 重新匯入（先清除舊向量）
python3.11 scripts/ingest_documents.py --path data/raw/ --reingest
```

---

## 主要 API 端點

完整文件：`http://localhost:8000/docs`

| 方法 | 端點 | 說明 |
|------|------|------|
| POST | `/api/auth/token` | 登入取得 JWT |
| POST | `/api/chat/query` | SSE 串流問答 |
| POST | `/api/chat/query/sync` | 同步問答（VoltAgent 使用）|
| POST | `/api/ingestion/youtube` | 觸發 YouTube ingest（admin, SSE）|
| GET | `/api/sessions` | 列出對話 Sessions |
| GET | `/api/admin/users` | 列出所有使用者（admin）|
| GET | `/health` | 健康檢查 |

**Chat 請求格式：**

```json
{
  "question": "如何準備外商面試？",
  "session_id": "uuid",
  "topic": "interview"
}
```

`topic` 對應 Milvus `section` 欄位 filter，可選值：`resume` / `interview` / `career_planning` / `salary` / `workplace` / `job_search` / `promotion` / `industry_insight` / `skill_development`

---

## 測試

```bash
pytest tests/ -v
pytest tests/unit/test_chunker.py -v
pytest tests/ --cov=src --cov-report=term-missing
```

---

## DB Migration

```bash
# 查看目前版本
alembic current

# 套用所有待執行 migration
alembic upgrade head

# 新增 migration
./scripts/make_migration.sh "add new column"
```

---

## 重置知識庫

```bash
# 清空 Milvus vectors（保留 PostgreSQL）
python3.11 scripts/reset_knowledge_base.py --vectors-only --yes

# 清空全部（含對話紀錄）
python3.11 scripts/reset_knowledge_base.py --yes --include-chat-history
```
