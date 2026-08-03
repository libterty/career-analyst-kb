# Graph Node Contracts — Agentic RAG Retrieval

**Date**: 2026-08-03 · **Implementation**: `services/kb-api/src/rag/graph/nodes.py`

所有 Node 只透過 `RetrievalGraphState` 溝通，不直接呼叫其他 Node 的方法；每個 Node 是既有物件（`PromptOptimizer`、`HybridSearchEngine`、`RelevanceChecker`、`QueryRewriter`、LLM）的**薄 adapter**，不重新實作業務邏輯。

---

```text
Node name: EnhanceQueryNode
Responsibility: 對使用者問題做術語正規化（委派給既有 PromptOptimizer.enhance_query()）
Input state fields: question
Output state fields: normalized_input
Dependencies: PromptOptimizer（既有，不修改）
External side effects: 無
Idempotency key: 不需要（純函式包裝，重跑結果相同）
Timeout: 100ms（本地字串處理，理論上不會逾時；仍設定以防未來換成需要 I/O 的實作）
Retry policy: 不重試（non-retryable：純運算，失敗代表程式錯誤而非暫態錯誤）
Fallback: 若拋例外，直接使用原始 question 作為 normalized_input（不阻斷主流程）
Observability: 記錄 input_len/output_len
Failure behavior: 捕捉例外記錄 error_category=INTERNAL，不重拋（保底行為與現行 inline 版一致）
Unit test strategy: 正常輸入；空字串；PromptOptimizer 拋例外時的 fallback
```

```text
Node name: RetrieveNode
Responsibility: 對單一 query（主問題或某個 sub-question）執行 embed + HybridSearchEngine.search()
Input state fields: normalized_input（或傳入的 sub-question 字串，透過參數而非讀 state，讓平行分支可各自持有自己的 query）
Output state fields: 回傳 list[SearchResult]（不直寫 state；由呼叫端 / Join 節點寫入 chunk_pool）
Dependencies: EmbeddingService.embed_query()（sync，經 run_in_executor 包裝以免阻塞 event loop）、HybridSearchEngine.search()
External side effects: Milvus 查詢（唯讀）
Idempotency key: 不需要（唯讀查詢，天然可重複執行）
Timeout: 5s per call（本地 Milvus，正常應 < 500ms；5s 為異常防護）
Retry policy: Infrastructure retry — max 1 次重試，無 backoff（本地服務，重試延遲無意義），僅重試 ConnectionError/TimeoutError 類別；業務例外（如 embedding 維度不符）不重試
Fallback: 重試後仍失敗 → 回傳空 list（讓下游 RelevanceCheckNode 視為 insufficient，走既有的重試/fallback 路徑，不是新增行為）
Observability: 記錄 query 長度（不記錄原文）、chunk 數、耗時、是否命中重試
Failure behavior: 記錄 error_category=INFRA，回傳空 list，不拋出中斷整個 Graph
Unit test strategy: 正常回傳；Milvus 逾時；Milvus 拋 ConnectionError 觸發重試；重試後仍失敗回傳空 list
```

```text
Node name: MergeChunksNode（Join）
Responsibility: 合併平行 RetrieveNode 的結果（sub-question fan-out），依 chunk_id 去重，截斷至 final_top_k
Input state fields: 各分支回傳的 list[SearchResult]（透過 asyncio.gather 收集，不從 state 讀）
Output state fields: chunk_pool（覆寫）
Dependencies: 無外部依賴，純記憶體運算
External side effects: 無
Idempotency key: 不需要
Timeout: 50ms
Retry policy: 不重試（純運算）
Fallback: 若輸入為空，chunk_pool = []（下游會被判定 insufficient）
Observability: 記錄合併前後 chunk 數、去重數量
Failure behavior: 例外時 chunk_pool 設為空 list，記錄 error_category=INTERNAL
Unit test strategy: 單一來源；多來源有重疊 chunk_id；多來源全不重疊；空輸入
```

```text
Node name: RelevanceCheckNode
Responsibility: 呼叫既有 RelevanceChecker.check()，判斷 chunk_pool 是否足以回答 question
Input state fields: question, chunk_pool
Output state fields: relevance_sufficient, missing_aspects
Dependencies: RelevanceChecker（fastLLM, qwen3:4b）
External side effects: 一次 LLM 呼叫（Ollama）
Idempotency key: 不需要（唯讀判斷，可重複執行且結果應一致，允許因 LLM 抽樣性有微小差異）
Timeout: 8s（fastLLM 本地推論，正常 3-5s）
Retry policy: Model/tool retry — 不在 Node 層重試（既有 RelevanceChecker 內部已有 try/except fallback，見下）；避免重試造成雙重 LLM 呼叫延遲堆疊
Fallback: 沿用 RelevanceChecker 既有邏輯 —— LLM 失敗或解析失敗 → sufficient=True, confidence 降低（既有行為不變，但 Node 層額外記錄 error_category=MODEL_FALLBACK 供 observability 區分「內容真的夠」vs「評估器掛了」）
Observability: 記錄 chunk 數、sufficient、confidence、missing_aspects 數量、是否為 fallback 結果
Failure behavior: 不阻斷，回傳既有 fallback 結果
Unit test strategy: sufficient=True 正常路徑；insufficient 帶 missing_aspects；LLM 呼叫拋例外時的 fallback；chunk 數 < 2 直接 insufficient（既有邏輯）
```

```text
Node name: RewriteQueryNode
Responsibility: 呼叫既有 QueryRewriter.rewrite()，依 missing_aspects 改寫查詢
Input state fields: question, missing_aspects
Output state fields: normalized_input（覆寫為改寫後查詢）；retry_count（+=1）
Dependencies: QueryRewriter（fastLLM + embedder cosine 相似度保護，既有邏輯不變）
External side effects: 一次 LLM 呼叫 + 兩次 embedding 呼叫（相似度檢查）
Idempotency key: 不需要
Timeout: 8s
Retry policy: 不重試（QueryRewriter 內部已有 try/except fallback 回傳原 query）
Fallback: 呼叫失敗或改寫無效（cosine 相似度過高）→ 回傳原 question（既有行為）
Observability: 記錄改寫前後查詢長度（不記錄原文，避免敏感內容進 log）、是否觸發 cosine 保護
Failure behavior: 不阻斷，回傳原查詢
Unit test strategy: 正常改寫；cosine 相似度過高被拒絕；LLM 失敗 fallback；embedding 失敗仍採用改寫結果（既有邏輯）
```

```text
Node name: BuildContextNode
Responsibility: 將 chunk_pool 格式化為 LLM system prompt 用的參考段落文字（委派既有 _build_context()）
Input state fields: chunk_pool
Output state fields: final_context
Dependencies: 無外部依賴
External side effects: 無
Idempotency key: 不需要
Timeout: 50ms
Retry policy: 不重試
Fallback: chunk_pool 為空 → 回傳「（未找到相關段落）」（既有行為）
Observability: 記錄輸出字元數
Failure behavior: 例外時記錄 error_category=INTERNAL，final_context 設為空字串 fallback 文案
Unit test strategy: 有 section 標籤；無 section 標籤；空 chunk_pool
```

```text
Node name: GenerateAnswerNode
Responsibility: 組裝訊息（system+history+question）並呼叫 LLM.astream() 串流生成
Input state fields: final_context, question, （對話 memory，透過既有 ConversationBufferWindowMemory 物件，非 Graph state）
Output state fields: 不寫回 RetrievalGraphState（此 Node 產生的 token stream 直接回傳給 AgenticRAGPipeline.query()，由外層負責 yield 給 client；Graph 的職責在 GenerateAnswerNode 之前結束）
Dependencies: LLM（build_llm()，既有）
External side效果: LLM 推論呼叫（成本/延遲主要來源）
Idempotency key: 不需要（生成式輸出，重跑會有不同結果，這是預期行為）
Timeout: 由既有 SSE keepalive 機制處理（router 層 15s heartbeat），Graph 內部不額外設定，避免與現有機制衝突
Retry policy: Infrastructure retry — 若串流中途連線中斷（非 LLM 邏輯錯誤），最多重試 1 次；已產生的部分 token 不重複 yield（重試等於整個生成重來，需在 UI layer 说明可能有輕微重複體感，本次不在範圍內實作，保留現行「失敗即整個 request 500」行為，僅記錄事件供未來評估）
Fallback: 無（生成失敗即整個請求失敗，這是既有行為，不在本次 Graph 化範圍內變更）
Observability: 記錄 token 數、耗時、model 名稱
Failure behavior: 不吞例外，往上拋給 router 的全域例外處理（既有行為）
Unit test strategy: 本次 Graph 化範圍**不包含**此 Node 的重構（保持在 `AgenticRAGPipeline.query()` 內，Graph 只負責到 `final_context` 產出為止）——見下方「範圍界定」
```

---

## 範圍界定（重要）

Phase 1 的 Graph **只覆蓋 retrieval 階段**（`EnhanceQueryNode` → `RetrieveNode`(s) → `MergeChunksNode` → `RelevanceCheckNode` → (`RewriteQueryNode` 迴圈) → `BuildContextNode`），對應現行 `_retrieve()` / `_do_retrieve()`。LLM 生成（`GenerateAnswerNode` 所描述的行為）**維持在 `AgenticRAGPipeline.query()` 原地**，不搬進 Graph——原因：

1. 生成階段目前無條件分支、無 repair loop，Graph 化收益低（見 `graph-candidate-analysis.md` 的評分邏輯，只對高分段落動手）。
2. 保持生成階段不變，可以讓 Graph 版與既有版共用完全相同的下游程式碼（`self._llm.astream(messages)`），降低回歸風險。
3. Node 表中列出 `GenerateAnswerNode` 是為了完整呈現目標架構圖（`target-graph-design.md`），但其實作維持原樣，僅供未來若要擴充（如加 Infrastructure retry）時有明確的 Node 邊界可用。

## Node 共同保證

- 每個 Node 是 `async def run(state_snapshot, **inputs) -> NodeResult` 形式的 callable，不修改傳入的 state 物件本身（除了明確標示為 Join 的 `MergeChunksNode`），而是回傳新的欄位值，由 `GraphRunner` 統一寫回，符合使用者全域規則「ALWAYS create new objects, NEVER mutate existing ones」。
- 沒有 Node 會建立無法追蹤的 background task；所有 I/O 呼叫都在 `await` 鏈上，Graph 執行完（或失敗）之前不會有游離的 coroutine。
- 沒有 Node 使用無限重試；所有 Retry policy 明確標註 max attempts。
