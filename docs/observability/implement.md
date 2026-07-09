# Observability — 實作計畫

**Author**: Albert
**Date**: 2026-07-09
**Status**: Planning
**關聯設計文件**: [design.md](./design.md)

---

## 前置條件

- Langfuse 帳號（cloud.langfuse.com）或 self-host instance
- `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` 環境變數

---

## Phase A — VoltAgent 接入（最優先）

> **目標**：零改動業務邏輯，每個 user request 自動產生完整 Langfuse trace。

### A-1：安裝套件

```bash
cd services/voltagent-career
npm install @voltagent/langfuse-exporter
```

### A-2：建立 Langfuse Exporter

- [ ] 新增 `services/voltagent-career/src/tracing/langfuse-exporter.ts`

```typescript
import { LangfuseExporter } from "@voltagent/langfuse-exporter";

export const langfuseExporter = new LangfuseExporter({
  publicKey: process.env.LANGFUSE_PUBLIC_KEY!,
  secretKey: process.env.LANGFUSE_SECRET_KEY!,
  baseUrl: process.env.LANGFUSE_BASE_URL ?? "https://cloud.langfuse.com",
});
```

### A-3：接入 VoltAgent 初始化

- [ ] 更新 `services/voltagent-career/src/index.ts`

```typescript
import { langfuseExporter } from "./tracing/langfuse-exporter";

new VoltAgent({
  agents: { supervisor },
  telemetryExporter: langfuseExporter,
});
```

### A-4：Supervisor onFinish Hook

- [ ] 更新 `src/agents/supervisor.ts`：在 `onFinish` 附上 routing metadata

```typescript
onFinish: async ({ output, metadata }) => {
  // 附上 routing result、agent name、confidence
  return {
    ...metadata,
    routing_agent: selectedAgent,
    routing_confidence: confidence,
    routing_fallback: isFallback,
  };
}
```

### A-5：更新環境變數

- [ ] 更新 `.env.example`：

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_BASE_URL=https://cloud.langfuse.com
```

- [ ] 更新 `docker/docker-compose.yml`：voltagent-career service 加上上述環境變數

**完成條件**：
- [ ] 發一個 question → Langfuse dashboard 出現對應 trace
- [ ] Trace 包含：supervisor routing → sub-agent → queryCareerKB tool
- [ ] `npm run build` 通過

---

## Phase B — FastAPI RAG trace

> **目標**：RAG 查詢（embedding → Milvus → LLM）成為 VoltAgent trace 的 child span。

### B-1：安裝套件

```bash
cd services/kb-api
pip install langfuse
```

### B-2：Retriever trace

- [ ] 更新 `services/kb-api/src/rag/retriever.py`

```python
from langfuse.decorators import observe

@observe(name="rag-retrieve")
async def retrieve(self, query: str, top_k: int = 10):
    # 現有邏輯不動
    ...
```

### B-3：Generator trace

- [ ] 更新 `services/kb-api/src/rag/generator.py`（或 llm_provider.py）

```python
@observe(name="rag-generate")
async def generate(self, prompt: str, context: str):
    ...
```

### B-4：跨服務 trace 串接

- [ ] 更新 `services/kb-api/src/api/routers/chat.py`：接收 `langfuse-trace-id` header

```python
trace_id = request.headers.get("langfuse-trace-id")
if trace_id:
    langfuse.get_client().trace(id=trace_id)
```

- [ ] 更新 `services/voltagent-career/src/tools/kb-client.ts`：發請求時帶 header

```typescript
headers: {
  "langfuse-trace-id": currentTraceId,
}
```

**完成條件**：
- [ ] Langfuse trace 展開後可看到 embedding span、Milvus search span、LLM generate span
- [ ] FastAPI latency 分布與 `latency_bench.py` 結果一致

---

## Phase C — Eval Dataset 遷移

> **目標**：golden_dataset.jsonl 在 Langfuse 管理，支援 UI 新增/標記。

### C-1：上傳 Dataset

- [ ] 新增 `eval/upload_to_langfuse.py`

```python
from langfuse import Langfuse
import json

client = Langfuse()
dataset = client.create_dataset(name="career-kb-golden-dataset")

with open("eval/golden_dataset.jsonl") as f:
    for line in f:
        item = json.loads(line)
        dataset.create_item(
            input={"query": item["query"]},
            expected_output={"answer": item.get("expected_answer", "")},
            metadata={"agent": item.get("agent"), "language": item.get("language")},
        )
```

### C-2：routing_eval.py 改用 Langfuse Dataset

- [ ] 更新 `eval/routing_eval.py`：從 Langfuse Dataset 拉題目，結果回寫為 Dataset Run
- [ ] 保留本地 jsonl 作 fallback（兩路並存）

### C-3：rag_eval.py 改用 Langfuse Dataset

- [ ] 同上，RAG eval 結果對應 Langfuse Dataset Run

**完成條件**：
- [ ] Langfuse Datasets 頁面可看到 career-kb-golden-dataset（含完整題目）
- [ ] 跑 routing_eval.py → Langfuse Dataset Runs 出現對應 run

---

## Phase D — Prompt 版本管理

> **目標**：Supervisor prompt 在 Langfuse 管理，每次改版可回溯。

### D-1：上傳 Supervisor Prompt

- [ ] 在 Langfuse Prompt Management 建立 `career-supervisor-prompt`
- [ ] 版本 1 = 現有 supervisor.ts 的 system instructions
- [ ] 在 `supervisor.ts` 加上版本標記：`// PROMPT_VERSION: 1`

### D-2：Hill Climbing 整合

- [ ] `hill-climbing/auto-apply.ts`：套用 diff 後，push 新版本到 Langfuse
- [ ] `hill-climbing/harness-improver.ts`：pull prompt 時從 Langfuse 取最新版

**完成條件**：
- [ ] 改一次 supervisor prompt → Langfuse 出現版本 2
- [ ] 可在 Langfuse 比對版本 1 vs 版本 2 的 eval 結果差異

---

## Langfuse Dashboard 設定（一次性）

部署後手動設定：

1. **Traces** tab：確認每個 request 有完整 trace
2. **Dashboard**：建立以下 panels
   - Agent routing 分佈（ResumeAgent / InterviewAgent / CareerPlanAgent / SalaryAgent / Fallback）
   - 平均 latency per agent
   - Answer Quality Judge score 分佈（1–4）
   - Confidence Gate fallback rate
3. **Datasets**：建立 `career-kb-golden-dataset`（Phase C 後自動有）
4. **Prompts**：建立 `career-supervisor-prompt`（Phase D 後自動有）

---

## 驗收條件

| Phase | 完成條件 |
|-------|---------|
| A | Langfuse trace 有 supervisor + sub-agent + tool call 完整鏈路 |
| B | RAG trace 含 embedding、Milvus、LLM span，與 VoltAgent trace 串接 |
| C | golden_dataset 在 Langfuse 管理，eval run 有歷史記錄 |
| D | Supervisor prompt 版本歷史可回溯，eval 結果與版本對齊 |
