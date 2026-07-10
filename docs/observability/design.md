# Observability Design — Career Analyst KB × Langfuse

**Author**: Albert
**Date**: 2026-07-09
**Status**: Draft

---

## 1. 背景

Career Analyst KB 目前缺乏跨層可觀測性：

- VoltAgent supervisor 路由決策、sub-agent 呼叫、RAG tool invoke，只有 `console.log` 散落各處
- FastAPI RAG 層（embedding、Milvus 查詢、LLM 生成）完全沒有 trace
- rag_eval.py / routing_eval.py 結果只存 JSON 檔，無法跨 request 串聯
- eval score 與 prompt 版本無關聯，hill climbing 改版後效果是黑箱

### 現況問題

| 問題 | 影響 |
|------|------|
| 無法追蹤單一 user question 的完整鏈路 | debug routing 失敗、answer 不佳困難 |
| LLM call latency 無法追蹤 | 不知道哪個 agent 最慢（qwen3-30b-a3b P95 ~71s） |
| Answer Quality Judge 評分只記 JSON | 無法在同一視角與 routing 對照 |
| Prompt 版本與 eval 結果無法關聯 | 不知道哪版 prompt 改善了哪些問題 |

---

## 2. 技術選型

| 比較項目 | LangSmith | Langfuse |
|---------|-----------|---------|
| Free tier | 5K traces/月 | 50K units/月 |
| 付費最低 | $39/seat/月 | $29/月（無限 user） |
| Self-host | ❌ | ✅ MIT 授權完全免費 |
| VoltAgent 整合 | 手動 SDK wrap | ✅ 官方 `@voltagent/langfuse-exporter` |
| Prompt 版本管理 | ✅ Prompt Hub | ✅ Prompt Management |
| Dataset / Eval | ✅ | ✅ |

**決定：VoltAgent + Langfuse**

理由：官方原生整合（`@voltagent/langfuse-exporter`），self-host 零費用，Free tier 是 LangSmith 的 10 倍，功能對等。

---

## 3. 目標

整合 Langfuse，在不改動現有業務邏輯的前提下，讓以下可觀測：

1. **端到端 trace**：user question → supervisor routing → sub-agent → RAG tool → LLM → answer
2. **Latency tracking**：每個 agent 的 P50/P95，對應 `latency_bench.py` 現有指標
3. **Eval 關聯**：Answer Quality Judge score、Confidence Gate 結果附在同一 trace
4. **Prompt 版本追蹤**：每次 supervisor prompt 更新後，eval 結果可與版本對齊
5. **Dataset 管理**：golden_dataset.jsonl（879 筆）可在 Langfuse 管理與擴充

---

## 4. 架構

```
User question
    │
    ▼
VoltAgent SupervisorAgent
    │  @voltagent/langfuse-exporter (telemetryExporter)
    ├── Confidence Gate (child span + confidence metadata)
    ├── sub-agent call (child trace)
    │       ├── queryCareerKB tool (child span)
    │       │       └── FastAPI RAG  ← langfuse-python wrap
    │       │             ├── embedding span
    │       │             ├── Milvus search span
    │       │             └── LLM generate span (qwen3-30b-a3b)
    │       └── Answer Quality Judge (child span, score as metadata)
    └── knowledge gap reporting (fire-and-forget, not traced)
    │
    ▼
Langfuse Project: career-analyst-kb
    ├── Traces — 完整鏈路
    ├── Dashboard — latency / cost / error rate / agent routing distribution
    ├── Datasets — golden_dataset.jsonl 管理（routing + RAG eval）
    └── Prompts — supervisor prompt 版本
```

---

## 5. 實作計畫

### Phase A：VoltAgent 側接入

**目標**：每個 user request 自動產生一條完整的 Langfuse trace，零改動業務邏輯。

**套件**：`@voltagent/langfuse-exporter`

| 項目 | 檔案 | 說明 |
|------|------|------|
| A-1 | `src/tracing/langfuse-exporter.ts` | 初始化 `LangfuseExporter`，讀環境變數 |
| A-2 | `src/index.ts` | 將 exporter 傳入 VoltAgent `telemetryExporter` option |
| A-3 | `src/agents/supervisor.ts` | 在 `onFinish` hook 附上 routing result、agent name、judge score |
| A-4 | `src/middleware/confidence-gate.ts` | fallback 事件加 custom span metadata（confidence 值、fallback 原因） |
| A-5 | `src/judges/answer-quality.ts` | judge score 加進 span output metadata |

**環境變數**：
```bash
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com   # 或 self-host URL
```

**核心接入範例**：
```typescript
import { LangfuseExporter } from "@voltagent/langfuse-exporter";

const langfuseExporter = new LangfuseExporter({
  publicKey: process.env.LANGFUSE_PUBLIC_KEY,
  secretKey: process.env.LANGFUSE_SECRET_KEY,
  baseUrl: process.env.LANGFUSE_BASE_URL,
});

new VoltAgent({ telemetryExporter: langfuseExporter, ... });
```

---

### Phase B：FastAPI RAG 側 Python trace

**目標**：RAG 查詢鏈路（embedding → Milvus → LLM）成為 VoltAgent trace 的 child span。

**套件**：`langfuse` Python package（`@observe` decorator）

| 項目 | 檔案 | 說明 |
|------|------|------|
| B-1 | `services/kb-api/src/rag/retriever.py` | `@observe(name="rag-retrieve")` wrap，記錄 query / top-k / sources |
| B-2 | `services/kb-api/src/rag/generator.py` | `@observe(name="rag-generate")` wrap，記錄 model / tokens / latency |
| B-3 | `services/kb-api/src/api/routers/chat.py` | 接收 VoltAgent 傳來的 `langfuse-trace-id` header，attach 到 parent trace |

**跨服務串接**：
```python
# FastAPI 側接收 trace id
trace_id = request.headers.get("langfuse-trace-id")
if trace_id:
    langfuse.get_client().trace(id=trace_id)
```

---

### Phase C：Eval Dataset 遷移

**目標**：`eval/golden_dataset.jsonl` 遷移到 Langfuse Datasets，支援在 UI 新增/標記題目。

| 項目 | 說明 |
|------|------|
| C-1 | `eval/upload_to_langfuse.py`：將 golden_dataset.jsonl 上傳為 Langfuse Dataset |
| C-2 | `eval/routing_eval.py` 改為從 Langfuse Dataset 拉題目，結果回寫為 Dataset Run |
| C-3 | `eval/rag_eval.py` 同上，RAG eval 結果對應 Langfuse Dataset Run |

---

### Phase D：Prompt 版本管理

**目標**：Supervisor prompt 在 Langfuse Prompt Management 管理，每次 Hill Climbing 改版可回溯。

| 項目 | 說明 |
|------|------|
| D-1 | Supervisor system prompt 上傳到 Langfuse，版本號對齊 `// PROMPT_VERSION:` 註解 |
| D-2 | Hill Climbing auto-apply 後，push 新版本到 Langfuse Prompt Management |
| D-3 | harness-improver 改為從 Langfuse 取最新版 prompt，不直接讀 fs |

---

## 6. 關鍵決策

| 決策 | 選擇 | 理由 |
|------|------|------|
| Observability 平台 | Langfuse | 官方 VoltAgent exporter、self-host 免費、Free tier 50K units |
| Self-host vs Cloud | Cloud 先行 | 先驗證效果，有需要再切 self-host（MIT 授權，無鎖定風險） |
| 跨服務串接方式 | HTTP header propagation | 不引入 OpenTelemetry collector，最輕量 |
| Eval dataset 存放 | 雙軌（本地 jsonl + Langfuse） | 本地 jsonl 保留作 fallback；Langfuse 作為主要管理介面 |
| Phase 優先順序 | A → B → C → D | A 零改動業務邏輯就有完整 trace；B/C/D 逐步疊加 |

---

## 7. 預期效益

| 指標 | 現況 | 目標 |
|------|------|------|
| Debug 單一問題所需時間 | 翻 console.log | < 2 分鐘（Langfuse trace 直接展開） |
| Latency 可視化 | 只有 latency_bench.py 離線測 | 每個 request 即時 P50/P95 dashboard |
| Eval 回歸可視化 | 比對 JSON 檔 | Langfuse Dataset Run 圖表對比 |
| Prompt 版本可回溯 | git blame | Langfuse Prompt Management 版本歷史 |
| Agent routing 分佈 | 無 | Dashboard 即時查看 ResumeAgent/InterviewAgent/等 比例 |
