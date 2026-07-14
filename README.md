# Career Analyst KB — 職涯分析師知識庫系統

基於 RAG（Retrieval-Augmented Generation）架構的職涯問答系統，知識來源為 YouTube 職涯影片字幕，支援混合向量搜索（Dense + BM25 + RRF）與 VoltAgent 多代理人協作。

---

## 系統架構

```
使用者 / Chat UI（kb-web, port 3000）
      │
      ▼ nginx（port 80）
VoltAgent Layer（TypeScript, port 3141）
  ① Guardrail（輸入過濾：主題相關性 / Prompt Injection / 有害內容）
  ② SupervisorAgent（CareerLeadAgent）
       → ResumeAgent / InterviewAgent / CareerPlanAgent / SalaryAgent
       → WebSearchAgent → SearXNG（即時搜尋，port 8080）
      │  HTTP
      ▼
Career KB API（FastAPI, port 8000）
  RAG Pipeline: Hybrid Search（Dense + BM25 + RRF）→ Ollama qwen3:14b
      │
      ├── Milvus（向量資料庫, port 19530）
      └── PostgreSQL（對話紀錄, port 5436）
```

**Mono-repo 結構：**

```
career-analyst-kb/
├── services/
│   ├── kb-api/              # Python FastAPI + RAG pipeline
│   ├── voltagent-career/    # TypeScript VoltAgent 多代理人層
│   └── kb-web/              # Next.js Chat UI + Admin Panel
├── eval/                    # Eval harness（routing / RAG / latency / A-B）
├── data/
│   └── processed/transcripts/  # 影片逐字稿
├── docker/
│   └── docker-compose.yml
└── docs/
    └── design-career-analyst-kb.md
```

---

## 請求流程

### User Query → Sub-Agent → RAG

```
使用者輸入問題
      │
      ▼
[kb-web] Chat UI
  使用者選擇模式：
  ① 直連模式 ──────────────────────────────────────────────────────► [KB API] /api/chat/query（SSE）
  ② VoltAgent 模式 ──► /agents/CareerLeadAgent/stream（SSE）           │
                              │                                         │
                              ▼                                         ▼
                    [Guardrail middleware]                    RAG Pipeline
                    fastModel（qwen3:4b）                    ├── BM25 sparse search
                    BLOCK → 拒絕訊息                         ├── Dense vector search（bge-m3）
                    PASS ↓                                    └── RRF fusion rerank
                              │                                         │
                              ▼                                         ▼
                    [SupervisorAgent]                         [Milvus] 向量資料庫
                    qwen3:14b                                 取回 top-k 相關影片片段
                    分析問題意圖                                         │
                    決定路由目標                                         ▼
                              │                              [Ollama] qwen3:14b
          ┌───────────────────┼──────────────────┬──────────► 根據片段生成回答
          ▼                   ▼                  ▼
    ResumeAgent         InterviewAgent     CareerPlanAgent
    SalaryAgent         qwen3:14b          qwen3:14b
          │             （specialist）     （specialist）
          │                   │                  │
          └───────────────────┴──────────────────┘
                              │
                    呼叫工具（擇一）：
                    ├── queryCareerKB ──────────────────────► 同上 RAG Pipeline
                    ├── analyzeJobDescription（InterviewAgent）
                    ├── mockInterviewSession（InterviewAgent）
                    └── analyzeResume（ResumeAgent）
                              │
                              ▼
                    [WebSearchAgent]（即時資訊類問題）
                    qwen3:14b → SearXNG REST API
                    適用：公司薪資行情 / 職場相處 / 主管管理 / 產業趨勢
                              │
                              ▼
                    Sub-agent 生成專業回應
                              │
                              ▼
                    SSE stream 回傳 → Chat UI 即時顯示
```

### Hill Climbing — Supervisor Prompt 自動優化迴圈

Hill climbing 是一套以 eval 結果驅動的 supervisor routing instructions 持續改善機制：

```
① Eval Harness
   eval/routing_eval.py 執行 golden dataset（30 題）
   記錄每題的 routing trace → eval/results/trace_analysis_latest.json
         │
         ▼
② Harness Improver（hill-climbing/harness-improver.ts）
   讀取 trace_analysis_latest.json + 當前 supervisor.ts instructions
   呼叫 LLM 分析 routing 失誤模式
   產出 proposed-diffs（每條 diff 含 original_excerpt / replacement）
   風險分類：low_risk（加關鍵字/釐清規則）/ high_risk（重構路由邏輯）
         │
         ▼
③ 人工 Review（Admin Panel → Hill Climbing Tab）
   列出所有 pending diffs，顯示風險等級與 rationale
   管理員勾選要套用的 diff → 按「Apply」
         │
         ▼
④ Apply
   備份當前 supervisor.ts → hill-climbing/backups/supervisor_YYYYMMDD_HHMMSS.ts
   將勾選的 diff patch 寫入 supervisor.ts instructions
   記錄到 apply-log.jsonl（timestamp / applied / missed / gate_passed）
         │
         ▼
⑤ 驗證
   重跑 routing_eval.py 確認 accuracy 是否提升
   若退步 → 從 backups/ 還原上一版
```

**核心概念**：每輪迭代都是「量測 → 分析失誤 → 提出修改 → 人工把關 → 套用 → 再量測」，讓 supervisor routing 在不更動模型權重的前提下持續收斂。

---

## 前置需求

- [Ollama](https://ollama.com) 已安裝並執行
- Docker + Docker Compose
- Python 3.11+（venv 建議，僅開發用）

---

## 快速開始

### 1. 拉取 Ollama 模型

```bash
ollama serve &
ollama pull qwen3:14b        # LLM（~9 GB，supervisor + specialist）
ollama pull bge-m3           # Embedding model（~1.7 GB）
```

> **記憶體參考（M3 Max 36GB）**：qwen3:14b 約 11GB VRAM，bge-m3 約 1.7GB，加 macOS + Docker 共約 16-18GB，不會 swap。

### 2. 設定環境變數

```bash
cp .env.example .env
# 修改 ADMIN_PASSWORD（首次啟動時自動建立管理員帳號）
```

主要設定值（`.env`）：

```dotenv
# KB API
LLM_PROVIDER=ollama
LLM_MODEL=qwen3:14b
OLLAMA_BASE_URL=http://localhost:11434

EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=bge-m3

DATABASE_URL=postgresql+asyncpg://career:secret@localhost:5436/career_kb
MILVUS_HOST=localhost
MILVUS_COLLECTION=career_kb

ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme123        # 首次啟動後請修改

# VoltAgent
CAREER_API_TOKEN=<POST /api/auth/token 取得>
VOLTAGENT_MODEL=qwen3:14b         # SupervisorAgent 用
SPECIALIST_MODEL=qwen3:14b        # 各 sub-agent 用

# Langfuse（可選，LLM tracing）
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

### 3. 啟動服務

```bash
cd docker
docker compose up -d
```

| 服務 | 用途 | Port |
|------|------|------|
| `app` | FastAPI KB API | 8000 |
| `voltagent` | VoltAgent 多代理人層 | 3141 |
| `kb-web` | Next.js Chat UI + Admin Panel | 3000 |
| `searxng` | 自架搜尋引擎（WebSearchAgent 後端） | — |
| `postgres` | 對話紀錄 / metadata | 5436 |
| `milvus-standalone` | 向量資料庫 | 19530 |
| `etcd` / `minio` | Milvus 依賴 | — |
| `nginx` | 反向代理（統一入口） | 80 |

```bash
docker compose ps
curl http://localhost/health
```

### 4. 匯入 YouTube 知識庫

```bash
cd services/kb-api

# 增量匯入（跳過已匯入影片）
python3.11 scripts/ingest_youtube.py --incremental >> /tmp/ingest_log.txt 2>&1 &

# 監控進度
while true; do echo "$(date +%H:%M) done: $(grep 'Stored' /tmp/ingest_log.txt | wc -l)/1035"; sleep 60; done
```

### 5. 開啟 Chat UI

```bash
open http://localhost          # Chat 介面（nginx 入口）
open http://localhost:3000     # Chat 介面（直連 kb-web）
open http://localhost:8000/docs  # Swagger API 文件
```

登入：使用 `ADMIN_USERNAME` / `ADMIN_PASSWORD`（預設 `admin` / `changeme123`）。

---

## VoltAgent 多代理人層

使用者問題由 **Guardrail** 過濾後，交由 **SupervisorAgent（CareerLeadAgent）** 路由到對應的專家子 agent：

| 元件 / Agent | 職責 | 模型 |
|-------------|------|------|
| **Guardrail** | 輸入過濾：主題相關性、Prompt Injection、有害內容；BLOCK 直接拒絕，失敗則放行 | fastModel（qwen3:4b）|
| **SupervisorAgent** | 問題理解、路由決策、整合多 agent 回應 | qwen3:14b |
| **ResumeAgent** | 履歷撰寫、ATS 關鍵字優化、版面結構 | qwen3:14b |
| **InterviewAgent** | 面試準備、STAR 方法、模擬問答、JD 分析 | qwen3:14b |
| **CareerPlanAgent** | 職涯規劃、轉職路徑、技能 Gap 分析 | qwen3:14b |
| **SalaryAgent** | 薪資行情、談判策略、offer 評估 | qwen3:14b |
| **WebSearchAgent** | 即時資訊：公司薪資行情、職場相處、主管管理課題、產業趨勢 | qwen3:14b |

**Chat UI 切換方式**：`localhost:3000` 右下角 Toggle → 切換到「VoltAgent 多 Agent 路由模式」。

### Agent 工具對照

| Agent | 工具 | 說明 |
|-------|------|------|
| ResumeAgent | `analyzeResume` | 履歷評分、ATS 優化建議 |
| ResumeAgent | `queryCareerKB` | 查詢 YouTube KB 影片知識 |
| InterviewAgent | `analyzeJobDescription` | 分析 JD 必要技能、面試題方向、準備策略，可搭配履歷做 gap 分析 |
| InterviewAgent | `mockInterviewSession` | 模擬面試：評估候選人回答、STAR 架構分析、追問建議 |
| InterviewAgent | `generateInterviewQuestions` | 針對特定職位生成面試題目 |
| InterviewAgent | `queryCareerKB` | 查詢 YouTube KB 影片知識 |
| CareerPlanAgent | `queryCareerKB` | 查詢 YouTube KB 影片知識 |
| SalaryAgent | `queryCareerKB` | 查詢 YouTube KB 影片知識 |
| WebSearchAgent | `webSearch` | 呼叫 SearXNG 取得即時搜尋結果，Ollama 整合成職涯分析 |

詳見 [services/voltagent-career/README.md](./services/voltagent-career/README.md)

---

## Chat UI（kb-web）

Next.js 前端，功能：

- **雙模式切換**：直連 KB API SSE 模式 vs VoltAgent 多 Agent 路由模式
- **主題篩選**：履歷 / 面試 / 薪資 / 職涯規劃 / 求職 / 升遷 / 職場 / 技能發展
- **Admin Panel**：文件管理、System Prompt 設定、知識缺口分析、User 管理

詳見 [services/kb-web/README.md](./services/kb-web/README.md)

---

## Eval Harness

| 腳本 | 指標 | 說明 |
|------|------|------|
| `routing_eval.py` | Topic routing accuracy | 不需啟動 server |
| `rag_eval.py` | RAG relevance 0–4（LLM-as-judge）、keyword hit rate | KB API + Ollama |
| `latency_bench.py` | avg / P50 / P95 / P99（可設並發） | KB API |
| `ab_eval.py` | A/B 對比（qwen3:8b vs qwen3:14b） | KB API + Ollama |

```bash
# Routing accuracy（不需要 server）
python eval/routing_eval.py --verbose

# RAG precision（需要 KB API + Ollama 運行）
export CAREER_API_TOKEN=<JWT>
python eval/rag_eval.py --url http://localhost:8000

# Latency benchmark（並發 3，共 20 次請求）
python eval/latency_bench.py --url http://localhost:8000 --runs 20 --concurrency 3
```

初測結果：routing accuracy **83.3%** (25/30)

---

## Tech Stack

| 層級 | 技術 |
|------|------|
| **Chat UI** | Next.js 15（App Router）+ Tailwind CSS |
| **KB API** | FastAPI 0.115 + Python 3.11 |
| **Agent Layer** | VoltAgent 2.7 + TypeScript |
| **LLM** | Ollama qwen3:14b（supervisor + specialist） |
| **Embedding** | Ollama bge-m3（1024 dim） |
| **Vector DB** | Milvus 2.4 |
| **Search** | Dense + BM25 + RRF fusion |
| **Web Search** | SearXNG（自架，無 API 費用）|
| **Relational DB** | PostgreSQL 16 |
| **Auth** | JWT HS256 |
| **Tracing** | Langfuse（可選） |

---

## 主要 API 端點

| 方法 | 端點 | 說明 |
|------|------|------|
| POST | `/api/auth/token` | 登入取得 JWT |
| POST | `/api/chat/query` | SSE 串流問答 |
| POST | `/api/chat/query/sync` | 同步問答（VoltAgent 使用）|
| POST | `/api/ingestion/youtube` | 觸發 YouTube ingest（admin，SSE）|
| GET | `/api/sessions` | 列出對話 Sessions |
| GET | `/health` | 健康檢查 |

完整 API 文件：`http://localhost:8000/docs`

---

## 開發

```bash
# KB API
cd services/kb-api
python3.11 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v

# VoltAgent
cd services/voltagent-career
npm install
npm run dev        # hot reload，port 3141

# kb-web
cd services/kb-web
npm install
npm run dev        # port 3000（本地開發用，需設 VOLTAGENT_URL）
```

---

## 相關文件

- [系統設計文件](./docs/current/design-career-analyst-kb.md)
- [Guardrail + WebSearchAgent 設計](./docs/current/design-guardrail-web-agent.md)
- [KB API README](./services/kb-api/README.md)
- [VoltAgent README](./services/voltagent-career/README.md)
- [kb-web README](./services/kb-web/README.md)
