# Design Doc: Career Analyst Knowledge Base + VoltAgent Integration

**Author**: Albert  
**Date**: 2026-04-18  
**Status**: Draft  
**Scope**: 職涯分析師 KB — YouTube 影片知識庫 + VoltAgent Agent 管理層

---

## 1. Problem Statement

### 1.1 背景

目標頻道 [@hrjasmin](https://www.youtube.com/@hrjasmin) 持續產出職涯相關內容。這些影片包含大量隱性知識（履歷撰寫、面試技巧、職涯規劃、薪資談判等），但分散在數十支影片中，難以系統性查詢與應用。

### 1.2 目標

1. **Knowledge Base**：將頻道職涯影片的語音內容轉化為可查詢的向量知識庫
2. **Career Analyst Agent**：以此 KB 為基底，提供職涯諮詢、履歷評估、面試準備等能力
3. **Agent Management**：引入 VoltAgent 統一管理多個專門 agent，並提供 VoltOps 可觀測性

### 1.3 非目標 (Out of Scope)

- 影片版權重新散布
- 即時監控頻道新影片（Phase 1 不含，可未來擴充）
- 自訓練 fine-tuned model（使用 RAG 即可）

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
│   VoltAgent Layer      │            │   yiguandao-kb API          │
│   (TypeScript/Node)    │◄──────────►│   (FastAPI / Python)        │
│                        │  HTTP      │                             │
│  ┌──────────────────┐  │            │  /api/chat/query (SSE)      │
│  │ SupervisorAgent  │  │            │  /api/documents/upload      │
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
│  YouTube API  →  yt-dlp  →  Whisper (STT)  →  Transcript          │
│                                ↓                                   │
│              Topic Classifier  →  Chunker  →  Embedder             │
│                                              ↓                     │
│                                      Milvus: career_kb             │
└────────────────────────────────────────────────────────────────────┘
```

---

## 3. Architecture Decisions

### 3.1 以 yiguandao-kb 為樣板，建立獨立 Repo

yiguandao-kb 已有成熟的：
- Milvus vector store、Hybrid Search（BM25 + Dense + RRF）
- FastAPI + SSE streaming
- JWT auth、rate limiting、semantic cache
- Clean Architecture（ingestion / rag / api / security 分層）

**決策**：`cp -r yiguandao-kb career-analyst-kb` 建立全新獨立 repo，移除所有一貫道領域內容（glossary、system prompt、sample data），重新命名 collection 為 `career_kb`。兩個 repo 完全分離，不共用程式碼。

### 3.2 VoltAgent 作為 Agent 管理層

yiguandao-kb 的 FastAPI 是純 RAG API，缺乏：
- 多 agent 協作（Supervisor Pattern）
- Agent 狀態機 / Workflow
- 可觀測性（trace、span、metrics）
- 工具呼叫鏈（Tool Use）

**決策**：VoltAgent（TypeScript）作為 agent orchestration layer，透過 HTTP 呼叫 yiguandao-kb API。兩層獨立部署，透過 Docker Compose 整合。

### 3.3 語音轉文字策略

| 方案 | 優點 | 缺點 |
|------|------|------|
| YouTube 自動字幕 | 免費、快速 | 繁中品質差，錯字多 |
| OpenAI Whisper (local) | 高品質、離線 | 慢（large model ~2x 影片時長）|
| Whisper API | 快速、準確 | 付費、需上傳音訊 |

**決策**：**優先使用 YouTube 現有字幕**（yt-dlp 批次抓取），只有沒有字幕的影片才啟動 Whisper 轉錄。這樣可大幅縮短初始 ingest 時間。字幕品質問題用 LLM 後處理修正。

---

## 4. Data Pipeline: YouTube → Career KB

### 4.0 前置作業：批次抓取字幕（一次性執行）

在啟動完整 pipeline 前，先對整個頻道做字幕探勘，建立影片清單與字幕狀態的索引：

```bash
# Step 1：列出所有影片 ID + 標題（不下載）
yt-dlp --flat-playlist --print "%(id)s %(title)s" \
  https://www.youtube.com/@hrjasmin > data/video_list.txt

# Step 2：批次下載所有現有字幕（自動字幕 + 手動字幕，繁中優先）
yt-dlp \
  --write-auto-subs \
  --write-subs \
  --sub-langs "zh-TW,zh-Hant,zh" \
  --skip-download \
  --sub-format vtt \
  -o "data/subtitles/%(id)s.%(ext)s" \
  https://www.youtube.com/@hrjasmin

# Step 3：統計結果，找出沒有字幕的影片
python scripts/audit_subtitles.py \
  --video-list data/video_list.txt \
  --subtitle-dir data/subtitles/ \
  > data/missing_subtitles.txt
```

**預期結果**：大多數影片有自動生成字幕（zh-TW 或 zh），少數需 Whisper 補充。

### 4.1 Pipeline 流程

```
Step 0: Subtitle Audit (前置，一次性)
  yt-dlp --flat-playlist → video_list.txt
  yt-dlp --write-auto-subs → data/subtitles/*.vtt
  audit_subtitles.py → 分類：has_subtitle / needs_whisper

Step 1: Transcription（依字幕狀態分流）
  has_subtitle:
    vtt_to_text.py → 清理 VTT 格式 → plain text + timestamps
    LLM post-process → 修正錯字、斷句（批次，cheap model）
  needs_whisper:
    yt-dlp --extract-audio → mp3
    openai-whisper large-v3 → transcript + timestamps

Step 2: Enrichment
  Topic Classifier (LLM)
    → resume / interview / career_plan / salary / mindset / other
    → other → skip（不進 KB）
  Metadata: video_id, title, published_at, duration, url

Step 3: Chunking
  CareerChunker
    → max_tokens=512, overlap=64
    → 保留 timestamp_start / timestamp_end（方便引用影片片段）

Step 4: Embed & Store
  EmbeddingService (nomic-embed-text, 768-dim)
    → Milvus: career_kb
    → metadata: video_id, title, topic, timestamp_start, timestamp_end, url
```

### 4.2 Milvus Schema: `career_kb`

```python
fields = [
    FieldSchema("chunk_id",       VARCHAR, max_length=64,   is_primary=True),
    FieldSchema("video_id",       VARCHAR, max_length=32),
    FieldSchema("video_title",    VARCHAR, max_length=256),
    FieldSchema("topic",          VARCHAR, max_length=32),   # resume/interview/...
    FieldSchema("content",        VARCHAR, max_length=4096),
    FieldSchema("timestamp_start",INT32),                    # seconds
    FieldSchema("timestamp_end",  INT32),
    FieldSchema("published_at",   VARCHAR, max_length=32),
    FieldSchema("url",            VARCHAR, max_length=256),
    FieldSchema("token_count",    INT32),
    FieldSchema("embedding",      FLOAT_VECTOR, dim=768),
]
```

### 4.3 新增 API Endpoint

```
POST /api/ingestion/youtube
  Body: { channel_url: str, limit?: int, force_reingest?: bool }
  Auth: admin only
  Response: SSE stream of ingestion progress

GET /api/ingestion/youtube/status
  Response: { total_videos, processed, skipped, failed, last_run }
```

### 4.4 CLI Script

```bash
# 全量 ingest
python scripts/ingest_youtube.py \
  --channel https://www.youtube.com/@hrjasmin \
  --collection career_kb \
  --whisper-model large-v3

# 增量（只處理新影片）
python scripts/ingest_youtube.py \
  --channel https://www.youtube.com/@hrjasmin \
  --incremental

# 僅特定影片
python scripts/ingest_youtube.py \
  --video-id dQw4w9WgXcQ
```

---

## 5. VoltAgent Layer

### 5.1 Agent 拓撲

```
SupervisorAgent (Career Lead)
│   role: 分析使用者需求，路由到專門 agent，整合回應
│   model: claude-sonnet-4-6 (Anthropic)
│   tools: [routeToAgent, synthesizeResponse]
│
├── ResumeAgent
│   role: 履歷撰寫、評估、ATS 優化
│   tools: [queryCareerKB(topic="resume"), analyzeResume, suggestKeywords]
│
├── InterviewAgent
│   role: 面試準備、模擬問答、STAR 方法指導
│   tools: [queryCareerKB(topic="interview"), generateQuestions, evaluateAnswer]
│
├── CareerPlanAgent
│   role: 職涯規劃、轉職策略、技能 Gap 分析
│   tools: [queryCareerKB(topic="career_plan"), mapSkillGap, suggestRoadmap]
│
└── SalaryAgent
    role: 薪資談判、市場行情分析
    tools: [queryCareerKB(topic="salary"), compareSalary]
```

### 5.2 核心 Tool 定義

#### `queryCareerKB` Tool

```typescript
import { z } from "zod";

const queryCareerKBTool = createTool({
  name: "queryCareerKB",
  description: "Query the career knowledge base built from @hrjasmin YouTube videos",
  parameters: z.object({
    query:   z.string().describe("User's career question"),
    topic:   z.enum(["resume","interview","career_plan","salary","mindset","all"])
               .default("all"),
    limit:   z.number().default(5),
  }),
  execute: async ({ query, topic, limit }) => {
    const res = await fetch(`${KB_API_URL}/api/chat/query/sync`, {
      method: "POST",
      headers: { Authorization: `Bearer ${KB_API_TOKEN}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        collection: "career_kb",
        filter: topic !== "all" ? { topic } : undefined,
        top_k: limit,
      }),
    });
    return await res.json();
  },
});
```

#### `analyzeResume` Tool

```typescript
const analyzeResumeTool = createTool({
  name: "analyzeResume",
  description: "Analyze a resume text and provide structured feedback",
  parameters: z.object({
    resumeText: z.string(),
    targetRole: z.string().optional(),
  }),
  execute: async ({ resumeText, targetRole }) => {
    // LLM structured output with career KB context
  },
});
```

### 5.3 SupervisorAgent 路由邏輯

```typescript
const supervisorAgent = new Agent({
  name: "CareerLeadAgent",
  instructions: `
    你是一位資深職涯顧問，負責理解使用者的職涯問題並路由給最合適的專家。
    
    路由規則：
    - 履歷相關（寫法、格式、ATS）→ ResumeAgent
    - 面試相關（準備、練習、STAR）→ InterviewAgent  
    - 職涯規劃（轉職、升遷、技能）→ CareerPlanAgent
    - 薪資相關（談判、行情）→ SalaryAgent
    - 複合問題 → 依序呼叫多個 agent，整合回應
    
    所有回應以繁體中文輸出，引用影片來源時附上影片標題。
  `,
  model: anthropic("claude-sonnet-4-6"),
  subAgents: [resumeAgent, interviewAgent, careerPlanAgent, salaryAgent],
});
```

### 5.4 VoltAgent 專案結構

```
voltagent-career/
├── src/
│   ├── agents/
│   │   ├── supervisor.ts      # CareerLeadAgent
│   │   ├── resume.ts          # ResumeAgent
│   │   ├── interview.ts       # InterviewAgent
│   │   ├── career-plan.ts     # CareerPlanAgent
│   │   └── salary.ts          # SalaryAgent
│   ├── tools/
│   │   ├── query-career-kb.ts # queryCareerKB tool
│   │   ├── analyze-resume.ts
│   │   └── generate-questions.ts
│   ├── config.ts              # env config (KB_API_URL, API keys)
│   └── index.ts               # VoltAgent server entry
├── package.json
├── tsconfig.json
└── .env
```

---

## 6. API Design

### 6.1 Career KB API（獨立 repo）

collection 固定為 `career_kb`，無需切換參數。新增 `topic` filter 傳入 Milvus：

```
POST /api/chat/query
Body:
{
  "query": "如何準備外商面試？",
  "session_id": "...",
  "filter": { "topic": "interview" }
}
```

config 簡化為單一 collection：

```python
# src/core/config.py
class Settings(BaseSettings):
    milvus_collection: str = "career_kb"
    milvus_embedding_dim: int = 768
```

### 6.2 VoltAgent HTTP API

VoltAgent 預設在 port `3141` 提供：

```
POST /agents/career-lead/invoke
  Body: { input: "幫我評估這份履歷...", sessionId: "..." }
  Response: { output: "...", sources: [...], agentTrace: [...] }

GET  /agents/career-lead/sessions/:sessionId
GET  /health
```

---

## 7. Infrastructure

### 7.1 Docker Compose 擴充

```yaml
# docker/docker-compose.career.yml (extends docker-compose.yml)
services:
  voltagent:
    build: ../voltagent-career
    ports: ["3141:3141"]
    environment:
      KB_API_URL: http://app:8000
      KB_API_TOKEN: ${CAREER_API_TOKEN}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      VOLTAGENT_PUBLIC_KEY: ${VOLTAGENT_PUBLIC_KEY}
      VOLTAGENT_PRIVATE_KEY: ${VOLTAGENT_PRIVATE_KEY}
    depends_on: [app]

  whisper-worker:
    build: docker/whisper
    volumes:
      - ./data/youtube_audio:/audio
      - ./data/transcripts:/transcripts
    environment:
      WHISPER_MODEL: large-v3
    profiles: ["ingestion"]  # 只在 ingestion 時啟動
```

### 7.2 環境變數新增

```dotenv
# Career KB
CAREER_COLLECTION=career_kb
YOUTUBE_API_KEY=...         # YouTube Data API v3
WHISPER_MODEL=large-v3      # base / small / medium / large-v3

# VoltAgent
VOLTAGENT_PUBLIC_KEY=...
VOLTAGENT_PRIVATE_KEY=...
CAREER_API_TOKEN=...        # 內部 service token (non-user JWT)

# LLM for agents
ANTHROPIC_API_KEY=...       # VoltAgent 使用 claude-sonnet-4-6
```

---

## 8. Security

### 8.1 YouTube 資料使用

- 僅儲存文字 transcript，不重新散布音訊/影片
- 在 chunk metadata 保留 `url` 方便引導用戶回原影片
- 遵循 YouTube ToS（個人/研究用途）

### 8.2 Service-to-Service Auth

VoltAgent → yiguandao-kb 使用獨立的 `service_account` role JWT，不用使用者 token。

```python
# admin API: 建立 service account
POST /api/admin/users
{ "username": "voltagent-svc", "role": "viewer", "max_sessions": 0 }
```

### 8.3 Guardrails (VoltAgent 層)

```typescript
const careerGuardrail = {
  input: (text: string) => {
    // Block off-topic queries (e.g. medical, legal, financial advice)
    if (isOffTopic(text)) return { blocked: true, reason: "本系統僅提供職涯相關諮詢" };
  },
  output: (text: string) => {
    // Strip any PII accidentally surfaced from transcripts
  },
};
```

---

## 9. Implementation Phases

### Phase 0 — Repo Bootstrap (0.5 天)

> **Owner**: Backend / DevOps

| Task | Deliverable |
|------|-------------|
| `cp -r yiguandao-kb career-analyst-kb` + git init | 新 repo |
| 移除一貫道領域內容：glossary、system prompt、sample data | 乾淨基底 |
| 重新命名 collection、app name、README | `src/core/config.py` 更新 |
| 更新 Docker Compose service 名稱與 port 規劃 | `docker/docker-compose.yml` |
| 建立新的 `.env.example`（含 YouTube/Whisper 欄位） | `.env.example` |

### Phase 0.5 — 字幕批次抓取（前置，一次性）

> **Owner**: Backend（先做，不需要其他 phase 就緒）

| Task | Deliverable |
|------|-------------|
| yt-dlp 列出頻道全部影片 ID + 標題 | `data/video_list.txt` |
| yt-dlp 批次下載所有現有字幕（VTT，繁中） | `data/subtitles/*.vtt` |
| `audit_subtitles.py`：統計有/無字幕影片 | `data/missing_subtitles.txt` |

### Phase 1 — YouTube Ingestion Pipeline (2–3 天)

> **Owner**: Backend

| Task | Deliverable |
|------|-------------|
| `vtt_to_text.py`：VTT 格式解析 + 時間戳記提取 | `scripts/vtt_to_text.py` |
| LLM 字幕後處理：修正錯字、斷句（有字幕影片用） | `src/finetuning/subtitle_cleaner.py` |
| Whisper 轉錄（無字幕影片 fallback） | `scripts/transcribe.py` |
| Topic Classifier（LLM 分類：resume / interview / career_plan / salary / mindset / skip） | `src/finetuning/career_classifier.py` |
| CareerChunker（保留 timestamp metadata） | `src/ingestion/career_chunker.py` |
| Milvus `career_kb` collection schema + migration | `migrations/versions/` |
| `ingest_youtube.py` 整合 CLI（支援 `--incremental`） | `scripts/ingest_youtube.py` |

### Phase 2 — API 調整 (1 天)

> **Owner**: Backend

| Task | Deliverable |
|------|-------------|
| Chat API 新增 `filter` param（topic → Milvus metadata filter） | `src/api/routers/chat.py` |
| `/api/ingestion/youtube` admin endpoint（SSE progress） | `src/api/routers/ingestion.py` |
| Service account JWT（供 VoltAgent 呼叫用） | admin seed script |
| System prompt 改寫為職涯顧問角色 | `src/application/services/chat_service.py` |

### Phase 3 — VoltAgent Layer (2–3 天)

> **Owner**: TS / Agent Engineer

| Task | Deliverable |
|------|-------------|
| `career-agent/` 專案初始化（`npm create voltagent-app@latest`） | 獨立 TS repo |
| `queryCareerKB` tool（呼叫 KB API） | `src/tools/query-career-kb.ts` |
| 4 個 sub-agents（Resume / Interview / CareerPlan / Salary） | `src/agents/*.ts` |
| SupervisorAgent + 路由邏輯 | `src/agents/supervisor.ts` |
| VoltOps 接入（公私鑰 + trace 確認） | `.env` + VoltOps Console |
| Docker Compose 整合（career-analyst-kb + career-agent） | `docker-compose.yml` |

### Phase 4 — Eval Harness (1–2 天)

> **Owner**: Harness Engineer

Harness 的任務是在 agent 路由和 RAG 回應上建立可量測的 baseline，讓後續任何改動都有數字依據。

| Task | Deliverable |
|------|-------------|
| 建立 Golden Dataset：30 筆職涯問答（含預期 topic 標籤、預期 sub-agent） | `eval/golden_dataset.jsonl` |
| RAG Precision Eval：top-5 檢索相關性（LLM-as-judge） | `eval/rag_eval.py` |
| Agent Routing Eval：自動化驗證 SupervisorAgent 路由準確率 | `eval/routing_eval.py` |
| Latency Benchmark：P50 / P95 end-to-end（VoltAgent → KB → LLM） | `eval/latency_bench.py` |
| CI 整合：每次 merge 跑 eval，低於 threshold 阻擋 | `.github/workflows/eval.yml` |

### Phase 5 — UI & E2E (1–2 天)

> **Owner**: Frontend / QA

| Task | Deliverable |
|------|-------------|
| 職涯顧問 Chat UI（全新 frontend） | `frontend/index.html` |
| E2E：履歷評估完整流程 | `e2e/resume_flow.spec.ts` |
| E2E：面試問答流程 | `e2e/interview_flow.spec.ts` |
| VoltOps trace 截圖驗證 | QA report |

---

## 10. Open Questions

| # | 問題 | 影響 | 預計決定時間 |
|---|------|------|------------|
| Q1 | Whisper large-v3 轉錄速度是否可接受？ | Phase 1 工時 | Phase 1 開始前 |
| Q2 | YouTube API quota：每日 10,000 units，列片單夠用？ | Phase 1 設計 | Phase 1 開始前 |
| Q3 | VoltAgent 是否使用 VoltOps Cloud 或 self-host？ | Phase 3 架構 | Phase 3 開始前 |
| Q4 | 是否需要實時追蹤新影片（Cron/Webhook）？| Phase 4 範疇 | Phase 3 完成後 |
| Q5 | Career UI 是否獨立部署或整合現有 frontend？| Phase 4 | Phase 4 開始前 |

---

## 11. Success Metrics

| Metric | Target |
|--------|--------|
| 影片覆蓋率 | ≥ 90% 職涯相關影片成功 ingest |
| 查詢相關性 | RAG top-5 precision ≥ 0.75 (人工評估 20 queries) |
| Agent 路由準確率 | ≥ 85% 正確路由到對應 sub-agent |
| 回應延遲 (P50) | ≤ 3s (first token, VoltAgent → KB → LLM) |
| VoltOps Trace | 100% 對話可在 VoltOps Console 查到完整 trace |

---

## Appendix A: Tech Reference

- yiguandao-kb repo: `/Users/liyuncheng/workspace/me/yiguandao-kb`
- VoltAgent: https://github.com/VoltAgent/voltagent
- YouTube Data API v3: https://developers.google.com/youtube/v3
- yt-dlp: https://github.com/yt-dlp/yt-dlp
- Whisper: https://github.com/openai/whisper
- Milvus multi-collection: https://milvus.io/docs/manage_collections.md

## Appendix B: Glossary

| 術語 | 說明 |
|------|------|
| RAG | Retrieval-Augmented Generation — 先檢索再生成 |
| RRF | Reciprocal Rank Fusion — 混合搜尋排名融合 |
| Supervisor Pattern | 一個 orchestrator agent 管理多個 sub-agents |
| VoltOps | VoltAgent 的雲端可觀測性 Console |
| career_kb | 職涯知識庫的 Milvus collection 名稱 |
| STT | Speech-to-Text（語音轉文字） |
