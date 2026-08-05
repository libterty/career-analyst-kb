# Career Analyst KB

職涯問答系統。知識來源是 YouTube 職涯影片字幕,問答走 RAG(混合向量搜索 + LLM 生成),前面掛一層 VoltAgent 多代理人做問題路由(履歷 / 面試 / 職涯規劃 / 薪資 / 即時搜尋)。

## 架構

```text
Chat UI (kb-web, :3000)
      │ nginx (:80)
      ▼
VoltAgent (:3141)                 Career KB API (:8000)
  Guardrail → QueryDecomposer  →   Agentic RAG Pipeline
  → SupervisorAgent → 專家 Agent      relevance check → query rewrite
     (Resume/Interview/Plan/Salary)   → hybrid search (dense+BM25)
  → WebSearchAgent (SearXNG)          → 多輪迭代 → LLM 生成
                                          │
                                    Milvus(向量) / PostgreSQL(對話紀錄)
```

Mono-repo:

```text
career-analyst-kb/
├── services/
│   ├── kb-api/           # FastAPI + RAG pipeline
│   ├── voltagent-career/ # 多代理人層 (TypeScript)
│   └── kb-web/           # Next.js Chat UI + Admin Panel
├── eval/                 # Eval harness
├── data/processed/       # 影片逐字稿
├── docker/
└── docs/                 # 設計文件（見下方「進階閱讀」）
```

RAG retrieval 有兩種實作,用 `.env` 的 `MODE` 切換,行為與回傳型別完全相同:

- `MODE=Agentic`(預設)——既有 self-reflection 迴圈,inline 實作
- `MODE=Graph`——同一套邏輯改用 State/Node/Edge 的 Graph 建模,可觀測性更細

## 前置需求

- [Ollama](https://ollama.com)、Docker + Docker Compose
- Python 3.11+(僅開發用)

## 快速開始

```bash
# 1. 拉模型
ollama serve &
ollama pull qwen3:14b   # LLM，~9GB
ollama pull bge-m3      # Embedding，~1.7GB

# 2. 設定環境變數
cp .env.example .env    # 記得改 ADMIN_PASSWORD

# 3. 啟動
cd docker && docker compose up -d
curl http://localhost/health

# 4. 匯入知識庫（背景執行，1000+ 部影片會跑一陣子）
cd services/kb-api
python3.11 scripts/ingest_youtube.py --incremental >> /tmp/ingest_log.txt 2>&1 &

# 5. 開啟
open http://localhost           # Chat UI
open http://localhost:8000/docs # API 文件
```

登入用 `.env` 裡的 `ADMIN_USERNAME` / `ADMIN_PASSWORD`。

| 服務 | 用途 | Port |
| --- | --- | --- |
| `app` | KB API | 8000 |
| `voltagent` | 多代理人層 | 3141 |
| `kb-web` | Chat UI + Admin Panel | 3000 |
| `postgres` | 對話紀錄 | 5436 |
| `milvus-standalone` | 向量資料庫 | 19530 |
| `searxng` | WebSearchAgent 後端 | — |
| `nginx` | 統一入口 | 80 |

## 主要 API

| 方法 | 端點 | 說明 |
| --- | --- | --- |
| POST | `/api/auth/token` | 登入取得 JWT |
| POST | `/api/chat/query` | SSE 串流問答 |
| POST | `/api/chat/query/sync` | 同步問答（VoltAgent 用） |
| POST | `/api/ingestion/youtube` | 觸發 YouTube ingest（admin） |
| GET | `/health` | 健康檢查 |

完整文件:`http://localhost:8000/docs`

## Tech Stack

Next.js 15 · FastAPI + Python 3.11 · VoltAgent 2.7 (TypeScript) · Ollama(qwen3:14b / bge-m3) · Milvus 2.4 · PostgreSQL 16 · SearXNG · Langfuse(可選 tracing)

## 開發

```bash
# KB API
cd services/kb-api
python3.11 -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v

# VoltAgent
cd services/voltagent-career && npm install && npm run dev   # :3141

# kb-web
cd services/kb-web && npm install && npm run dev             # :3000，需設 VOLTAGENT_URL
```

Eval:

```bash
python eval/routing_eval.py --verbose                 # routing accuracy，不需 server
python eval/rag_eval.py --url http://localhost:8000   # RAG relevance，需 KB API + Ollama
python eval/latency_bench.py --url http://localhost:8000 --runs 20 --concurrency 3
```

## 進階閱讀

各主題的完整設計與實作細節都在 `docs/` 底下:

- [系統設計](./docs/current/design-career-analyst-kb.md) · [Guardrail + WebSearchAgent](./docs/current/design-guardrail-web-agent.md) · [Request Flow](./docs/current/request-flow.md)
- [Agentic RAG](./docs/agentic-rag/design.md)(RelevanceChecker / QueryRewriter / 多輪迭代取回)
- [Graph Engineering](./docs/graph-design/)(retrieval 的 Graph 化版本、候選評分、為何不用 LangGraph 等現成框架)
- [Hill Climbing](./docs/loop-engineer/design.md)(用 eval 結果驅動 supervisor routing prompt 的自動優化迴圈)
- [Model Gateway](./docs/multi-model/design.md)(多模型分工)
- [可觀測性](./docs/observability/design.md)
- 各服務自己的 README:[kb-api](./services/kb-api/README.md) · [voltagent-career](./services/voltagent-career/README.md) · [kb-web](./services/kb-web/README.md)
