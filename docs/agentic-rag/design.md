# Agentic RAG 強化設計文件

**Author**: Albert
**Date**: 2026-07-19
**Branch**: feat/agentic-rag
**Status**: Draft

---

## 1. 背景

### 現況架構

```
[使用者]
   │
   ▼
[VoltAgent SupervisorAgent]
   ├─ routing-classifier (fastModel)   — 意圖分類
   ├─ confidence-gate                  — 低信心 fallback
   ├─ sub-agents: resume / interview / career-plan / salary / web-search
   └─ answer-quality-gate (judgeModel) — 品質評分 + knowledge gap 記錄
         │
         ▼ queryCareerKBTool
[KB API RAGPipeline]
   ├─ PromptOptimizer.enhance_query()  — 術語正規化
   ├─ HybridSearchEngine               — Dense (Milvus) + BM25 + RRF
   └─ LLM 串流生成 (ConversationBufferWindowMemory)
```

### 現況問題（Agentic RAG 視角）

| 問題 | 現象 | 根因 |
|------|------|------|
| 被動 Retrieve | 不管 chunk 相不相關都送進 LLM | RAG pipeline 無 relevance check |
| 單次查詢 | 複合問題（轉職+薪資談判）靠一次 hybrid search 覆蓋 | 無 query decomposition |
| 無自我修正 | 相關 chunk 不足時 LLM 直接幻覺 | 無 iterative retrieval |
| 稀疏主題 fallback | 主管管理、職場相處走 WebSearch | KB 資料缺口 + 無補撈機制 |

---

## 2. 設計目標

1. **Self-Reflection Loop** — RAG pipeline 內部自我評估 chunk 相關性，不足時改寫 query 再 retrieve（最多 2 輪，避免 latency 爆炸）
2. **Query Decomposition** — VoltAgent 層對複合問題拆成 sub-questions，各自 retrieve 後合併
3. **Local LLM Only** — 沿用現有 model-gateway，不引入 cloud model
4. **向後相容** — 現有 `/api/chat/query/sync` endpoint 行為不變，新功能以 opt-in 方式加入

---

## 3. 新架構

```
[使用者]
   │
   ▼
[VoltAgent SupervisorAgent]
   ├─ routing-classifier (fastModel)
   ├─ confidence-gate
   ├─ ★ QueryDecomposer (fastModel)    — 新增：複合問題拆 sub-questions
   ├─ sub-agents（同現有）
   │     └─ ★ 各 sub-agent 可帶 sub_questions 參數呼叫 queryCareerKBTool
   └─ answer-quality-gate
         │
         ▼ queryCareerKBTool（帶 sub_questions 欄位）
[KB API AgenticRAGPipeline]            — 新增：取代現有 RAGPipeline
   ├─ PromptOptimizer.enhance_query()
   │
   ├─ ★ RelevanceChecker (fastLLM)    — 新增：評估 chunk 是否能回答問題
   │
   ├─ [Iteration Loop, max=2]
   │   ├─ HybridSearchEngine
   │   ├─ RelevanceChecker.check()
   │   │   ├─ SUFFICIENT  → 進 LLM 生成
   │   │   └─ INSUFFICIENT → QueryRewriter.rewrite() → 下一輪
   │   └─ [逾時 fallback] → 直接用現有 chunk 生成
   │
   └─ LLM 串流生成 + 在回應 metadata 中帶 retrieval_iterations
```

---

## 4. 新增元件詳細設計

### 4.1 RelevanceChecker（Python, KB API）

**位置**：`services/kb-api/src/rag/relevance_checker.py`

**職責**：給定問題和 chunk 列表，判斷是否足以回答問題。

**LLM**：`fastLLM`（對應 `FAST_MODEL`，預設 `qwen3:4b`）。輕量判斷，不需要 reasoning heavy model。

**輸出格式**（structured output）：
```python
class RelevanceResult:
    sufficient: bool          # chunk 能否回答問題
    missing_aspects: list[str]  # 不足的面向（用於 QueryRewriter）
    confidence: float         # 0.0–1.0
```

**判斷邏輯**：
- `sufficient=True` 條件：chunk 覆蓋問題的核心面向，無明顯缺漏
- `sufficient=False` 觸發條件：chunk 全部是泛論、問題問的具體場景 chunk 一個都沒有、或 chunk 數 < 3

**prompt 設計**：
```
你是一位 RAG 系統品質評估員。
問題：{question}
以下是從知識庫檢索到的段落（共 {n} 段）：
{chunks_summary}   ← 每段只取前 80 字，避免 context 過長

判斷這些段落是否足以回答上述問題。
若不足，列出缺少哪些面向。
```

---

### 4.2 QueryRewriter（Python, KB API）

**位置**：`services/kb-api/src/rag/query_rewriter.py`

**職責**：根據 RelevanceChecker 回傳的 `missing_aspects`，改寫查詢以補撈缺漏段落。

**LLM**：`fastLLM`（`qwen3:4b`）。

**改寫策略**：
- 原始問題 + missing_aspects → 新查詢
- 範例：原問題「怎麼和主管建立信任？」，missing_aspects=["具體行動步驟", "新人場景"]
  → 改寫為「新進員工如何透過具體行動建立與主管的信任關係」

**保護機制**：改寫後的 query 與原 query 相似度 > 0.85（cosine）則跳過，避免無效迴圈。

---

### 4.3 AgenticRAGPipeline（Python, KB API）

**位置**：`services/kb-api/src/rag/agentic_pipeline.py`

**職責**：封裝 Self-Reflection Loop，對外介面與現有 `RAGPipeline.query()` 相同（AsyncIterator[str]）。

**迭代流程**：
```python
MAX_ITERATIONS = 2

async def query(question, session_id):
    enhanced = enhance_query(question)
    embedding = embed(enhanced)

    for iteration in range(MAX_ITERATIONS):
        chunks = hybrid_search(enhanced, embedding)
        relevance = relevance_checker.check(question, chunks)

        if relevance.sufficient or iteration == MAX_ITERATIONS - 1:
            break  # 夠用，或已達上限

        # 不夠：改寫 query，下一輪
        enhanced = query_rewriter.rewrite(question, relevance.missing_aspects)
        embedding = embed(enhanced)

    # 串流生成，metadata 帶 retrieval_iterations
    async for token in llm_stream(chunks, question, iteration+1):
        yield token
```

**Latency 估算**（local LLM）：
- 第 0 輪 relevance check：fastLLM (qwen3:4b) ≈ 3-5 秒
- 第 1 輪（若觸發）：rewrite + search + check ≈ 5-8 秒
- 額外總開銷：≤ 13 秒（只在不足時觸發）

---

### 4.4 QueryDecomposer（TypeScript, VoltAgent）

**位置**：`services/voltagent-career/src/middleware/query-decomposer.ts`

**職責**：在 supervisor input middleware 層，判斷問題是否為複合問題，若是則拆成 sub-questions 注入 context。

**LLM**：`fastModel`（`qwen3:4b`）。

**觸發條件**（以下任一）：
- 問題包含「而且」「另外」「同時」「還有」等並列詞
- 問題長度 > 80 字
- routing-classifier 回傳 `agent: "direct"`（意圖不明確，可能是複合）

**不觸發條件**：
- 問題已被 routing-classifier 明確分類（confidence > 0.8）且長度 < 60 字

**輸出**：在 context 中注入 `sub_questions: string[]`，supervisor 帶著這個 context 依序呼叫各 agent 或 queryCareerKBTool。

---

### 4.5 model-gateway 新增 fastLLM（Python）

**位置**：`services/kb-api/src/core/llm_factory.py`

新增 `build_fast_llm()` function，對應 `FAST_MODEL` env var（預設 `qwen3:4b`）。RelevanceChecker 和 QueryRewriter 都使用這個 model。

---

## 5. LLM 分工

| 元件 | 模型 | 理由 |
|------|------|------|
| Supervisor orchestration | `gemma3:12b` | 需要 heavy reasoning 做多 agent 路由 |
| Sub-agents | `gemma3:12b` | 領域推理 |
| **RelevanceChecker** | `qwen3:4b` | 是/否判斷，不需要大模型 |
| **QueryRewriter** | `qwen3:4b` | 短 query 改寫，輕量 |
| **QueryDecomposer** | `qwen3:4b` | 問題拆解，structured output |
| Answer quality judge | `qwen3:8b` | 品質評分需要稍強的判斷力 |
| routing-classifier | `qwen3:4b` | intent detection |

---

## 6. API 介面變更

### `/api/chat/query/sync`（現有，擴充 response）

```json
{
  "answer": "...",
  "sources": [...],
  "retrieval_iterations": 1,      // 新增：實際執行了幾輪 retrieve
  "relevance_sufficient": true    // 新增：最終 relevance check 結果
}
```

request body 新增 optional 欄位：
```json
{
  "question": "...",
  "session_id": "...",
  "language": "zh-TW",
  "agentic": true,              // 新增：true 使用 AgenticRAGPipeline，false 沿用舊版
  "sub_questions": ["...", "..."]  // 新增：由 QueryDecomposer 注入
}
```

`agentic` 預設為 `false`，讓現有呼叫端（kb-web 直連）不受影響，VoltAgent 側設為 `true`。

---

## 7. 不做的事

- **Graph RAG**：職涯建議型內容無強實體關係，投資報酬率低
- **無限迭代**：上限 2 輪，防止 local LLM latency 堆疊
- **改變 kb-web 呼叫方式**：kb-web 走 VoltAgent，不直連 KB API，此次不動 kb-web

---

## 8. 成功指標

| 指標 | 現況 | 目標 |
|------|------|------|
| RAG eval score (golden dataset) | 3.0/4.0 | ≥ 3.3/4.0 |
| knowledge gap rate (score ≤ 2) | 待測量 | 降低 20% |
| retrieval_iterations = 2 比例 | N/A | < 30%（大部分一輪夠） |
| 稀疏主題回答完整性（主管管理）| WebSearch fallback | KB 能直接回答 |
