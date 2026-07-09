# Multi-Model Design — Career Analyst KB

**Author**: Albert
**Date**: 2026-07-09
**Status**: Draft

---

## 1. 背景

Career Analyst KB 目前所有 LLM 呼叫均使用同一個模型（Ollama qwen3-30b-a3b），不論是 supervisor routing、RAG answer generation、answer quality judge、還是 resume analysis，全部走同一個 endpoint。

### 現況問題

| 問題 | 影響 |
|------|------|
| 所有任務用同一個 30B 模型 | P95 latency 71s，routing 等簡單任務耗時與 RAG 生成相同 |
| Judge 任務用 30B | Judge 只需 7B 即可，浪費資源 |
| 無法按任務複雜度選模型 | 簡單分類 vs 複雜推理 vs 多語言 RAG 無差異化 |
| 本機 Ollama 無法同時跑多個大模型 | qwen3-30b-a3b + embedding 已接近記憶體極限 |

---

## 2. 目標

建立 Model Gateway，依任務類型自動選擇最適合的模型：

- 快速 routing / classification → 小模型（7B），低 latency
- RAG 答案生成 → 中型模型（14B–30B），高品質
- Answer Quality Judge → 小模型（7B），成本低
- Resume/Document 分析 → 中型 vision 模型（支援文字密集輸入）
- Fine-tuned 推論（未來）→ SFT 後的 career-specific 模型

---

## 3. 模型分工設計

### 3.1 任務 → 模型映射

| 任務 | 模型 | 理由 |
|------|------|------|
| Supervisor routing 分類 | `qwen3:8b`（本機）| 路由只需指令跟隨，7–8B 足夠 |
| RAG 答案生成 | `qwen3-30b-a3b`（本機）| 需深度推理 + 長 context 整合 |
| Answer Quality Judge | `qwen3:8b`（本機）| 評分只需 1–4 分類，7–8B 夠 |
| Resume 結構化分析 | `qwen3:14b`（本機）| 需結構化輸出，平衡速度/品質 |
| Interview 問題生成 | `qwen3:14b`（本機）| 需創意 + 領域知識，14B 適中 |
| Embedding | `bge-m3`（本機 Ollama）| 多語言 embedding，維持不動 |

### 3.2 Cloud Fallback（可選）

| 情境 | 模型 | 觸發條件 |
|------|------|---------|
| 本機 Ollama 無回應 | `claude-haiku-4-5`（Anthropic API）| timeout > 120s |
| 高品質 resume 分析 | `claude-sonnet-4-6`（Anthropic API）| 使用者明確要求 |
| 緊急 production fallback | `claude-haiku-4-5` | 本機 GPU 掛掉 |

---

## 4. 架構：Model Gateway

```
VoltAgent Agent
    │
    ▼
Model Gateway (src/gateway/model-gateway.ts)
    │
    ├── task: "routing"       → qwen3:8b  (Ollama)
    ├── task: "rag-generate"  → qwen3-30b-a3b (Ollama)
    ├── task: "judge"         → qwen3:8b  (Ollama)
    ├── task: "resume"        → qwen3:14b (Ollama)
    ├── task: "interview"     → qwen3:14b (Ollama)
    └── [fallback]            → claude-haiku-4-5 (Anthropic API)
```

### Model Gateway Interface

```typescript
type TaskType =
  | "routing"
  | "rag-generate"
  | "judge"
  | "resume"
  | "interview";

interface ModelGateway {
  getProvider(task: TaskType): LanguageModelV1;
  withFallback(task: TaskType): LanguageModelV1;
}
```

---

## 5. Ollama 多模型並行限制

本機 Ollama 同一時間只能載入一個大模型到 GPU memory。

### 解法

1. **冷啟動接受**：不同任務按序執行，模型按需 load（Ollama 自動管理 LRU 換出）
2. **Router 優先**：routing 用的 qwen3:8b 常駐記憶體，生成再 swap 到 30B
3. **Judge 非同步**：judge 評分在 RAG 回傳後背景執行，不阻塞 user response

### 記憶體估算（假設 M-series Mac，64GB 統一記憶體）

| 模型 | VRAM 估算 |
|------|---------|
| qwen3:8b (Q4) | ~5GB |
| qwen3:14b (Q4) | ~9GB |
| qwen3-30b-a3b (Q4) | ~20GB |
| bge-m3 (embedding) | ~1.5GB |
| 系統 + OS | ~8GB |
| **合計（最大同時）** | ~29GB（30B + bge-m3 + OS）|

---

## 6. 未來：Fine-tuned 模型整合

現有 `eval/sft_seeds.jsonl` 已有 SFT 種子資料，可作為以下基礎：

### SFT 路線圖

| 階段 | 說明 |
|------|------|
| SFT-1 | 補齊 sft_seeds.jsonl 至 500+ 筆（covering resume/interview/salary/career） |
| SFT-2 | 基於 qwen3:8b 做 LoRA fine-tune（career domain routing + answer quality） |
| SFT-3 | 評估 SFT 模型 vs 原始 qwen3:8b 的 routing accuracy 差異 |
| SFT-4 | SFT 模型通過 regression gate 後，進 Model Gateway 為 `career-routing-ft` |

**前置條件**：Phase A eval pipeline（Loop 2）建立後，才能做 SFT 品質評估。

---

## 7. 實作計畫

### Phase A：Model Gateway 基礎

- [ ] `src/gateway/model-gateway.ts`：task → model 映射表
- [ ] 更新 `src/config.ts`：各 task 的 model name 可由 env var 覆蓋
- [ ] 更新 `src/agents/supervisor.ts`：routing 使用 `model-gateway.getProvider("routing")`
- [ ] 更新 `src/judges/answer-quality.ts`：judge 使用 `model-gateway.getProvider("judge")`

### Phase B：FastAPI 側多模型

- [ ] `services/kb-api/src/rag/generator.py`：支援 `GENERATE_MODEL` env var 切換
- [ ] `services/kb-api/src/application/services/chat_service.py`：可在 request 層傳入 model hint

### Phase C：Cloud Fallback

- [ ] Model Gateway 加 fallback logic：Ollama timeout → Anthropic API
- [ ] 環境變數：`ANTHROPIC_API_KEY`、`FALLBACK_MODEL=claude-haiku-4-5-20251001`
- [ ] fallback 事件寫入 Langfuse trace metadata（`model_fallback: true`）

---

## 8. 關鍵決策

| 決策 | 選擇 | 理由 |
|------|------|------|
| 主要 provider | 本機 Ollama | 零成本，適合個人專案 |
| Routing 模型 | qwen3:8b | 指令跟隨夠用，latency < 5s |
| RAG 生成模型 | qwen3-30b-a3b | 現有最佳 RAG eval 3.00/4.0 |
| Judge 模型 | qwen3:8b | 評分任務簡單，不需 30B |
| Fallback provider | Anthropic API（claude-haiku） | 可靠性保證，僅在本機掛掉時啟用 |
| SFT 基底 | qwen3:8b | 小模型 LoRA 資源需求低，適合本機 fine-tune |
