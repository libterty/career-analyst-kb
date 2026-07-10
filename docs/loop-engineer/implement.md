# Loop Engineering — 實作計畫

**Author**: Albert
**Date**: 2026-07-09
**Status**: Planning
**關聯設計文件**: [design.md](./design.md)

---

## 願景：Personal Career Intelligence Platform

本計畫的最終目標不是「會聊天的 RAG」，而是一個能自我學習、持續改進的職涯諮詢平台，具備：

- **可引用的知識檢索**（RAG + hybrid search + citation，YouTube 知識庫）
- **可驗證的回答品質**（Verification Loop + Answer Quality Judge）
- **可自我更新的知識庫**（Event-Driven：YouTube 新影片自動 ingest）
- **可自我改進的 Prompt**（Hill Climbing：eval 驅動的自動 prompt 優化）
- **可觀測的系統行為**（Langfuse：trace + eval + prompt 版本管理）

---

## 現有工作狀態

### 已完成（Phase 1–8）

| 項目 | 說明 |
|------|------|
| Mono-Repo 架構 | `services/kb-api/` + `services/voltagent-career/` |
| Agent Loop | SupervisorAgent → 4 sub-agents（Resume/Interview/CareerPlan/Salary） |
| RAG Pipeline | Hybrid Search（BM25 + Dense + RRF）→ Milvus（career_kb） |
| Eval Pipeline | golden_dataset.jsonl、rag_eval.py、routing_eval.py |
| RAG Eval Score | 3.00/4.0（qwen3-30b-a3b） |
| SFT Seeds | sft_seeds.jsonl 初步建立 |

### 未完成

| 項目 | 狀態 |
|------|------|
| Verification Loop（Loop 2） | ❌ 未實作 |
| Event-Driven Loop（Loop 3） | ❌ 未實作 |
| Hill Climbing Loop（Loop 4） | ❌ 未實作 |
| Observability（Langfuse） | ❌ 未整合 |
| Multi-model Gateway | ❌ 未實作 |

---

## Phase A — Verification Loop（最高優先）

> **目標**：讓 Agent Loop 有自動品質驗證，阻止低品質回答直接回傳。

### A-1：Routing Confidence Gate

**前置**：無

- [ ] 新增 `services/voltagent-career/src/middleware/routing-classifier.ts`
  - Supervisor routing decision 後計算 confidence（LLM 回傳 JSON `{ agent, confidence }`）
- [ ] 新增 `services/voltagent-career/src/middleware/confidence-gate.ts`
  - confidence < 0.7 → fallback，附 `routing_fallback: true` metadata
- [ ] 在 `src/agents/supervisor.ts` 的 routing decision 後接入 confidence gate
- [ ] fallback 事件寫入 `routing_fallbacks` 表

**完成條件**：低信心 routing 不再強制路由，改為 supervisor 直接回答 + metadata 標記

### A-2：Answer Quality Judge

**前置**：A-1

- [ ] 新增 `services/voltagent-career/src/judges/answer-quality.ts`
  - LLM-as-Judge 評分 1–4（使用 qwen3:8b，見 multi-model/design.md）
  - score < 3 → supervisor 重試（最多 1 次）
  - score ≤ 2 → 記錄到 `knowledge_gaps` 表
- [ ] 更新 `src/agents/supervisor.ts`：answer 生成後呼叫 judge
- [ ] `services/kb-api/src/` 新增 `knowledge_gaps` 表 migration

**完成條件**：每次回答都有 quality score；score ≤ 2 的問題自動記錄

### A-3：Eval Regression Gate

**前置**：現有 eval pipeline（已完成）

- [ ] `eval/regression_check.py`：比對 routing eval 結果與 baseline
- [ ] `eval/regression_guard.py`：比對 RAG eval 結果與 baseline
- [ ] 建立 baseline 檔案（第一次執行後自動存檔）
- [ ] 確認：routing accuracy ≥ baseline、RAG eval ≥ 3.00/4.0

**完成條件**：regression gate 基礎設施就位

### A-4：Knowledge Gap Daily Summary

**前置**：A-2

- [ ] `eval/knowledge_gap_analyzer.py`：聚合每日 score ≤ 2 的問題，按主題分群
- [ ] 輸出 markdown report：`data/knowledge_gaps/YYYY-MM-DD.md`

**完成條件**：每日可看到哪些主題被問到但回答不好

---

## Phase B — Observability（高優先）

> **目標**：每個 request 可在 Langfuse 看到完整 trace。

見 [observability/design.md](../observability/design.md)，此處列 Phase A 依賴的項目：

- [ ] **B-A-1**（Phase A 前置）：Langfuse exporter 接入 VoltAgent，才能讓 judge score 附在 trace 上
- [ ] **B-A-2**：FastAPI RAG trace（Phase A 後再做）

---

## Phase C — Hill Climbing Loop

> **目標**：eval 驅動的自動 prompt 改進，reducing human toil。

**前置**：Phase A（eval regression gate）、Phase B（Langfuse trace）

### C-1：Trace Analyzer

- [ ] `hill-climbing/trace-analyzer.ts`（或 `eval/trace_analyzer.py`）
  - 輸入：routing_eval 結果 + routing_fallbacks 表
  - 輸出：高頻混淆 agent pair、持續失敗題目 top-20

### C-2：Harness Improver

- [ ] `hill-climbing/harness-improver.ts`
  - 輸入：trace analyzer 輸出 + 當前 supervisor prompt
  - 使用 LLM 產生 prompt diff
  - 分類 low-risk（加範例、澄清邊界）/ high-risk（改路由邏輯）

### C-3：Auto Apply

- [ ] `hill-climbing/auto-apply.ts`
  - low-risk diff → 套用 → 跑 regression gate → 通過才正式寫入
  - fail → rollback + 通知

### C-4：Human Review

- [ ] high-risk diff → 儲存 pending store
- [ ] `POST /api/hillclimbing/approve`、`POST /api/hillclimbing/reject` endpoints

**完成條件**：low-risk prompt diff 可自動套用；regression gate 保護不讓 eval 下滑

---

## Phase D — Event-Driven Loop（中優先）

> **目標**：知識庫自動感知 YouTube 新影片並更新。

**前置**：Phase A（knowledge gap detection）

- [ ] cron job（`scripts/check_new_videos.sh`）：每日執行 yt-dlp 抓新影片清單
- [ ] 新影片 → 自動觸發 ingest pipeline（現有 STT → chunk → embed → Milvus）
- [ ] knowledge gap 分析 → 推薦影片搜尋關鍵字（人工確認後 ingest）

---

## Phase E — Multi-Model Gateway（中優先）

見 [multi-model/design.md](../multi-model/design.md)

- [ ] `src/gateway/model-gateway.ts`：task → model 映射
- [ ] Routing 改用 qwen3:8b（latency 改善）
- [ ] Judge 改用 qwen3:8b（資源節省）
- [ ] RAG 生成維持 qwen3-30b-a3b

---

## 完整里程碑

| Phase | 內容 | 前置 | 狀態 |
|-------|------|------|------|
| A-1 | Routing Confidence Gate | — | ❌ 待做 |
| A-2 | Answer Quality Judge | A-1 | ❌ 待做 |
| A-3 | Eval Regression Gate | 現有 eval | ❌ 待做 |
| A-4 | Knowledge Gap Daily Summary | A-2 | ❌ 待做 |
| B-A-1 | Langfuse VoltAgent 接入 | — | ❌ 待做 |
| B-A-2 | Langfuse FastAPI trace | B-A-1 | ❌ 待做 |
| C-1 | Trace Analyzer | A-3, B-A-1 | ❌ 待做 |
| C-2 | Harness Improver | C-1 | ❌ 待做 |
| C-3 | Auto Apply | C-2, A-3 | ❌ 待做 |
| C-4 | Human Review UI | C-2 | ❌ 待做 |
| D | Event-Driven Loop | A-4 | ❌ 待做 |
| E | Multi-Model Gateway | — | ❌ 待做 |

### 依賴關係

```
A-1（Confidence Gate）
  └── A-2（Quality Judge）
        └── A-4（Knowledge Gap）
              └── D（Event-Driven）

現有 eval pipeline
  └── A-3（Regression Gate）
        └── C-1（Trace Analyzer）
              └── C-2（Harness Improver）
                    └── C-3（Auto Apply）

B-A-1（Langfuse VoltAgent）← 獨立，可先做
  └── B-A-2（Langfuse FastAPI）

E（Multi-Model Gateway）← 獨立，可與 A 並行
```

---

## Evaluation 框架

### 評估面向

| 面向 | 指標 | 目標 |
|------|------|------|
| Routing | routing accuracy | ≥ 90% |
| RAG Answer | eval score 1–4 | ≥ 3.5/4.0 |
| Latency | P50 / P95 | P50 < 10s, P95 < 30s |
| Knowledge Coverage | knowledge gap rate | score ≤ 2 < 5% |
| Prompt Stability | regression rate | 0 regression per release |

### Release Gate

進入下一 Phase 前必須通過：
- [ ] 當前 Phase eval 指標達標
- [ ] regression gate 通過（routing + RAG eval 不低於 baseline）
- [ ] 新功能有對應 Langfuse trace 驗證
