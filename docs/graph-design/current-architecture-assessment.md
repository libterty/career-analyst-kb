# Current Architecture Assessment

**Author**: Albert (with Claude Code assistance)
**Date**: 2026-08-03
**Branch**: `feat/graph-agentic-retrieval`
**Status**: Draft — Phase 1 of Graph Engineering initiative

---

## 1. 現有架構摘要

career-analyst-kb 是一個雙服務 mono-repo：

- **kb-api**（Python / FastAPI, port 8000）— Clean Architecture 分層（`api → application → core/domain → infrastructure`），外加一個尚未搬進分層架構的 `rag/`（RAG pipeline）、`ingestion/`、`security/` 模組。RAG 檢索使用 Hybrid Search（Dense Milvus + BM25 + RRF fusion）。
- **voltagent-career**（TypeScript / VoltAgent, port 3141）— Multi-agent supervisor 架構，`CareerLeadAgent` 透過 input/output middleware chain（`guardrail → queryDecomposer → confidenceGate` → subAgent 路由 → `answerQualityGate`）委派給 5 個 specialist agents，並呼叫 kb-api 的 `queryCareerKBTool`。

兩者透過 HTTP + Bearer Token（`CAREER_API_TOKEN`）整合；PostgreSQL 儲存使用者、Session、Feedback；Milvus 儲存向量；Ollama 提供本地 LLM 推論（`gemma3:12b` 主模型、`qwen3:4b` fastModel）。

## 2. 主要流程列表

| # | 流程 | 服務 | 觸發方式 |
|---|------|------|---------|
| F1 | Auth（註冊／登入／refresh） | kb-api | HTTP `POST /api/auth/*` |
| F2 | Chat（標準 RAG 問答, streaming） | kb-api | HTTP `POST /api/chat/query` (SSE) |
| F3 | Chat（標準 RAG 問答, sync） | kb-api | HTTP `POST /api/chat/query/sync` |
| F4 | **Agentic RAG 問答**（Self-Reflection Loop） | kb-api | `POST /api/chat/query/sync` with `agentic=true`（由 VoltAgent 呼叫） |
| F5 | VoltAgent 多 agent 路由 | voltagent-career | HTTP (Hono, port 3141) → `Agent.generate()` |
| F6 | Query Decomposition（複合問題拆解） | voltagent-career | Supervisor `inputMiddlewares` |
| F7 | 文件／逐字稿 Ingestion | kb-api | `POST /api/ingestion/*` 或 CLI script |
| F8 | Session／Feedback CRUD | kb-api | 一般 REST CRUD |
| F9 | Eval Harness（routing / RAG / latency） | eval/ | 獨立 CLI script，非 production runtime |

## 3. 每個流程目前的入口與出口

- **F2/F3**（`chat.py`）：入口 `ChatService.stream_answer()`；出口為 SSE token stream 或 `ChatResponseDTO`。內部依序：session 上限檢查 → `IInputValidator` → `IQueryEnhancer` → 語意快取查詢（可短路）→ `ISearchEngine.search()` → context 組裝 → LLM `astream()` → `IOutputSanitizer` → session 持久化。
- **F4**（`agentic_pipeline.py`）：入口 `AgenticRAGPipeline.query()`；出口同上但額外帶 `retrieval_iterations` / `relevance_sufficient`。內部 `_retrieve()` 是一個 **bounded self-reflection loop**（`MAX_ITERATIONS=2`）：enhance → (sub-question 平行 retrieve 可選) → `RelevanceChecker.check()` → 條件分支（`sufficient` 或已達上限 → 跳出；否則 `QueryRewriter.rewrite()` → 換 query 重新 search）。
- **F5/F6**：入口 VoltAgent `Agent.generate()`；`queryDecomposer` middleware 用 `fastModel` 做 structured-output 分類（`isComplex`, `subQuestions`），注入 `[SUB_QUESTIONS:[...]]` 標記到訊息中；supervisor 依規則路由至 sub-agent 或直接呼叫 `queryCareerKBTool`（帶 `sub_questions`）。
- **F7**：入口 CLI script 或 router；出口為 Milvus 向量 + Postgres metadata。線性 ETL：parse → chunk → classify → embed → store。

## 4. 流程中的狀態如何傳遞

- **F2–F4**：狀態主要透過**函式呼叫堆疊的區域變數**傳遞（`enhanced_query`、`query_embedding`、`results`、`context`、`full_response`），沒有集中的狀態物件。跨請求持久狀態只有兩處：`ChatService._memories`（per-session `ConversationBufferWindowMemory`，LRU-bounded）與 DB 裡的 `chat_messages` 表。
- **F4 自我反思迴圈**：狀態（`current_query`, `current_chunks`, `iterations`）活在 `_retrieve()` 內的區域變數，迴圈結束即丟棄；只有 `RetrievalMeta(iterations, sufficient)` 被保留供 API response 使用。**沒有可持久化、可恢復的中間狀態**——若 process 在迴圈中重啟，整個請求必須重來。
- **F5/F6**：狀態透過訊息字串內嵌的 `[SUB_QUESTIONS:...]` tag 傳遞給下一個 middleware/agent，屬於 stringly-typed、無 schema 驗證的隱性狀態傳遞。

## 5. 現有分支與 retry 邏輯

- **F4 的條件分支**：`relevance.sufficient == True` → 結束迴圈；`False` 且 `i < MAX_ITERATIONS-1` → rewrite 並重試；`False` 且已達上限 → 仍結束迴圈但標記 `sufficient=False`（無 fallback 節點，直接用現有 chunk 生成）。
- **F6 判斷分支**：`isLikelyComplex()`（正規表達式 + 長度）決定要不要呼叫 LLM 分類；LLM 分類的 `isComplex` 決定是否注入 sub-questions。
- **重試**：`QueryRewriter` / `RelevanceChecker` 對外部 LLM 呼叫失敗時**直接 fallback**（`sufficient=True` 或回傳原 query），沒有 retry-with-backoff；這是刻意設計（避免 local LLM 卡住拖慢請求），但也代表暫時性錯誤（如 Ollama 短暫過載）不會重試，會被誤判為「內容足夠」。
- 全域：無 Infrastructure-level retry（Milvus/Ollama 連線失敗直接向上拋例外，由 FastAPI 全域 exception handler 轉成 500）。

## 6. 關鍵 Side Effects

- LLM 呼叫（Ollama/OpenAI/Grok/Anthropic）— 有成本與延遲。
- Milvus 向量搜索、BM25 index 存取。
- PostgreSQL 寫入：`chat_messages`、`chat_sessions.message_count`、`semantic_cache`。
- Langfuse tracing span（`rag-retrieve`、`agentic-rag-retrieve`）。
- Prometheus counter（如 `milvus_flush_errors_total`）。
- 語意快取寫入（fire-and-forget，失敗只記 log）。

## 7. 目前的可靠性與可觀測性問題

- **Agentic 迴圈無逐輪 observability**：目前只有迴圈結束後一次性 `logger.info`，看不到「第幾輪 rewrite 了什麼」「每輪 latency」等中間資料，除非開 DEBUG log。
- **無法從迴圈中斷點恢復**：MAX_ITERATIONS=2 且是同步函式呼叫，一次請求的完整迴圈必須在同一個 process 存活期內跑完；長時間 Ollama 冷啟動會直接拖慢整個 request，沒有背景執行 + polling 的退路。
- **sub_questions 平行檢索未平行化**：`_retrieve()` 對每個 sub-question 是**序列**呼叫 `search()`（見 `agentic_pipeline.py:175-179`），這是可平行化卻沒平行化的段落。
- **relevance check / rewrite 失敗即 silent fallback**：`sufficient=True`／回傳原 query，混淆了「內容真的夠」與「評估器掛了」兩種情況，指標上無法區分。
- **無 Human-in-the-loop**：`relevance_sufficient=False` 且已達重試上限時，目前仍直接生成答案，沒有升級（escalate）路徑。

## 8. 適合 Graph 化的流程

- **F4：Agentic RAG Retrieval（self-reflection loop + sub-question 合併）**— 見 `docs/graph-candidate-analysis.md` 評分，這是本次 Phase 1 重構對象。

## 9. 不適合 Graph 化、應維持原狀的流程

| 流程 | 原因 |
|------|------|
| F1 Auth | 純 CRUD + JWT，無分支、無重試需求 |
| F2/F3 標準 Chat（非 agentic） | 線性流程，僅一個快取短路分支，複雜度低、已穩定且有測試覆蓋 |
| F7 Ingestion | 決定性 ETL（parse→chunk→classify→embed→store），順序固定、無需人工介入或動態路由 |
| F8 Session/Feedback CRUD | 標準 REST CRUD |
| F5/F6 VoltAgent Supervisor 路由 | **VoltAgent 框架本身已提供 Node/Edge 語意**（`subAgents` delegation + `inputMiddlewares`/`outputMiddlewares` 鏈），重新用另一套 Graph 框架重寫等於是重複發明框架已有能力，風險/收益比差 |
| F9 Eval Harness | Batch/CLI 工具，非 production runtime，不需要 Graph 的 checkpoint/resume 語意 |

## 10. Graph 化的實際收益與引入成本

**收益**：
- 每輪 retrieve/check/rewrite 可獨立 trace、可獨立測試、可獨立套用 timeout/retry 政策。
- sub-question retrieval 可以合法宣告為平行分支（Fan-out/Join），而不是隱藏在 for-loop 裡。
- 迴圈終止條件（sufficient / max iteration / timeout / budget）可以被明確路由規則表達，而非埋在 if/else。
- 未來要加「connection 失敗時 escalate 給人工複核」或「超過 budget 時直接進 fallback context」時，只需新增一個 Node + Edge，不需改動既有迴圈邏輯。

**成本**：
- 新增一層抽象（State / Node / Runner），對只有 2 輪迴圈的流程而言有輕微 overhead。
- 需要保證 Graph 版本與現有 inline 版本行為一致（透過共用測試 + feature flag 降低風險）。

**結論**：收益大於成本，但僅限 F4；其他流程維持現狀（詳見 `docs/graph-candidate-analysis.md` 評分表）。
