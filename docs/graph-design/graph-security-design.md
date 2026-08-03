# Graph Security Design — Agentic RAG Retrieval

**Date**: 2026-08-03

本文件聚焦於 Graph 架構引入後的安全邊界；系統層級的既有安全機制（JWT、Rate limiting、CORS、Presidio PII redaction）已在 `.planning/codebase/ARCHITECTURE.md` / `CONCERNS.md` 記錄，不重複展開。

## 每個 Node 的最小權限

| Node | 取得的依賴 | 明確不取得 |
|---|---|---|
| `EnhanceQueryNode` | `PromptOptimizer` | 無 LLM、無網路、無 DB |
| `RetrieveNode` | `EmbeddingService`, `HybridSearchEngine`（唯讀 Milvus client） | 無寫入 Milvus 的權限、無 LLM、無 DB |
| `MergeChunksNode` | 無外部依賴 | 純記憶體運算 |
| `RelevanceCheckNode` | `RelevanceChecker`（僅 fastLLM） | 不使用主 LLM（成本/延遲考量），不存取 DB |
| `RewriteQueryNode` | `QueryRewriter`（fastLLM + embedder） | 不存取 DB、不存取主 LLM |
| `BuildContextNode` | 無外部依賴 | 純字串格式化 |

這個切分讓「哪個 Node 出問題可能造成什麼影響」有明確邊界——例如即使 `RewriteQueryNode` 的 prompt 被 injection 影響，它最多只能改變**搜索查詢字串**，無法觸及主 LLM 生成、無法寫入資料庫、無法呼叫其他工具。

## Prompt Injection

- `AgenticRAGPipeline.query()` 的呼叫路徑（`chat.py::_chat_query_sync_agentic`）**目前未經過** `SecurityGuardrail.check_input()`（此為既有缺口，見 `graph-reliability-design.md` 的「發現的既有缺口」，已列入 `graph-migration-plan.md` 的 Remaining Risks，不在本次範圍內修正，因為修正會改變既有 `agentic=True` 路徑的行為，需要獨立的回歸測試與 PR）。
- `RelevanceCheckNode` / `RewriteQueryNode` 的 LLM 呼叫使用**固定模板 + 使用者輸入插值**，兩者皆用 `_PROMPT_TEMPLATE.format()`——這代表使用者問題若包含類似「忽略上述指示」的字串，仍會被當作純文字插入模板，而不是被當成新的系統指令（因為 LangChain `HumanMessage` 的角色邊界由底層 chat model API 保證，不是由字串拼接決定）。此為既有設計，Graph 化未改變其安全性質，僅是把呼叫點從函式改為 Node。
- `RelevanceChecker._parse()` **嚴格驗證** LLM 輸出格式（第一行必須是 `SUFFICIENT`/`INSUFFICIENT`），任何不符合格式的輸出都會被視為「無法解析」而觸發 fallback，**不會**讓 LLM 的自由文字輸出直接決定路由——這正是任務要求「Router 使用 LLM 時必須使用 structured output、定義有限 enum destinations、不允許模型輸出任意 Node name」的體現。

## Router 的 Enum 邊界

`route_after_relevance_check()`（`graph-node-contracts.md` 中 `RelevanceCheckNode` 之後的路由）**不讓 LLM 決定下一個 Node**。路由完全由 deterministic 程式碼判斷：

```text
relevance_sufficient == True
    → BuildContextNode

relevance_sufficient == False AND retry_count < MAX_ITERATIONS - 1
    → RewriteQueryNode

relevance_sufficient == False AND retry_count >= MAX_ITERATIONS - 1
    → BuildContextNode（fallback，帶 relevance_sufficient=False）
```

LLM（`RelevanceChecker`）只負責產出一個 **boolean** 欄位（`sufficient`），這個 boolean 才是路由輸入，而不是讓 LLM 輸出「下一步要做什麼」的自由文字。這消除了「模型可以指示 Graph 跳到任意 Node」的攻擊面。

## Secrets / Sensitive Data

- 無新增 secrets；本次重構不引入新的外部服務或 API Key。
- `node_results` 與 log 只記錄：Node 名稱、耗時、chunk 數、boolean 決策、error_category——**不記錄**使用者問題全文、chunk 全文、LLM 完整回應。若需要除錯完整內容，走既有的 Langfuse trace（該系統已有自己的存取控制與資料保留政策），不透過本次新增的 `node_results` 洩漏。
- `errors` 欄位的 message 經過截斷與清理（移除可能的 stack trace 路徑資訊），避免內部檔案路徑或依賴版本號洩漏到最終可能被記錄或回傳的欄位。

## SSRF / SQL Injection / 任意指令執行

不適用——本 Graph 呼叫的所有外部系統（Milvus、Ollama）皆為內部服務、透過既有的 client library（`pymilvus`, `langchain-ollama`）呼叫，沒有使用者可控的 URL 或 SQL 字串拼接。

## Audit Logging

- `node_results`（append-only）提供「這次執行經過哪些 Node、做了什麼決策」的軌跡，可作為 audit trail 的資料來源。
- 尚未接上正式的 audit log 系統（如集中式 audit 服務）；`graph-migration-plan.md` 列為 Remaining Risk / 未來擴充項，非本次 Phase 1 交付範圍。

## 本次未新增的攻擊面

- 未新增任何新的網路端點（Graph 完全在既有 `AgenticRAGPipeline` 內部運作，經由 feature flag 切換，不改變 `POST /api/chat/query/sync` 的外部介面）。
- 未新增任何新的依賴套件（Graph engine 是專案內自製的輕量模組，見 `docs/graph-design/graph-migration-plan.md` 的 Framework 選擇理由）。
- 未新增任何背景執行緒或無法追蹤的 async task；所有 Node 都在既有的 request-scoped `await` 鏈上執行。
