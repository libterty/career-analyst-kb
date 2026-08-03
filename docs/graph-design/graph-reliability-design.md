# Graph Reliability Design — Agentic RAG Retrieval

**Date**: 2026-08-03

## Retry 分類

| 類別 | 適用 Node | Max attempts | Backoff | Jitter | Retryable errors | Non-retryable errors | Idempotency 要求 | 最終失敗路徑 |
|---|---|---|---|---|---|---|---|---|
| Infrastructure retry | `RetrieveNode`（Milvus） | 1（共 2 次嘗試） | 無（本地服務，重試延遲無意義） | 無 | `ConnectionError`, `TimeoutError` | Schema/維度不符等程式錯誤 | 天然 idempotent（唯讀查詢） | 回傳空 chunk list，交由 `RelevanceCheckNode` 判定 insufficient |
| Model/tool retry | 無獨立重試層 | 0（不重試） | — | — | — | — | — | 沿用 `RelevanceChecker`/`QueryRewriter` 既有的 try/except fallback（非重試，是降級） |
| Business repair loop | 整個 self-reflection 迴圈（`RelevanceCheckNode → RewriteQueryNode → RetrieveNode`） | 2（`MAX_ITERATIONS`，含第一次） | 無（同輪內立即重試，不是等待型重試） | 無 | N/A（不是錯誤驅動，是品質驅動） | N/A | 每輪都是全新查詢，天然可重複 | 達上限後 `relevance_sufficient=False`，仍用現有 `chunk_pool` 進 `BuildContextNode`（既有行為，不新增 escalation） |

**刻意不做的事**：不把「Milvus 逾時」「LLM 判斷內容不足」「LLM API 呼叫失敗」三種完全不同性質的錯誤都丟回同一個 retry loop 重跑整個 Agent——這是任務要求明確禁止的模式。三者被拆成獨立的 Retry 類別，各自有自己的終止條件與 fallback 路徑。

## Checkpoint 與恢復

**Phase 1 範圍內的決定：不引入跨 process 持久化 Checkpoint。**

理由：
- F4 的完整 retrieval 執行時間 < 5 秒（2 輪迴圈上限），屬於同步 request-response 模式，沒有「長時間執行後中斷」的場景。
- 目前沒有 Human-in-the-loop 節點需要「暫停等待人工輸入」。
- 引入 Checkpoint 儲存（例如 Postgres 表）會增加寫入延遲與維運面，但對這個短生命週期流程沒有對應收益。

**仍然實作的輕量級「記憶體內快照」**（非持久化 Checkpoint，但滿足「可觀測每輪狀態」的需求）：
- `execution_id`：每次 `_retrieve()` 呼叫產生一個 UUID，寫入每個 `NodeResult`，可在 log/Langfuse 中依此關聯同一次執行的所有 Node。
- `node_results`：append-only 清單，記錄每個 Node 執行前後的 state 摘要（不含完整 chunk 內容），等同於「執行軌跡（execution trace）」，可用於除錯與未來若要重放（replay）特定一次執行時的輸入參考。

**若未來需要真正的跨 process Checkpoint／Resume（下一階段觸發條件）**：
1. 觸發條件：F4 迴圈上限提高到 > 2 輪、或新增需要等待外部系統（如人工審批）的 Node、或整體延遲需要背景化（見 `docs/target-graph-design.md` 的 Phase 4 建議模式：`HTTP → 建立 Execution → 回傳 executionId → Background Graph Execution → polling/SSE`）。
2. 實作方式：在 `node_results` 每次 append 後，非阻塞寫入一筆 Postgres `graph_checkpoints` row（`execution_id`, `node_name`, `state_snapshot_ref`, `created_at`），`state_snapshot_ref` 存 chunk_id 清單而非全文。
3. Resume：process 重啟後，用 `execution_id` 查詢最後一筆 checkpoint，從對應 Node 之後繼續（只重跑失敗 Node，不重跑已成功的 Node）。
4. Deployment 情境：新版本部署時，in-flight execution 的 `schema_version` 若與新版本不相容，直接判定該 execution 失敗並要求前端重新發送請求（因為單次執行 < 5 秒，重新發送的成本遠低於實作跨版本相容遷移）。

## Human-in-the-loop

**Phase 1 不需要**：F4 是唯讀知識庫檢索流程，不涉及刪除資料、IAM 修改、付款、對外發布、客戶資源修改或高風險 migration。`relevance_sufficient=False` 時目前的既有行為（用現有 chunk 直接生成，誠實告知不足）已經是可接受的降級策略，不需要人工阻斷。

**未來擴充點**（記錄供 `graph-migration-plan.md` 參考，不在本次實作）：若導入「知識庫覆蓋率低於門檻時，暫停回答並通知內容團隊補充教材」的營運流程，該節點需包含：
- 即將執行的操作：暫停回答、通知內容團隊
- 操作原因：`relevance_sufficient=False` 且已達重試上限
- 預期影響：使用者會看到「稍後回覆」而非即時答案
- 風險：使用者體驗延遲
- Rollback：人工可直接關閉此 Gate，回復到「直接用現有 chunk 生成」
- 執行依據：`missing_aspects` 累積次數超過門檻
- 需要批准的具體選項：核准補充教材 / 核准直接生成 / 標記為知識庫缺口待辦

## Security（與本 Graph 相關的檢查項）

| 項目 | 狀態 | 說明 |
|---|---|---|
| Prompt injection | 已有既有防護 | `SecurityGuardrail`/`InjectionDetector` 在 `ChatService`／router 層執行，Graph 範圍內的 `question` 已是清洗後輸入（F4 目前**未**經過 `IInputValidator`——見下方發現的既有缺口） |
| Tool permission boundary | 符合 | 每個 Node 只取得完成該 Node 所需的依賴（`RetrieveNode` 只拿 search engine + embedder，不拿 LLM 生成用的主 model） |
| Tenant isolation | N/A | 單租戶系統 |
| Secrets leakage | 符合 | Node 不記錄完整 LLM prompt/response 原文到 log，只記錄長度與 metadata |
| Sensitive data persistence | 符合 | State 不落地持久化（Phase 1） |
| Arbitrary command execution | 不適用 | 無 shell/subprocess 呼叫 |
| Unsafe file access | 不適用 | 無檔案系統存取 |
| SSRF | 不適用 | 呼叫的都是內部服務（Milvus, Ollama），無使用者可控 URL |
| SQL injection | 不適用 | 本 Graph 無 SQL 查詢 |
| Output validation | 符合 | `RelevanceChecker._parse()` 對 LLM 輸出做嚴格格式驗證，非結構化文字不會被信任為路由決策 |
| Audit logging | 部分符合 | `node_results` 提供執行軌跡，但非正式 audit log（見 State Schema 文件） |

**發現的既有缺口（超出本次重構範圍，記錄供追蹤）**：`chat.py::_chat_query_sync_agentic()` 直接呼叫 `AgenticRAGPipeline.query()`，**未經過** `IInputValidator.check_input()`（該檢查只在 `ChatService.stream_answer()` 路徑執行）。這是既有程式碼的行為，本次 Graph 化不修正（避免範圍蔓延），但列入 `graph-migration-plan.md` 的 Remaining Risks。
