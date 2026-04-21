# Career Analyst KB — 職涯分析師知識庫系統

基於 RAG（Retrieval-Augmented Generation）架構的職涯問答系統，知識來源為 YouTube 頻道 YouTube 職涯影片字幕，支援混合向量搜索（Dense + BM25 + RRF）與 VoltAgent 多代理人協作。預設使用本機 **Ollama + Gemma3:12b**，零成本運行。

---

## 系統架構

```
使用者 / Chat UI
      │
      ▼
VoltAgent Layer (TypeScript, port 3141)
  SupervisorAgent → ResumeAgent / InterviewAgent / CareerPlanAgent / SalaryAgent
      │  HTTP
      ▼
Career KB API (FastAPI, port 8000)
  RAG Pipeline: Hybrid Search (Dense + BM25 + RRF) → Ollama LLM
      │
      ├── Milvus (向量資料庫, port 19530)
      └── PostgreSQL (對話紀錄, port 5436)
```

**Mono-repo 結構：**

```
career-analyst-kb/
├── services/
│   ├── kb-api/              # Python FastAPI + RAG pipeline
│   └── voltagent-career/    # TypeScript VoltAgent 多代理人層
├── eval/                    # Eval harness（routing / RAG / latency）
├── data/
│   └── processed/transcripts/  # 影片逐字稿
├── docker/
│   └── docker-compose.yml
├── frontend/                # 靜態 HTML Chat UI
└── docs/
    └── design-career-analyst-kb.md
```

---

## 前置需求

- [Ollama](https://ollama.com) 已安裝並執行
- Docker + Docker Compose
- Python 3.11+（venv 建議）

---

## 快速開始

### 1. 拉取 Ollama 模型

```bash
ollama serve &                     # 啟動 Ollama
ollama pull gemma3:12b             # LLM（~8 GB）
ollama pull nomic-embed-text       # Embedding model（~274 MB）
```

> 記憶體不足可改用 `gemma3:4b`（~4 GB），在 `.env` 調整 `LLM_MODEL`。

### 2. 設定環境變數

```bash
cp .env.example .env
# 修改 ADMIN_PASSWORD（首次啟動時自動建立管理員帳號）
```

主要設定值（`.env`）：

```dotenv
LLM_PROVIDER=ollama
LLM_MODEL=gemma3:12b
OLLAMA_BASE_URL=http://localhost:11434

EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text

DATABASE_URL=postgresql+asyncpg://career:secret@localhost:5436/career_kb
MILVUS_HOST=localhost
MILVUS_COLLECTION=career_kb

ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme123        # 首次啟動後請修改

# VoltAgent（Phase 3+）
CAREER_API_TOKEN=<POST /api/auth/login 取得>
VOLTAGENT_MODEL=gemma3:12b
```

### 3. 啟動服務

```bash
cd docker
docker compose up -d
```

| 服務 | 用途 | Port |
|------|------|------|
| `app` | FastAPI KB API | 8000 |
| `postgres` | 對話紀錄 / metadata | 5436 |
| `milvus-standalone` | 向量資料庫 | 19530 |
| `etcd` / `minio` | Milvus 依賴 | — |
| `nginx` | 反向代理 | 80 |

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
open http://localhost          # Chat 介面
open http://localhost:8000/docs  # Swagger API 文件
```

---

## VoltAgent 多代理人層（Phase 3+）

使用者問題由 **SupervisorAgent（CareerLeadAgent）** 接收，依主題路由到對應的專家子 agent：

| Agent | 職責 |
| ----- | ---- |
| **SupervisorAgent** | 理解問題、路由決策、整合多 agent 回應 |
| **ResumeAgent** | 履歷撰寫、ATS 關鍵字優化、版面結構建議 |
| **InterviewAgent** | 面試準備、STAR 方法指導、模擬問答生成 |
| **CareerPlanAgent** | 職涯規劃、轉職路徑、技能 Gap 分析 |
| **SalaryAgent** | 薪資行情、談判策略、offer 綜合評估 |

所有 agent 透過 `queryCareerKB` tool 存取 KB API，回應引用具體影片內容。

```bash
# 另開一個 terminal
cd services/voltagent-career
npm install
npm run dev                    # 開發模式，port 3141
```

或透過 Docker Compose profile：

```bash
docker compose --profile voltagent up -d
```

詳見 [services/voltagent-career/README.md](./services/voltagent-career/README.md)

---

## Eval Harness（Phase 4）

三支評測腳本共用一份 **golden dataset**（`eval/golden_dataset.jsonl`，30 題，涵蓋 resume / interview / career_plan / salary / general 五個 topic），結果寫入 `eval/results/`。

| 腳本 | 指標 | 依賴 |
| ---- | ---- | ---- |
| `routing_eval.py` | Topic routing accuracy（CareerClassifier） | 不需要啟動 server |
| `rag_eval.py` | Relevance score 0–4（LLM-as-judge）、keyword hit rate、sources 附帶率 | KB API + Ollama |
| `latency_bench.py` | avg / P50 / P95 / P99（可設並發） | KB API |

**routing_eval.py** — 直接 import `CareerClassifier` 在本機執行，測試問題是否被分類到預期 topic（允許多 topic 命中）。

**rag_eval.py** — 對 `/api/chat/query/sync` 發送問題，用 Ollama judge model（預設 `gemma3:12b`）對回答打 0–4 分，同時計算 expected_keywords 命中率與來源引用率。

**latency_bench.py** — 以可設定並發數（`--concurrency`）對 KB API 打壓，輸出完整百分位數分布。

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

## Phase 8 — 模型升級計畫

**目標**：以 [Qwen3.6-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled](https://huggingface.co/hesamation/Qwen3.6-35B-A3B-Claude-4.6-Opus-Reasoning-Distilled-GGUF) 取代現行 Gemma3:12b。

此模型為 Qwen 3.6 35B（MoE，實際 active 3B 參數）以 Claude Opus 4.6 的 Chain-of-Thought 蒸餾資料做 SFT，保留 Qwen 的 agentic 編碼底座，同時獲得 Claude Opus 級別的推理結構。GGUF Q4_K_M 量化版本約 22 GB，可完整 GPU offload 在 **Mac M3 Max 36GB**。

**Phase 8 實作範圍**：

1. 透過 Ollama 載入 GGUF 並驗證 Metal GPU offload
2. API 層過濾 `<think>…</think>` 推理軌跡，不送到前端（可選 debug header 暴露）
3. Prompt 微調：KB API system prompt 加入 CoT 引導、各 VoltAgent sub-agent instructions 強化推理格式要求
4. LoRA fine-tune（Unsloth，選項）：以職涯問答 golden dataset 做領域 SFT
5. 重跑 eval harness 對比 Gemma3:12b baseline（目標 routing ≥ 88%、RAG relevance ≥ 3.0/4.0）

詳見 [設計文件 Phase 8](./docs/design-career-analyst-kb.md)。

---

## Tech Stack

| 層級 | 技術 |
|------|------|
| **KB API** | FastAPI 0.115 + Python 3.11 |
| **Agent Layer** | VoltAgent 2.7 + TypeScript |
| **LLM** | Ollama Gemma3:12b（現行）→ Qwen3.6-35B-A3B Reasoning Distilled（Phase 8）/ xAI Grok（可選） |
| **Embedding** | Ollama nomic-embed-text（768 dim）|
| **Vector DB** | Milvus 2.4 |
| **Search** | Dense + BM25 + RRF fusion |
| **Relational DB** | PostgreSQL 16 |
| **Auth** | JWT HS256 |

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
cd services/kb-api
python3.11 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

---

## 相關文件

- [設計文件](./docs/design-career-analyst-kb.md)
- [KB API README](./services/kb-api/README.md)
- [VoltAgent README](./services/voltagent-career/README.md)
