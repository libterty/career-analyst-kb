# Agentic RAG 強化實作計畫

**Author**: Albert
**Date**: 2026-07-19
**Branch**: feat/agentic-rag
**Design Doc**: [design.md](./design.md)

---

## 總覽

三個 Phase，各自獨立可測試，按順序實作。

```
Phase 1 — Self-Reflection Loop（KB API，Python）
Phase 2 — AgenticRAGPipeline 串接（KB API，Python）
Phase 3 — QueryDecomposer（VoltAgent，TypeScript）
```

---

## Phase 1：Self-Reflection Loop（KB API）

**目標**：在 KB API 內建立 relevance check + query rewrite 能力，尚未接入 pipeline。

### 1-1 新增 `build_fast_llm()`

**檔案**：`services/kb-api/src/core/llm_factory.py`

新增 `build_fast_llm()` function，讀取 `FAST_MODEL` env var（預設 `qwen3:4b`），`streaming=False`（RelevanceChecker 需要 structured output，不需串流）。

### 1-2 新增 `RelevanceChecker`

**新檔案**：`services/kb-api/src/rag/relevance_checker.py`

```python
@dataclass(frozen=True)
class RelevanceResult:
    sufficient: bool
    missing_aspects: list[str]
    confidence: float

class RelevanceChecker:
    def __init__(self, llm): ...
    def check(self, question: str, chunks: list[SearchResult]) -> RelevanceResult: ...
```

實作細節：
- 每個 chunk 只取前 80 字組成 `chunks_summary`，避免 prompt 過長
- 用 `with_structured_output(RelevanceResultSchema)` 取得結構化輸出
- 若 LLM 呼叫失敗，fallback 回傳 `sufficient=True`（不阻斷流程）
- chunk 數 < 2 時直接回傳 `sufficient=False, missing_aspects=["相關段落不足"]`

### 1-3 新增 `QueryRewriter`

**新檔案**：`services/kb-api/src/rag/query_rewriter.py`

```python
class QueryRewriter:
    def __init__(self, llm, embedder): ...
    def rewrite(self, original: str, missing_aspects: list[str]) -> str: ...
```

實作細節：
- 改寫後計算與原 query embedding cosine similarity，> 0.85 則回傳原 query（避免無效迴圈）
- prompt 限制改寫結果在 50 字內（針對中文職涯場景）
- 若 LLM 呼叫失敗，fallback 回傳原 query

### 1-4 單元測試

**新檔案**：`services/kb-api/tests/rag/test_relevance_checker.py`
**新檔案**：`services/kb-api/tests/rag/test_query_rewriter.py`

測試策略：mock LLM，測試各分支（sufficient/insufficient、fallback、cosine 保護）。

### Phase 1 完成標準

- [ ] `RelevanceChecker.check()` 在 mock LLM 下正確回傳 sufficient/insufficient
- [ ] `QueryRewriter.rewrite()` cosine 保護邏輯通過測試
- [ ] `build_fast_llm()` 讀取 `FAST_MODEL` env var

---

## Phase 2：AgenticRAGPipeline 串接（KB API）

**目標**：新增 `AgenticRAGPipeline`，串接 Self-Reflection Loop，並暴露 `agentic=true` API 選項。

### 2-1 新增 `AgenticRAGPipeline`

**新檔案**：`services/kb-api/src/rag/agentic_pipeline.py`

```python
class AgenticRAGPipeline:
    MAX_ITERATIONS = 2

    def __init__(self, milvus_host, milvus_port, llm_model, fast_llm_model, memory_window=10): ...

    async def query(
        self,
        question: str,
        session_id: str = "default",
        sub_questions: list[str] | None = None,
    ) -> AsyncIterator[str]:
        """
        sub_questions 若有值，依序 retrieve 每個 sub-question，
        合併 chunk pool 後再進入 self-reflection loop。
        """
        ...

    def _retrieve_with_reflection(self, question: str) -> tuple[str, list[SearchResult], int]:
        """
        回傳 (context, results, iterations_used)
        """
        ...
```

`AgenticRAGPipeline` 不繼承 `RAGPipeline`，獨立實作（避免耦合），但共用 `HybridSearchEngine`、`EmbeddingService`、`build_llm()`。

### 2-2 `dependencies.py` 新增 `get_agentic_chat_service()`

**檔案**：`services/kb-api/src/api/dependencies.py`

新增 singleton factory，類比現有 `get_chat_service()`，回傳 `AgenticRAGPipeline` 實例。

### 2-3 chat router 擴充

**檔案**：`services/kb-api/src/api/routers/chat.py`

在 `POST /api/chat/query/sync` 的 request body 加入：
```python
class QueryRequest(BaseModel):
    question: str
    session_id: str = "voltagent-default"
    language: str = "zh-TW"
    topic: str | None = None
    agentic: bool = False          # 新增
    sub_questions: list[str] = []  # 新增
```

response body 加入：
```python
class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    retrieval_iterations: int = 1     # 新增
    relevance_sufficient: bool = True # 新增
```

路由邏輯：
```python
if request.agentic:
    pipeline = get_agentic_chat_service()
else:
    pipeline = get_chat_service()
```

### 2-4 整合測試

**新檔案**：`services/kb-api/tests/api/test_agentic_query.py`

- mock Milvus + mock LLM，驗證 `agentic=true` 回應帶 `retrieval_iterations`
- 驗證 `agentic=false` 行為與現有一致（regression）

### 2-5 `kb-client.ts` 更新（VoltAgent）

**檔案**：`services/voltagent-career/src/tools/kb-client.ts`

`fetchCareerKB()` request body 加入 `agentic: true`，讓 VoltAgent 所有查詢走 Agentic pipeline。

response 型別加入 `retrieval_iterations?: number`（optional，向後相容舊 API 版本）。

### Phase 2 完成標準

- [ ] `POST /api/chat/query/sync` 加 `agentic=true` 回應帶 `retrieval_iterations`
- [ ] `agentic=false`（或不帶）的呼叫行為與現有完全一致（regression test pass）
- [ ] iteration 上限 2 不會超過
- [ ] LLM 呼叫失敗時 fallback 不阻斷串流

---

## Phase 3：QueryDecomposer（VoltAgent）

**目標**：在 supervisor 輸入層加入複合問題拆解，讓各 sub-agent 能針對性 retrieve。

### 3-1 新增 `QueryDecomposer`

**新檔案**：`services/voltagent-career/src/middleware/query-decomposer.ts`

```typescript
export type DecomposedQuery = {
  isComplex: boolean;
  subQuestions: string[];  // 若 isComplex=false，為空陣列
};

export async function decomposeQuery(query: string): Promise<DecomposedQuery>
```

觸發條件（AND 邏輯）：
- `isComplex=true` 需要同時滿足：長度 > 80 字 **或** 包含並列詞（而且/另外/同時/還有/但是...同時）
- routing-classifier confidence < 0.75（問題跨域）

不觸發（回傳 `isComplex=false`）：
- routing-classifier confidence ≥ 0.75
- query 長度 ≤ 30 字

structured output schema：
```typescript
const schema = z.object({
  isComplex: z.boolean(),
  subQuestions: z.array(z.string()).max(3),  // 最多拆 3 個
  reason: z.string(),
});
```

### 3-2 整合進 supervisor input middleware

**檔案**：`services/voltagent-career/src/agents/supervisor.ts`

在 `inputMiddlewares` 加入 `queryDecomposer`（順序：guardrail → queryDecomposer → confidenceGate）。

middleware 行為：若 `isComplex=true`，在 user message 後附加：
```
[系統：此問題已拆解為以下 sub-questions，請依序處理：
1. {subQ1}
2. {subQ2}
並整合成一個完整回答。]
```

sub-questions 也透過 `queryCareerKBTool` 的 `question` 參數傳遞，讓各 sub-question 獨立 retrieve。

### 3-3 `queryCareerKBTool` 擴充

**檔案**：`services/voltagent-career/src/tools/query-career-kb.ts`

parameters 加入 optional `subQuestions` 欄位，傳到 `fetchCareerKB` 的 `sub_questions` 陣列。

### 3-4 單元測試

**新檔案**：`services/voltagent-career/src/middleware/__tests__/query-decomposer.test.ts`

測試：觸發條件判斷、max 3 sub-questions 限制、mock LLM structured output。

### Phase 3 完成標準

- [ ] 複合問題（> 80 字且跨域）被拆成 ≤ 3 個 sub-questions
- [ ] 簡單問題不觸發（isComplex=false），無額外 latency
- [ ] supervisor 接到 sub-questions 後依序 retrieve 並整合回答

---

## 跨 Phase 風險與對策

| 風險 | 可能性 | 對策 |
|------|--------|------|
| RelevanceChecker latency 過高（qwen3:4b 本地 > 10s） | 中 | 設 5s timeout，逾時直接視為 sufficient；iteration 2 不再做 check |
| QueryRewriter 改寫後 query 跑偏，召回更差 | 低 | cosine similarity 保護（> 0.85 不改寫）|
| AgenticPipeline structured output 解析失敗 | 低 | fallback sufficient=True，不阻斷 |
| Phase 3 QueryDecomposer 把簡單問題拆爛 | 中 | 觸發條件保守（AND 邏輯），先上線觀察 Langfuse trace |

---

## 實作順序總結

```
Week 1
  ├─ Phase 1：RelevanceChecker + QueryRewriter + 單元測試
  └─ Phase 2（前半）：AgenticRAGPipeline + dependencies

Week 2
  ├─ Phase 2（後半）：chat router 擴充 + 整合測試 + kb-client.ts 更新
  └─ Phase 3：QueryDecomposer + supervisor 整合 + 測試

驗收
  └─ 跑 eval/rag_eval.py 對比 baseline，確認 score ≥ 3.3/4.0
```

---

## 檔案異動清單

### KB API（Python）

| 動作 | 檔案 |
|------|------|
| 修改 | `src/core/llm_factory.py` — 新增 `build_fast_llm()` |
| 新增 | `src/rag/relevance_checker.py` |
| 新增 | `src/rag/query_rewriter.py` |
| 新增 | `src/rag/agentic_pipeline.py` |
| 修改 | `src/api/dependencies.py` — 新增 `get_agentic_chat_service()` |
| 修改 | `src/api/routers/chat.py` — 擴充 request/response schema |
| 新增 | `tests/rag/test_relevance_checker.py` |
| 新增 | `tests/rag/test_query_rewriter.py` |
| 新增 | `tests/api/test_agentic_query.py` |

### VoltAgent（TypeScript）

| 動作 | 檔案 |
|------|------|
| 新增 | `src/middleware/query-decomposer.ts` |
| 修改 | `src/agents/supervisor.ts` — 加入 queryDecomposer middleware |
| 修改 | `src/tools/query-career-kb.ts` — 加入 subQuestions 參數 |
| 修改 | `src/tools/kb-client.ts` — 加入 agentic + sub_questions 欄位 |
| 新增 | `src/middleware/__tests__/query-decomposer.test.ts` |
