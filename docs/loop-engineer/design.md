# Loop Engineering Design — Career Analyst KB

**Author**: Albert
**Date**: 2026-07-09
**Status**: Draft

---

## 1. 背景

Career Analyst KB 目前是 VoltAgent（TypeScript）+ FastAPI RAG（Python）的雙層架構。SupervisorAgent 路由到 4 個 sub-agent，透過 `queryCareerKB` tool 查詢 Milvus 職涯知識庫（YouTube @hrjasmin 頻道 1,794 部影片轉錄）。

### 現況問題

- RAG eval 3.00/4.0（qwen3-30b-a3b）——距目標 3.5/4.0 仍有差距
- Routing 無 confidence gate：低信心問題仍強制路由，導致答案品質不穩定
- 無 Answer Quality Judge：無法在線上自動偵測不良回答
- Eval pipeline（golden_dataset.jsonl、rag_eval.py、routing_eval.py）已有，但缺少 regression gate
- 無 Knowledge Gap Detection：不知道知識庫哪些主題覆蓋不足
- Supervisor prompt 靠人工分析 failure → 手動調整，沒有自動化

---

## 2. Loop 1 — Agent Loop（已完成）

### 架構

```
使用者問題
    │
    ▼
SupervisorAgent (CareerLeadAgent)
    │  routing 決策樹
    ▼
┌─────────────────────────────────────┐
│  ResumeAgent       InterviewAgent  │
│  CareerPlanAgent   SalaryAgent     │
└─────────────────────────────────────┘
    │
    ▼  queryCareerKB tool
FastAPI /api/chat/query/sync
    │
    ▼
Hybrid RAG (BM25 + Dense + RRF) → Milvus (career_kb)
    │
    ▼
LLM 生成回答 (Ollama qwen3-30b-a3b)
    │
    ▼
回傳使用者
```

### 現有 sub-agent 分工

| Agent | 觸發條件 | Tools |
|-------|---------|-------|
| ResumeAgent | 履歷撰寫、自我介紹、LinkedIn profile | queryCareerKB, analyzeResume |
| InterviewAgent | 面試準備、STAR 回答、常見問題 | queryCareerKB, generateQuestions |
| CareerPlanAgent | 職涯規劃、轉職、職位選擇 | queryCareerKB |
| SalaryAgent | 薪資談判、package 拆解、加薪時機 | queryCareerKB |
| SupervisorAgent | 所有入口，fallback 兜底 | routes to above |

### 已知限制

- qwen3-30b-a3b 在「無資料」情境偶有 timeout（>300s）
- ResumeAgent ↔ CareerPlanAgent 偶發混淆（轉職主題）
- SalaryAgent 問題有時被 SupervisorAgent 直接回答而未路由

---

## 3. Loop 2 — Verification Loop（未實作，優先實作）

### 目標

在 Agent Loop 加入兩個自動驗證關卡，讓低品質回答在回傳前被攔截或重試。

### 設計

```
使用者問題
    │
    ▼
SupervisorAgent
    │
    ├── 關卡 A：Routing Confidence Gate
    │     └── confidence < 0.7 → fallback + 標記 routing_fallback: true
    ▼
sub-agent → queryCareerKB → LLM 生成
    │
    ├── 關卡 B：Answer Quality Judge
    │     └── score < 3 → supervisor 重試（最多 1 次）
    │     └── score ≤ 2 → 記錄 knowledge gap
    ▼
回傳使用者
```

### 關卡 A — Routing Confidence Gate

- 實作位置：`services/voltagent-career/src/middleware/routing-classifier.ts`
- 邏輯：Supervisor routing decision 後，計算 confidence score（0–1）
  - 基於 query 與 agent 職責描述的語義相似度
  - 或由 LLM 回傳 JSON `{ "agent": "...", "confidence": 0.85 }`
- `confidence-gate.ts`：confidence < 0.7 時 fallback 到 SupervisorAgent 直接回答，並附 `routing_fallback: true` metadata
- fallback 事件寫入 `routing_fallbacks` 表供 Hill Climbing 分析

### 關卡 B — Answer Quality Judge

- 實作位置：`services/voltagent-career/src/judges/answer-quality.ts`
- 使用 LLM-as-Judge 評分 1–4（Haiku 模型做 judge，成本低）
  - 4: 完整、有引用、有行動建議
  - 3: 正確但不完整
  - 2: 部分正確，有誤導
  - 1: 錯誤或完全無關
- score < 3 → 觸發重試（最多 1 次）
- score ≤ 2 → 記錄到 `knowledge_gaps` 表（query, agent, score, timestamp）

### 知識缺口偵測

- 每日 summary：聚合昨日 score ≤ 2 的問題，按主題分群
- 主題缺口自動產生補充 ingestion 建議（e.g., 「salary negotiation 主題缺少具體數字範例」）

---

## 4. Loop 3 — Event-Driven Loop（未實作）

### 目標

知識庫自動感知新內容（新影片），並在特定條件下主動更新。

### 設計

```
YouTube @hrjasmin 頻道
    │
    ├── [定時檢查] yt-dlp --date-after yesterday → 新影片清單
    │         → 自動 ingest 新字幕 → Milvus 更新
    │
    └── [知識缺口] knowledge_gaps 表
              → 缺口主題 → 搜尋相關影片 → 手動確認 ingest
```

### 實作項目

| 項目 | 說明 | 優先級 |
|------|------|--------|
| 定時新影片檢查 | cron job 每日執行 `yt-dlp --date-after` 抓新影片 | 🟡 中 |
| 自動 ingest pipeline | 新字幕 → STT → chunk → embed → Milvus | 🟡 中 |
| 知識缺口驅動的 manual ingest 建議 | 缺口分析 → 推薦影片 → 人工確認 | 🟢 低 |
| Webhook notification | ingest 完成 → 通知 Slack/email | 🟢 低 |

---

## 5. Loop 4 — Hill Climbing Loop（未實作）

### 目標

自動分析 eval 失敗原因，產生 supervisor prompt diff，low-risk 自動套用，high-risk 人工審核。

### 設計

```
Eval Dataset (golden_dataset.jsonl / routing_eval.py)
    │
    ▼
Trace Analyzer
    │  分析高頻混淆 agent pair、持續失敗題目
    ▼
Harness Improver (LLM)
    │  產生 supervisor prompt diff
    │  分類 low-risk / high-risk
    ▼
┌─────────────────────────────────────┐
│  low-risk → Auto Apply             │
│             eval gate 通過後套用    │
│  high-risk → Human Review          │
│             pending store          │
│             approve / reject       │
└─────────────────────────────────────┘
    │
    ▼
Regression Gate
    │  routing accuracy 不低於 baseline
    │  RAG eval score 不低於 baseline
    └── pass → 套用；fail → rollback
```

### Prompt as Code 原則

| ADR | 決策 |
|-----|------|
| ADR-001 | Prompt 有版本號（`PROMPT_VERSION: N`），每次 eval 記錄版本 |
| ADR-002 | Eval 是 release gate：routing 與 RAG 兩個 baseline 都必須維持 |
| ADR-003 | low-risk diff = 加範例、澄清邊界；high-risk diff = 改路由邏輯、移除 agent |
| ADR-004 | Auto Apply 後 eval 下滑 → 自動 rollback + 通知 |

---

## 6. 總體現況評估

| 面向 | 現況 | 缺口 |
|------|------|------|
| Agent Routing | ✅ 4 sub-agents 正確路由大部分問題 | ResumeAgent/CareerPlanAgent 混淆 ~10% |
| Verification | ❌ 無 confidence gate / quality judge | Loop 2 全未實作 |
| Knowledge Coverage | ⚠️ RAG eval 3.00/4.0，部分主題稀疏 | 需 knowledge gap detection |
| Eval Pipeline | ✅ golden_dataset.jsonl、rag_eval.py | 缺 regression gate |
| Prompt Evolution | ⚠️ 人工分析 + 手動修改 | 缺 Hill Climbing 自動化 |
| Observability | ❌ 只有 console.log | 需 Langfuse 整合（見 observability/design.md） |
| Multi-model | ❌ 單一 qwen3-30b-a3b | 需 model gateway（見 multi-model/design.md） |
