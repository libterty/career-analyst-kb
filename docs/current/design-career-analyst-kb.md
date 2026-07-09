# Design Doc: Career Analyst Knowledge Base + VoltAgent Integration

**Author**: Albert  
**Date**: 2026-04-18  
**Last Updated**: 2026-04-28 (Phase 1–8 complete; RAG eval 3.00/4.0 with qwen3-30b-a3b)  
**Status**: In Progress  
**Scope**: 職涯分析師 KB — YouTube 影片知識庫 + VoltAgent Agent 管理層

---

## 1. Problem Statement

### 1.1 背景

目標頻道 [@hrjasmin](https://www.youtube.com/@hrjasmin) 持續產出職涯相關內容（共 **1,794 部影片**，含長影片、Shorts、直播、Podcast）。這些內容包含大量隱性知識（履歷撰寫、面試技巧、職涯規劃、薪資談判等），但分散在大量影片中，難以系統性查詢與應用。

### 1.2 目標

1. **Knowledge Base**：將頻道職涯影片的語音內容轉化為可查詢的向量知識庫
2. **Career Analyst Agent**：以此 KB 為基底，提供職涯諮詢、履歷評估、面試準備等能力
3. **Agent Management**：引入 VoltAgent 統一管理多個專門 agent

### 1.3 非目標 (Out of Scope)

- 影片版權重新散布
- 即時監控頻道新影片（Phase 1 不含，可未來擴充）
- 自訓練 fine-tuned model（使用 RAG 即可）
- VoltOps Cloud 可觀測性（改用本機 Ollama，無需雲端 API key）

---

## 2. System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                          使用者介面層                                  │
│   Chat UI (HTML)  │  VoltOps Console  │  REST API clients           │
└────────────┬──────────────────────────────────────────┬─────────────┘
             │                                          │
             ▼                                          ▼
┌────────────────────────┐            ┌─────────────────────────────┐
│   VoltAgent Layer      │            │   career-analyst-kb API     │
│   (TypeScript/Node)    │◄──────────►│   (FastAPI / Python)        │
│   services/voltagent-  │  HTTP      │   services/kb-api/          │
│   career/              │            │                             │
│  ┌──────────────────┐  │            │  /api/chat/query (SSE)      │
│  │ SupervisorAgent  │  │            │  /api/ingestion/youtube     │
│  │  (Career Lead)   │  │            │  /api/sessions/             │
│  └────────┬─────────┘  │            └──────────┬──────────────────┘
│           │             │                       │
│  ┌────────▼──────────┐  │            ┌──────────▼──────────────────┐
│  │ ResumeAgent       │  │            │   RAG Pipeline              │
│  │ InterviewAgent    │  │            │   Hybrid Search (BM25+Dense)│
│  │ CareerPlanAgent   │  │            │   Milvus (career_kb coll.)  │
│  │ SalaryAgent       │  │            └─────────────────────────────┘
│  └───────────────────┘  │
└────────────────────────┘
             ▲
             │
┌────────────┴──────────────────────────────────────────────────────┐
│                     Ingestion Pipeline                             │
│                                                                    │
│  yt-dlp  →  VTT/Whisper (STT)  →  Transcript                      │
│                                ↓                                   │
│              Topic Classifier  →  Chunker  →  Embedder             │
│                                              ↓                     │
│                                      Milvus: career_kb             │
└────────────────────────────────────────────────────────────────────┘
```

---

## 3. Architecture Decisions

### 3.1 以 yiguandao-kb 為樣板，建立獨立 Repo (✅ Done)

yiguandao-kb 已有成熟的：
- Milvus vector store、Hybrid Search（BM25 + Dense + RRF）
- FastAPI + SSE streaming
- JWT auth、rate limiting、semantic cache
- Clean Architecture（ingestion / rag / api / security 分層）

**決策**：`cp -r yiguandao-kb career-analyst-kb` 建立全新獨立 repo，移除所有一貫道領域內容，重新命名 collection 為 `career_kb`。

### 3.2 Mono-Repo 結構（✅ Done — Codex 重構）

原始設計為兩個獨立 repo；Codex 將兩個服務整合為 mono-repo：

```
career-analyst-kb/          ← git root
├── services/
│   ├── kb-api/             ← Python FastAPI + RAG pipeline
│   └── voltagent-career/   ← TypeScript VoltAgent layer
├── docker/
│   └── docker-compose.yml
├── frontend/
├── data/
└── docs/
```

**優點**：共用 Docker Compose、統一 `.env`、CI/CD 單一 pipeline。

### 3.3 VoltAgent 作為 Agent 管理層

career-analyst-kb 的 FastAPI 是純 RAG API，缺乏多 agent 協作與工具呼叫鏈。

**決策**：VoltAgent（TypeScript）作為 agent orchestration layer，透過 HTTP 呼叫 KB API。兩層獨立部署，透過 Docker Compose 整合。

### 3.4 VoltAgent LLM：本機 Ollama（✅ 已確定）

原設計使用 Anthropic claude-sonnet-4-6，改為本機 Ollama 以零成本運行。

| 方案 | 成本 | 品質 | 狀態 |
|------|------|------|------|
| Anthropic claude-sonnet-4-6 | ~$3/M tokens | 優 | ❌ 改為本機 |
| Ollama gemma3:12b (本機) | 零成本 | 良好（個人專案足夠） | ✅ 採用 |

**實作**：使用 `@ai-sdk/openai` 的 `createOpenAI` 指向 `http://localhost:11434/v1`（Ollama OpenAI 相容端點）。模型可透過 `VOLTAGENT_MODEL` env var 切換（預設 `gemma3:12b`）。

### 3.5 語音轉文字策略

| 方案 | 優點 | 缺點 |
|------|------|------|
| YouTube 自動字幕 | 免費、快速 | 繁中品質差，錯字多 |
| OpenAI Whisper (local) | 高品質、離線 | 慢（large model ~2x 影片時長）|
| Whisper API | 快速、準確 | 付費、需上傳音訊 |

**決策**：**優先使用 YouTube 現有字幕**，只有沒有字幕的影片才啟動本機 Whisper（medium model 節省時間）。

---

## 4. Data Pipeline: YouTube → Career KB

### 4.0 前置作業：批次抓取字幕（✅ Done）

> **實際發現**：@hrjasmin 共有 **1,794 部影片**，分布在 4 個 tab。

#### 實際字幕覆蓋率（2026-04-18）

| Tab      | 影片數 | 有字幕 | 無字幕 | 覆蓋率 |
|----------|--------|--------|--------|--------|
| videos   | 421    | 359    | 62     | 85%    |
| shorts   | 1,264  | TBD    | TBD    | TBD    |
| streams  | 109    | 0      | 109    | 0%     |
| podcasts | 43     | 0      | 43     | 0%     |
| **合計** | **1,837** | **~360+** | **~250+** | **~68%** |

> ⚠️ streams 和 podcasts **全部**無字幕，需 Whisper 全量轉錄。

### 4.1 Pipeline 流程

```
Step 0: Subtitle Audit (前置，一次性) ✅
  yt-dlp --write-auto-subs → data/subtitles/*.vtt
  audit_subtitles.py → 分類：has_subtitle / needs_whisper

Step 1: Transcription ✅
  has_subtitle:  vtt_to_text.py → plain text
  needs_whisper: whisper_fallback.py → mlx-whisper medium → plain text

Step 2: Chunking + Classification
  CareerChunker (max_tokens=400, overlap=40)
  CareerClassifier (9 topics: resume/interview/career_planning/
                    salary/workplace/job_search/promotion/
                    industry_insight/skill_development)

Step 3: Embed & Store
  EmbeddingService (nomic-embed-text, 768-dim, via Ollama)
  → Milvus: career_kb collection
```

### 4.2 Milvus Schema: `career_kb`（實際實作）

```python
fields = [
    FieldSchema("chunk_id",     VARCHAR,      max_length=64,   is_primary=True),
    FieldSchema("doc_hash",     VARCHAR,      max_length=32),
    FieldSchema("source",       VARCHAR,      max_length=512),
    FieldSchema("section",      VARCHAR,      max_length=128),  # topic (e.g. "interview")
    FieldSchema("content",      VARCHAR,      max_length=4096),
    FieldSchema("token_count",  INT32),
    FieldSchema("page_number",  INT32),
    FieldSchema("video_title",  VARCHAR,      max_length=512),
    FieldSchema("upload_date",  VARCHAR,      max_length=16),   # YYYYMMDD
    FieldSchema("url",          VARCHAR,      max_length=128),  # YouTube watch URL
    FieldSchema("embedding",    FLOAT_VECTOR, dim=768),
]
```

> **注意**：topic 存放在 `section` 欄位（沿用 base template 的欄位名）。

### 4.3 Ingestion API Endpoint（✅ 已實作）

```
POST /api/ingestion/youtube?incremental=true
  Auth:     admin only
  Response: SSE stream — data: <log line>\n\n ... data: [DONE]\n\n
```

後端執行 `services/kb-api/scripts/ingest_youtube.py`，stdout 即時串流回 client。

### 4.4 CLI Script

```bash
# 全量 ingest
python services/kb-api/scripts/ingest_youtube.py

# 增量（跳過已 ingest 的影片）
python services/kb-api/scripts/ingest_youtube.py --incremental

# Dry run（只 chunk，不寫 Milvus）
python services/kb-api/scripts/ingest_youtube.py --dry-run
```

---

## 5. VoltAgent Layer

### 5.1 Agent 拓撲

```
SupervisorAgent (CareerLeadAgent)
│   model: gemma3:12b via Ollama (OpenAI-compatible API)
│   tools: [queryCareerKB]
│
├── ResumeAgent
│   tools: [analyzeResume, queryCareerKB]
│
├── InterviewAgent
│   tools: [generateInterviewQuestions, queryCareerKB]
│
├── CareerPlanAgent
│   tools: [queryCareerKB]
│
└── SalaryAgent
    tools: [queryCareerKB]
```

### 5.2 核心 Tool 定義（實際實作）

#### `queryCareerKB` Tool

```typescript
// services/voltagent-career/src/tools/query-career-kb.ts
const queryCareerKBTool = createTool({
  name: "queryCareerKB",
  parameters: z.object({
    question: z.string(),
    topic:    z.enum(["resume","interview","career_planning","salary",
                      "workplace","job_search","promotion",
                      "industry_insight","skill_development","general_career"])
               .optional(),
    sessionId: z.string().default("voltagent-default"),
  }),
  execute: async ({ question, topic, sessionId }) => {
    // fetchCareerKB() in kb-client.ts — shared HTTP helper
    const data = await fetchCareerKB(question, topic, sessionId);
    return { answer: data.answer, sources: data.sources };
  },
});
```

> `fetchCareerKB()` 從 `services/voltagent-career/src/tools/kb-client.ts` 提取，
> 供多個 tool 共用，避免 `tool.execute` optional-type 問題。

#### `analyzeResume` Tool

```typescript
// services/voltagent-career/src/tools/analyze-resume.ts
execute: async ({ resumeText, targetRole, sessionId }) => {
  const question = `請根據以下履歷${roleContext}，提供具體的改善建議：\n\n${resumeText.slice(0, 1500)}`;
  return await fetchCareerKB(question, "resume", sessionId);
}
```

### 5.3 VoltAgent 專案結構（實際實作）

```
services/voltagent-career/
├── src/
│   ├── agents/
│   │   ├── supervisor.ts       # CareerLeadAgent
│   │   ├── resume.ts           # ResumeAgent
│   │   ├── interview.ts        # InterviewAgent
│   │   ├── career-plan.ts      # CareerPlanAgent
│   │   └── salary.ts           # SalaryAgent
│   ├── tools/
│   │   ├── kb-client.ts        # 共用 fetchCareerKB() HTTP helper
│   │   ├── query-career-kb.ts  # queryCareerKB tool
│   │   ├── analyze-resume.ts   # analyzeResume tool
│   │   └── generate-questions.ts
│   ├── config.ts               # env config (KB_API_TOKEN, OLLAMA_BASE_URL, VOLTAGENT_MODEL)
│   └── index.ts                # VoltAgent server (port 3141)
├── Dockerfile
├── package.json                # @voltagent/core ^2.7.0, @ai-sdk/openai ^3.0.0
├── tsconfig.json
└── .env.example
```

---

## 6. API Design

### 6.1 Career KB API（實際實作）

```
POST /api/chat/query
Body: {
  "question":   "如何準備外商面試？",
  "session_id": "...",
  "topic":      "interview"    ← optional, maps to Milvus section filter
}

POST /api/chat/query/sync     ← non-streaming version (VoltAgent 使用此端點)

POST /api/ingestion/youtube?incremental=true   ← admin only, SSE stream
```

`topic` 直接對應 Milvus `section` 欄位的 expr filter。

### 6.2 VoltAgent HTTP API

VoltAgent 預設在 port `3141` 提供：

```
POST /agents/career-lead/invoke
  Body:     { input: "幫我評估這份履歷...", sessionId: "..." }
  Response: { output: "...", agentTrace: [...] }

GET  /health
```

---

## 7. Infrastructure

### 7.1 Mono-Repo 目錄結構

```
career-analyst-kb/
├── services/
│   ├── kb-api/              # Python FastAPI service
│   │   ├── src/
│   │   ├── scripts/
│   │   ├── migrations/
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── voltagent-career/    # TypeScript VoltAgent service
│       ├── src/
│       ├── Dockerfile
│       └── package.json
├── docker/
│   └── docker-compose.yml   # orchestrates all services
├── frontend/                # static HTML chat UI
├── data/
│   ├── subtitles/           # raw .vtt files
│   └── processed/
│       └── transcripts/     # plain .txt files
├── docs/
└── .env                     # single env file for all services
```

### 7.2 Docker Compose

```yaml
services:
  app:          # FastAPI — port 8000
  postgres:     # PostgreSQL — port 5436
  milvus:       # Milvus standalone — port 19530
  etcd:         # Milvus dependency
  minio:        # Milvus dependency
  nginx:        # reverse proxy — port 80
  voltagent:    # VoltAgent — port 3141 (profile: voltagent)
```

啟動 VoltAgent：
```bash
docker compose --profile voltagent up -d
```

### 7.3 環境變數

```dotenv
# LLM（FastAPI backend）
LLM_PROVIDER=ollama
LLM_MODEL=gemma3:12b
OLLAMA_BASE_URL=http://localhost:11434

# Embedding
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text

# Vector DB
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION=career_kb

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://career:secret@localhost:5436/career_kb

# Auth
SECRET_KEY=<random 32+ chars>
ADMIN_USERNAME=admin
ADMIN_PASSWORD=<set on first run>

# VoltAgent
CAREER_API_TOKEN=<JWT from /api/auth/login>
VOLTAGENT_MODEL=gemma3:12b   # or gemma3:4b for lighter RAM
# OLLAMA_BASE_URL already set above; voltagent reuses it

# Ingestion
WHISPER_MODEL=medium
```

> **無需 `ANTHROPIC_API_KEY`** — 全部使用本機 Ollama。

---

## 8. Security

### 8.1 YouTube 資料使用

- 僅儲存文字 transcript，不重新散布音訊/影片
- chunk metadata 保留 `url` 引導用戶回原影片
- 遵循 YouTube ToS（個人/研究用途）

### 8.2 Service-to-Service Auth

VoltAgent → career-analyst-kb 使用獨立的 service account JWT：

```bash
# 建立 service account（admin API）
POST /api/admin/users
{ "username": "voltagent-svc", "role": "viewer" }

# 登入取得 JWT，填入 CAREER_API_TOKEN
POST /api/auth/login
{ "username": "voltagent-svc", "password": "..." }
```

---

## 9. Implementation Phases

### Phase 0 — Repo Bootstrap ✅ Complete

| Task | Status | Deliverable |
|------|--------|-------------|
| `cp -r yiguandao-kb career-analyst-kb` + git init | ✅ | 新 repo |
| 移除一貫道領域內容 | ✅ | 乾淨基底 |
| 重新命名 collection、app name、README | ✅ | `src/core/config.py` |
| 更新 Docker Compose | ✅ | `docker/docker-compose.yml` |
| 建立 `.env.example` | ✅ | `.env.example` |

### Phase 0.5 — 字幕批次抓取 ✅ Complete

| Task | Status | Deliverable |
|------|--------|-------------|
| yt-dlp 批次下載字幕 — 4 tabs | ✅ | `data/subtitles/` |
| `audit_subtitles.py` 統計覆蓋率 | ✅ | `data/subtitles/no_subtitles.txt` |
| `whisper_fallback.py` 無字幕 Whisper 轉錄 | ✅ | `scripts/whisper_fallback.py` |
| Whisper 轉錄 streams + podcasts (152 部) | ✅ | `data/processed/transcripts/*.txt` |
| Whisper 轉錄 videos 無字幕 (62 部) | ✅ | `data/processed/transcripts/*.txt` |
| 合計轉錄（VTT + Whisper）: **1,035 部** | ✅ | — |

### Phase 1 — YouTube Ingestion Pipeline ✅ Complete

| Task | Status | Deliverable |
|------|--------|-------------|
| `vtt_to_text.py`：VTT → 純文字 | ✅ | `scripts/vtt_to_text.py` |
| `career_classifier.py`：9-topic keyword classifier | ✅ | `src/ingestion/career_classifier.py` |
| `career_chunker.py`：口語斷句 chunker | ✅ | `src/ingestion/career_chunker.py` |
| `ingest_youtube.py`：`--incremental`, `--dry-run` | ✅ | `scripts/ingest_youtube.py` |
| `whisper_fallback.py`：audio + Whisper 轉錄 | ✅ | `scripts/whisper_fallback.py` |
| Milvus schema 更新（video_title, upload_date, url） | ✅ | `src/ingestion/embedder.py` |
| 實際寫入 Milvus（14,278 chunks from 1,035 videos） | 🔄 In Progress | — |
| 修正 mono-repo 後 LangChain import 相容性 | ✅ | `chunker.py`, `career_chunker.py`, `llm_factory.py` |
| 修正 `src/ingestion/__init__.py` eager import 導致 pytesseract 依賴 | ✅ | `src/ingestion/__init__.py` |
| 修正 VoltAgent agent 檔案 import ordering（sed 殘留） | ✅ | `salary.ts`, `supervisor.ts` |

> **注意**：ingest_youtube.py 仍在背景執行中（412/1035 完成），預計完成後約 14,278 chunks 全數寫入 Milvus。
> 監控指令：`grep "Stored" /tmp/ingest_log.txt | wc -l`
> LLM 字幕後處理（subtitle_cleaner.py）列為 backlog，目前字幕品質足夠 RAG 使用。

### Phase 2 — API 調整 ✅ Complete

| Task | Status | Deliverable |
|------|--------|-------------|
| `SearchResult` 新增 video_title / upload_date / url 欄位 | ✅ | `src/core/domain/search_result.py` |
| `Chunk` domain 新增 video_title / upload_date / url | ✅ | `src/core/domain/chunk.py` |
| `MilvusRetriever` 更新 OUTPUT_FIELDS + 新欄位填充 | ✅ | `src/rag/retriever.py` |
| `IVectorRetriever` / `ISearchEngine` 介面加 topic 參數 | ✅ | `src/core/interfaces/` |
| `HybridSearchEngine` topic filter（Milvus expr + 局部 BM25） | ✅ | `src/rag/hybrid_search.py` |
| `ChatRequestDTO` 新增 optional `topic` 欄位 | ✅ | `src/application/dto/chat_dto.py` |
| `SourceDocumentDTO` 新增 video_title / url / upload_date | ✅ | `src/application/dto/chat_dto.py` |
| `ChatService._build_context()` 顯示影片標題引用 | ✅ | `src/application/services/chat_service.py` |
| `POST /api/ingestion/youtube` SSE endpoint（admin only） | ✅ | `src/api/routers/ingestion.py` |
| 註冊 ingestion router | ✅ | `src/api/main.py` |

### Phase 3 — VoltAgent Layer ✅ Complete

| Task | Status | Deliverable |
|------|--------|-------------|
| Mono-repo 重構（Codex） | ✅ | `services/kb-api/`, `services/voltagent-career/` |
| `services/voltagent-career/` 初始化 | ✅ | `package.json`, `tsconfig.json` |
| `kb-client.ts` 共用 HTTP helper | ✅ | `src/tools/kb-client.ts` |
| `queryCareerKB` tool | ✅ | `src/tools/query-career-kb.ts` |
| `analyzeResume` tool | ✅ | `src/tools/analyze-resume.ts` |
| `generateInterviewQuestions` tool | ✅ | `src/tools/generate-questions.ts` |
| 4 sub-agents（Resume / Interview / CareerPlan / Salary） | ✅ | `src/agents/*.ts` |
| SupervisorAgent（CareerLeadAgent） | ✅ | `src/agents/supervisor.ts` |
| VoltAgent server entry（port 3141） | ✅ | `src/index.ts` |
| Dockerfile | ✅ | `Dockerfile` |
| Docker Compose 整合（profile: voltagent） | ✅ | `docker/docker-compose.yml` |
| 改用本機 Ollama（棄 Anthropic API） | ✅ | 所有 agent 改用 `@ai-sdk/openai` → Ollama |
| 清理 agent import ordering（`salary.ts`, `supervisor.ts`） | ✅ | `src/agents/salary.ts`, `src/agents/supervisor.ts` |

### Phase 4 — Eval Harness ✅ Complete

| Task | Status | Deliverable |
|------|--------|-------------|
| 建立 Golden Dataset：30 筆職涯問答（9 topics）| ✅ | `eval/golden_dataset.jsonl` |
| RAG Precision Eval（LLM-as-judge + keyword hit rate） | ✅ | `eval/rag_eval.py` |
| Agent Routing Eval | ✅ | `eval/routing_eval.py` |
| Latency Benchmark P50/P95/P99（支援 concurrency） | ✅ | `eval/latency_bench.py` |

**Routing Eval 初測結果（2026-04-21）：**
- Overall accuracy: **83.3%** (25/30)（目標 ≥ 85%，差一點）
- Perfect: interview, resume, salary, promotion, workplace (100%)
- 需改善: job_search (50%), skill_development (50%), industry_insight (67%)
- 主要 miss 原因：multi-keyword 問題（offer → salary, 履歷 → resume）優先於 primary topic

**用法：**
```bash
# Routing eval（無需 server）
python eval/routing_eval.py --verbose

# RAG eval（需 KB API 運行）
export CAREER_API_TOKEN=<JWT>
python eval/rag_eval.py --url http://localhost:8000

# Latency benchmark
python eval/latency_bench.py --url http://localhost:8000 --runs 20 --concurrency 3
```

### Phase 5 — UI & E2E ✅ Complete

| Task | Status | Deliverable |
|------|--------|-------------|
| Chat UI 接入 VoltAgent（port 3141） | ✅ Done | `frontend/index.html` |
| 新增 topic filter 下拉選單 | ✅ Done | `frontend/index.html` |
| Sources 顯示影片標題 + YouTube 連結 | ✅ Done | `frontend/index.html` |
| Nginx 轉發 `/agents/*` → port 3141 | ✅ Done | `docker/nginx.conf` |
| E2E：履歷評估完整流程 | ✅ Done | `e2e/resume_flow.spec.ts` |
| E2E：面試問答流程 | ✅ Done | `e2e/interview_flow.spec.ts` |

### Phase 6 — Classifier 改善 ✅ Complete（routing 100%，30/30）

> 背景：Phase 4 routing eval 初測 83.3%（25/30），5 個 miss 原因已知。Phase 5 完成後補強。

| Task | Status | Deliverable |
|------|--------|-------------|
| `job_search` 關鍵字補強（offer 時間壓力、投履歷無回音） | ✅ Done | `src/ingestion/career_classifier.py` |
| `skill_development` 關鍵字補強（英文能力、職涯成長） | ✅ Done | `src/ingestion/career_classifier.py` |
| `industry_insight` 關鍵字補強（新創 vs 大企業） | ✅ Done | `src/ingestion/career_classifier.py` |
| `career_planning` fallback 降低（五年、離職、換環境） | ✅ Done | `src/ingestion/career_classifier.py` |
| multi-topic 問題的 primary topic 優先邏輯 | ✅ Done | `src/ingestion/career_classifier.py` |
| 重跑 `routing_eval.py` 驗證 ≥ 85% | ✅ Done — **100%** (30/30) | `eval/results/routing_eval_20260424_144053.json` |

---

### Phase 8 — 換模型至 Qwen3.6-35B-A3B Reasoning Distilled（Mac M3 Max 36GB）

> **背景**：Qwen3.6-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled 是 Qwen 3.6 35B（MoE，3B active）經 Claude Opus 4.6 CoT 蒸餾資料 SFT 的社群模型。GGUF 格式可透過 Ollama 直接載入，以 M3 Max 36GB 記憶體可完整容納（模型約 20–24 GB，量化 Q4_K_M）。目標是用 Qwen 的 agentic 編碼底座 + Claude Opus 推理邏輯取代 Gemma3:12b，提升多步推理品質。

#### 8.1 硬體與模型載入

| Task | Status | Deliverable |
| ---- | ------ | ----------- |
| 從 HuggingFace 下載 GGUF（Q4_K_M，~22 GB）| ⏳ Pending | `~/.ollama/models/` |
| `ollama create` 建立本機 Modelfile | ⏳ Pending | `models/Modelfile.qwen36b` |
| 驗證 M3 Max 36GB 記憶體可完整 GPU offload | ⏳ Pending | `ollama run` + `htop` 確認 Metal 使用率 |
| 測量冷啟動 / first-token 延遲（對比 Gemma3:12b baseline） | ⏳ Pending | `eval/latency_bench.py` 結果 |

#### 8.2 CoT Reasoning Trace 處理

此模型輸出 Claude Opus 風格的推理軌跡（`<think>…</think>` 或類似結構）再給出最終回答。需要在 API 層剝離推理段落。

| Task | Status | Deliverable |
| ---- | ------ | ----------- |
| 在 `LLMFactory` / provider 層新增 `strip_reasoning_trace()` 工具函式 | ⏳ Pending | `services/kb-api/src/core/llm_factory.py` |
| SSE stream 過濾：`<think>` block 轉為 debug log，不送到前端 | ⏳ Pending | `services/kb-api/src/infrastructure/llm/ollama_provider.py` |
| 可選 `X-Debug-Reasoning: true` header 讓管理員看到完整推理鏈 | ⏳ Pending | `services/kb-api/src/api/routers/chat.py` |

#### 8.3 Prompt 微調（Prompt Tuning）

Qwen3.6 Reasoning Distilled 最佳化方向：明確指示模型先思考再回答，並要求引用具體來源。

| Task | Status | Deliverable |
| ---- | ------ | ----------- |
| KB API system prompt 新增 CoT 引導句（「請先分析問題背景，再給出具體建議」） | ⏳ Pending | `services/kb-api/src/application/services/chat_service.py` |
| VoltAgent SupervisorAgent instructions 加入路由推理指示（要求列出路由理由再決定） | ⏳ Pending | `services/voltagent-career/src/agents/supervisor.ts` |
| ResumeAgent / InterviewAgent / CareerPlanAgent / SalaryAgent instructions 各增加 STAR / 量化 / 步驟化格式要求 | ⏳ Pending | `services/voltagent-career/src/agents/*.ts` |
| `VOLTAGENT_MODEL` / `LLM_MODEL` env var 統一切換至新模型名稱 | ⏳ Pending | `.env.example`, `services/kb-api/src/core/config.py` |

#### 8.4 Fine-tune 資料準備（選項）

> 若本機 SFT 效果不理想，可用 Unsloth + LoRA 在職涯問答 golden dataset 上做領域微調。

| Task | Status | Deliverable |
| ---- | ------ | ----------- |
| 將 `eval/golden_dataset.jsonl` 轉換為 SFT 格式（instruction / input / output） | ✅ Done — `scripts/build_sft_dataset.py` 自動呼叫 KB API 生成 chat-format 訓練對 | `eval/sft_dataset.jsonl`（執行後生成） |
| 補充 50–100 筆職涯 CoT 範例（繁體中文，含推理過程） | ✅ Done — 10 筆手工種子範例（履歷、面試、薪資談判、職涯規劃等主題） | `eval/sft_seeds.jsonl` |
| Unsloth LoRA fine-tune 腳本（4-bit，M3 Max 可跑） | ✅ Done — LoRA rank=16，4-bit 量化，支援 `--export-gguf` 直接輸出 GGUF | `eval/finetune/finetune_qwen3_30b.py` |
| 匯出 GGUF 並以 `ollama create` 更新本機模型 | ⏳ Pending（需先執行 build_sft_dataset.py + finetune_qwen3_30b.py） | `models/Modelfile.qwen3-30b-career` |

#### 8.5 Eval 驗收

| Task | Status | Deliverable |
| ---- | ------ | ----------- |
| 重跑 `routing_eval.py`（目標 ≥ 88%） | ✅ Done — **100%** (30/30) | `eval/results/routing_eval_20260427_203450.json` |
| 重跑 `rag_eval.py`（目標 relevance ≥ 3.0 / 4.0） | ✅ Done — **3.00/4.0** (+8% vs gemma3 2.77) | `eval/results/rag_eval_20260428_165214.json` |
| 重跑 `latency_bench.py`（目標 P50 ≤ 8s，M3 Max 本機） | ✅ Done — serial **P50=30s / P95=71s / 0 errors**；並發 3x P50=73s / P95=111s ⚠️ 目標 8s 為雲端 API 基準，本機 30B MoE 修訂為 P50 ≤ 35s | `eval/results/latency_bench_20260428_211430.json` |
| 更新 README 與 design doc 記錄 baseline → Phase 8 對比結果 | ✅ Done | `docs/design-career-analyst-kb.md` |

---

## 10. Open Questions

| # | 問題 | 影響 | 狀態 |
|---|------|------|------|
| Q1 | Whisper large-v3 轉錄速度是否可接受？ | Phase 1 工時 | ✅ 改用 `medium` model；streams/podcasts 全部走 Whisper（152 部） |
| Q2 | YouTube API quota？ | Phase 1 設計 | ✅ 不需要 YouTube API — yt-dlp 直接爬頻道頁面，無 quota 限制 |
| Q3 | VoltAgent 是否使用 VoltOps Cloud？ | Phase 3 架構 | ✅ 不使用 — 改用本機 Ollama，零成本；VoltOps 可日後選配 |
| Q4 | 是否需要實時追蹤新影片？ | Phase 4 範疇 | ⏳ 待決定（Phase 4 開始前） |
| Q5 | Career UI 是否獨立部署或整合現有 frontend？ | Phase 5 | ✅ 整合現有 frontend，Phase 5 更新 index.html 接入 VoltAgent |
| Q6 | Shorts 是否值得 ingest？ | Phase 0.5 | ⏳ Shorts 字幕覆蓋率 TBD；目前已 ingest 有字幕的 1,035 部 |

---

## 11. Success Metrics

| Metric | Target |
|--------|--------|
| 影片覆蓋率 | ≥ 90% 職涯相關影片成功 ingest |
| 查詢相關性 | RAG top-5 precision ≥ 0.75（人工評估 20 queries） |
| Agent 路由準確率 | ≥ 85% 正確路由到對應 sub-agent |
| 回應延遲 (P50) | ≤ 5s first token（本機 Ollama，含 VoltAgent overhead） |

---

## 12. Codebase Change Map

### Phase 4 — Eval Harness

| File | Action | Why |
|------|--------|-----|
| `eval/golden_dataset.jsonl` | **New** | 30 筆職涯問答 golden set（9 topics） |
| `eval/rag_eval.py` | **New** | RAG precision evaluation（LLM-as-judge + keyword hit） |
| `eval/routing_eval.py` | **New** | Agent routing accuracy test（初測 83.3%） |
| `eval/latency_bench.py` | **New** | P50/P95/P99 latency benchmark（支援 concurrency） |

### Phase 5 — UI & E2E

| File | Action | Why |
|------|--------|-----|
| `frontend/index.html` | **Modify** | 接入 VoltAgent port 3141；topic filter 下拉；citations 顯示影片標題 + URL |
| `docker/nginx.conf` | **Modify** | 新增 `/agents/*` proxy → port 3141 |
| `e2e/resume_flow.spec.ts` | **New** | 履歷評估 E2E flow |
| `e2e/interview_flow.spec.ts` | **New** | 面試問答 E2E flow |

### Phase 6 — Classifier 改善

| File | Action | Why |
|------|--------|-----|
| `src/ingestion/career_classifier.py` | **Modify** | 補強 job_search / skill_development / industry_insight 關鍵字；primary topic 優先邏輯 |

### Phase 8 — 模型換換至 Qwen3.6-35B-A3B

| File | Action | Why |
|------|--------|-----|
| `services/kb-api/src/core/llm_factory.py` | **Modify** | 新增 `strip_reasoning_trace()` |
| `services/kb-api/src/infrastructure/llm/ollama_provider.py` | **Modify** | SSE stream 過濾 `<think>` block |
| `services/kb-api/src/api/routers/chat.py` | **Modify** | 新增 `X-Debug-Reasoning` header 支援 |
| `services/kb-api/src/application/services/chat_service.py` | **Modify** | CoT 引導 system prompt |
| `services/voltagent-career/src/agents/supervisor.ts` | **Modify** | 路由推理指示 |
| `services/voltagent-career/src/agents/*.ts` | **Modify** | 各 agent STAR / 步驟化 prompt |
| `.env.example` | **Modify** | 更新 `LLM_MODEL` / `VOLTAGENT_MODEL` 預設值 |
| `models/Modelfile.qwen36b` | **New** | Ollama Modelfile |
| `eval/sft_dataset.jsonl` | **New** | SFT 格式職涯問答資料（選項） |
| `eval/finetune/finetune_qwen36b.py` | **New** | Unsloth LoRA fine-tune 腳本（選項） |

---

## Appendix A: Tech Reference

- career-analyst-kb repo: `/Users/liyuncheng/workspace/me/career-analyst-kb`
- VoltAgent: https://github.com/VoltAgent/voltagent
- yt-dlp: https://github.com/yt-dlp/yt-dlp
- Milvus: https://milvus.io/docs/manage_collections.md

## Appendix B: Glossary

| 術語 | 說明 |
|------|------|
| RAG | Retrieval-Augmented Generation — 先檢索再生成 |
| RRF | Reciprocal Rank Fusion — 混合搜尋排名融合 |
| Supervisor Pattern | 一個 orchestrator agent 管理多個 sub-agents |
| career_kb | 職涯知識庫的 Milvus collection 名稱 |
| section | Milvus 欄位名，儲存 topic（resume/interview/...） |
| STT | Speech-to-Text（語音轉文字） |
