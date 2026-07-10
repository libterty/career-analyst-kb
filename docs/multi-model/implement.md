# Multi-Model — 實作計畫

**Author**: Albert
**Date**: 2026-07-09
**Status**: Planning
**關聯設計文件**: [design.md](./design.md)

---

## 前置條件

- Loop 2（Verification Loop）的 Answer Quality Judge 實作後，才能驗證多模型效益
- Langfuse observability 接入後，才能追蹤不同模型的 latency / 品質差異

---

## Phase A — Model Gateway 基礎（VoltAgent 側）

> **目標**：讓 routing 和 judge 改用小模型，RAG 生成維持 30B，降低整體 latency。

### A-1：建立 Model Gateway

- [ ] 新增 `services/voltagent-career/src/gateway/model-gateway.ts`

```typescript
import { createOpenAI } from "@ai-sdk/openai";

const ollama = createOpenAI({
  baseURL: process.env.OLLAMA_BASE_URL ?? "http://localhost:11434/v1",
  apiKey: "ollama",
});

const MODEL_MAP: Record<TaskType, LanguageModelV1> = {
  routing: ollama(process.env.ROUTING_MODEL ?? "qwen3:8b"),
  "rag-generate": ollama(process.env.GENERATE_MODEL ?? "qwen3-30b-a3b"),
  judge: ollama(process.env.JUDGE_MODEL ?? "qwen3:8b"),
  resume: ollama(process.env.RESUME_MODEL ?? "qwen3:14b"),
  interview: ollama(process.env.INTERVIEW_MODEL ?? "qwen3:14b"),
};

export function getModel(task: TaskType): LanguageModelV1 {
  return MODEL_MAP[task];
}
```

### A-2：更新 config.ts

- [ ] 新增環境變數：`ROUTING_MODEL`, `GENERATE_MODEL`, `JUDGE_MODEL`, `RESUME_MODEL`, `INTERVIEW_MODEL`
- [ ] 更新 `.env.example` 加上上述變數與預設值

### A-3：更新 Supervisor 使用 routing model

- [ ] `src/agents/supervisor.ts`：路由 LLM 改用 `getModel("routing")`
- [ ] `src/middleware/routing-classifier.ts`：confidence 計算改用 `getModel("routing")`

### A-4：更新 Judge 使用 judge model

- [ ] `src/judges/answer-quality.ts`：評分改用 `getModel("judge")`

### A-5：更新 Resume/Interview agents

- [ ] `src/agents/resume.ts`：改用 `getModel("resume")`
- [ ] `src/agents/interview.ts`：改用 `getModel("interview")`

**完成條件**：
- [ ] `npm run build` 通過
- [ ] 用 routing task 問一個問題，trace 顯示 supervisor 用了 qwen3:8b，sub-agent 用了對應模型
- [ ] routing latency 明顯低於 30B 時期

---

## Phase B — FastAPI 側多模型支援

> **目標**：RAG 生成模型可透過 env var 或 request header 切換。

- [ ] `services/kb-api/src/rag/generator.py`：讀取 `GENERATE_MODEL` env var
- [ ] `services/kb-api/src/api/routers/chat.py`：接受 `X-Model` header，若有則 override env var
- [ ] 更新 `docker/docker-compose.yml`：加入 `GENERATE_MODEL` 環境變數

**完成條件**：可透過環境變數切換 RAG 生成模型，不需重啟 container

---

## Phase C — Cloud Fallback（選擇性）

> **觸發條件**：本機 Ollama 掛掉或 GPU 過熱時自動 fallback。

- [ ] Model Gateway 加 `withFallback(task: TaskType)`
  - 先呼叫本機 Ollama，timeout 120s → fallback Anthropic claude-haiku
- [ ] 環境變數：`ANTHROPIC_API_KEY`, `FALLBACK_MODEL=claude-haiku-4-5-20251001`
- [ ] fallback 事件寫入 Langfuse trace metadata（`model_fallback: true, fallback_reason: "timeout"`）
- [ ] 更新 `.env.example`

**完成條件**：手動 kill Ollama → VoltAgent fallback 到 Anthropic API，Langfuse 有 fallback trace

---

## Phase D — SFT 模型整合（未來）

**前置**：
1. Loop 2 完整運作（quality judge 收集到足夠 negative examples）
2. sft_seeds.jsonl 擴充至 500+ 筆

### D-1：SFT 資料準備

- [ ] 從 golden_dataset.jsonl + knowledge_gaps + high-quality traces 生成 SFT 訓練集
- [ ] 格式：`{ "instruction": "...", "input": "...", "output": "..." }`
- [ ] 目標：500+ 筆涵蓋 resume/interview/salary/career-plan 四個 domain

### D-2：LoRA Fine-tune

- [ ] 基底：qwen3:8b（本機 fine-tune 資源需求低）
- [ ] 框架：Unsloth / LLaMA-Factory（本機 GPU fine-tune）
- [ ] 輸出：`models/career-routing-v1`（Ollama modelfile）

### D-3：SFT 模型評估

- [ ] 跑 routing_eval.py + rag_eval.py 比對：qwen3:8b vs career-routing-v1
- [ ] regression gate 通過（routing accuracy ≥ baseline）後才進 Model Gateway

### D-4：Model Gateway 加入 SFT 模型

- [ ] `MODEL_MAP.routing = ollama("career-routing-v1")` 或透過 env var 切換
- [ ] Langfuse 追蹤 SFT vs base model 的 eval 差異

---

## 驗收條件

### Phase A 完成

| 指標 | 目標 |
|------|------|
| Routing P50 latency | < 5s（原 30B 約 10–15s） |
| Routing P95 latency | < 10s |
| RAG answer quality | 維持 ≥ 3.00/4.0 |
| Build | `npm run build` 通過 |

### Phase B 完成

| 指標 | 目標 |
|------|------|
| 切換 RAG model | `GENERATE_MODEL=qwen3:14b docker compose restart kb-api` 生效 |
| RAG eval @ qwen3:14b | ≥ 2.8/4.0（可接受的 regression） |
