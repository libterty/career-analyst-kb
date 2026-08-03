# Graph Migration Plan — Agentic RAG Retrieval

**Date**: 2026-08-03 · **Branch**: `feat/graph-agentic-retrieval`

## Framework 選擇

| 方案 | 與現有 Python/FastAPI/asyncio 整合 | State persistence | Checkpoint/Resume | Conditional routing | Parallel execution | HITL | Observability | Testing | Deployment 複雜度 | Vendor lock-in | Learning curve | Runtime cost | Community maturity |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **自製輕量 State Machine/Graph**（本次採用） | 完美（純 Python dataclass + asyncio，複用既有 loguru/Langfuse） | 需自行實作（本次不需要） | 需自行實作（本次不需要） | 完全掌控，deterministic | `asyncio.gather` 原生支援 | 需自行實作 | 直接沿用既有 loguru + Langfuse | 純 Python，pytest 直接測 | 零（無新服務） | 無 | 低（團隊已熟悉 Python） | 零（無額外 runtime） | N/A（內部程式碼） |
| LangGraph | 良好（同屬 LangChain 生態，專案已用 langchain-core） | 內建（SqliteSaver/PostgresSaver） | 內建 | 內建 conditional edges | 內建 | 內建 interrupt | 需另接 LangSmith 或自行整合 | 需學習其測試模式 | 低-中（新增依賴） | 中（API 隨 LangGraph 版本演進較快） | 中 | 低（僅套件） | 高（活躍社群） |
| Durable Workflow Engine（如 Temporal） | 中（需獨立 worker process，需序列化跨語言） | 內建，強一致 | 內建，業界標準 | 內建 | 內建 | 內建 signal/query | 內建 UI + metrics | 需額外 test harness | 高（需部署 Temporal server + worker） | 高 | 高 | 中-高（額外服務） | 高 |
| Queue + 狀態 DB（Celery/RQ + Postgres 表） | 良好 | 手動維護 schema | 手動實作 | 手動實作 | Worker 平行消費 | 手動實作 | 手動埋點 | 標準 | 中（需 broker） | 低 | 低-中 | 中（額外 broker） | 高 |
| Agent Graph Framework（如 AutoGen/CrewAI） | 中（設計目標是多 agent 對話，非通用 workflow） | 依框架而異 | 依框架而異 | 較弱（偏向 agent 間對話輪替） | 部分支援 | 部分支援 | 依框架而異 | 依框架而異 | 中 | 高 | 中-高 | 中 | 中 |

### 選擇理由

1. **F4 的執行特性不需要重量級引擎**：單次執行 < 5 秒、最多 2 輪迴圈、無跨 process 恢復需求、無 Human-in-the-loop（見 `graph-reliability-design.md`）。引入 LangGraph/Temporal 這類提供「持久化＋長時間執行＋跨進程恢復」的能力，對這個流程是**過度工程**——這正是任務原則「不要因為 Graph Engineering 就預設使用特定 Framework」所警示的情況。
2. **降低相依面**：專案目前已有 langchain-core/langchain-ollama 等依賴；新增 LangGraph 雖然生態相容，但會把「一個 2 輪迴圈的檢索流程」的行為正確性綁定到外部套件的版本演進上，而自製版本的行為完全由團隊掌控、可用既有 pytest 直接驗證。
3. **符合現有 DI/Testing 慣例**：kb-api 採 Clean Architecture + 建構子注入；自製 Graph 的 Node 就是「另一種 Service」，可以沿用完全相同的測試/mock 模式（既有 `test_agentic_pipeline.py` 的 `object.__new__()` + mock 注入手法可直接沿用到新的 Node 測試）。
4. **保留未來升級路徑**：本次的 `RetrievalGraphState`/`Node`/`GraphRunner` 抽象化程度足以在未來需要時**替換底層執行引擎**（例如若 WebSearchAgent 的人工審批流程需要真正的跨 process 持久化，屆時可以評估是否把那個更複雜的流程改用 LangGraph 或 Temporal，而不影響本次的 F4 實作）。

### 何時應該重新評估

若以下任一條件成立，應重新評估是否升級到 LangGraph 或 Durable Workflow Engine：
- MAX_ITERATIONS 提高到需要人工中途審批（Human-in-the-loop 節點出現）。
- 單次執行時間超過典型 HTTP request timeout（需要背景化 + polling/SSE 模式）。
- 需要跨 process/跨部署版本的 Checkpoint 恢復。
- 出現第二、第三個結構相似的 Graph 候選流程，值得共用一套更完整的引擎以攤提學習成本。

## 漸進式 Migration 步驟

1. **保留現有流程**：`AgenticRAGPipeline._retrieve()` 的 inline 實作**完全不刪除、不修改**，繼續作為預設路徑。
2. **抽出 Graph 候選流程**：新增 `services/kb-api/src/rag/graph/` 模組（`state.py`, `nodes.py`, `routing.py`, `runner.py`, `build.py`），封裝 retrieval 階段。
3. **建立相同 Interface 的 Graph 版本**：`run_retrieval_graph(question, sub_questions, ...) -> tuple[str, list[SearchResult], RetrievalMeta]`——與既有 `_do_retrieve()` 回傳型別完全相同。
4. **Adapter 包住新 Graph**：`AgenticRAGPipeline._retrieve()` 內以 `if self._use_graph_retrieval: ... else: (既有程式碼)` 分流，兩條路徑共用完全相同的下游（LLM 生成、memory 儲存）。
5. **Feature Flag 切換**：新增 `AppSettings.agentic_retrieval_graph_enabled: bool = False`（環境變數 `AGENTIC_RETRIEVAL_GRAPH_ENABLED`），預設關閉。
6. **Shadow Mode — 本次不引入執行期 Shadow Mode，原因見下方獨立段落**。
7. **低風險流量導入**：Phase 1 交付後，建議先在**非生產環境**（或以 `?debug=true` 之類的內部開關）啟用 flag 進行人工驗證＋跑一次 `eval/rag_eval.py`／`eval/latency_bench.py` 比較分數與延遲。
8. **觀察指標**：`retrieval_iterations` 分布、`relevance_sufficient` 比例、P50/P95 latency（透過既有 Langfuse trace + 新增的 `node_results` 觀察逐節點耗時）。
9. **逐步增加流量**：確認指標與 flag-off 版本一致後，將預設值改為 `True`（獨立 PR，附上觀察期數據）。
10. **快速 Rollback**：全程只需將環境變數改回 `False` 並重啟服務，無需 revert 程式碼（因為兩條路徑同時存在於程式碼庫中）。
11. **移除 Legacy 實作**：待 Graph 版本穩定運行一段時間（建議至少覆蓋一次完整的 golden dataset eval 週期）且觀察期無異常後，才在**獨立 PR**中移除 inline 版本的 `_do_retrieve()` 舊程式碼與對應的 flag 判斷分支。**本次任務不執行此步驟**（保留雙路徑）。

## 為什麼本次不引入執行期 Shadow Mode

任務要求「如果不需要 Shadow Mode，請說明原因」。本次判斷**不需要**執行期 Shadow Mode（即同時跑兩條路徑、比較結果、但只回傳一條路徑的做法），理由：

1. **兩條路徑共用完全相同的底層元件**（同一個 `RelevanceChecker`、`QueryRewriter`、`HybridSearchEngine`、LLM 實例），Graph 版本只是**重新組織呼叫順序與 observability**，不改變任何底層業務邏輯或模型呼叫參數。兩者行為理論上應完全一致，這也是「Graph Integration Tests」中『Feature flag 關閉』對照測試所驗證的重點。
2. Shadow Mode 需要對每個生產請求**執行兩次**完整檢索流程（一次線上、一次背景比較），這會使 Milvus/Ollama 負載加倍，對於本來就是本地資源受限的 Ollama 推論而言，成本不成比例。
3. 既有的**單元測試 + 整合測試等價性驗證**（`graph-testing-strategy.md`）已經在程式碼層級證明兩條路徑行為一致，不需要用生產流量重複驗證同一件事。
4. 若觀察期（步驟 7-8）發現指標有意外差異，屆時可以臨時加上一次性的離線比較腳本（用既有 golden dataset 各跑一次 flag on/off），而不需要常態化的 Shadow Mode 基礎設施。

## 本次交付範圍（Phase 1 實際修改）

- ✅ 建立 State type/schema（`RetrievalGraphState`、`NodeResult`、`GraphError`）
- ✅ 建立 Graph abstraction（`GraphRunner`, `Node` protocol）
- ✅ 將既有 retrieval 邏輯包成 Node（不複製業務邏輯，委派給既有 `PromptOptimizer`/`HybridSearchEngine`/`RelevanceChecker`/`QueryRewriter`）
- ✅ 建立 deterministic edges（`route_after_relevance_check`）
- ✅ 加入錯誤分類與有限 Retry（`RetrieveNode` 的 Infrastructure retry）
- ✅ 加入 structured logging（loguru，每個 Node 進出）
- ✅ 加入 unit 與 graph integration tests
- ✅ 加入 Feature Flag（`AppSettings.agentic_retrieval_graph_enabled`）
- ✅ 更新文件（本系列 9 份文件）
- ✅ 執行既有及新增測試，確認全部通過

## Remaining Risks（尚未解決）

1. **既有安全缺口延續**：`agentic=True` 路徑（無論 flag 開關）目前**未經過** `SecurityGuardrail.check_input()`（詳見 `graph-security-design.md`）。這是本次重構前就存在的既有行為，本次刻意不修正以控制變更範圍，但應在下一個獨立 PR 修正。
2. **`GenerateAnswerNode` 未 Graph 化**：LLM 生成階段仍在 `AgenticRAGPipeline.query()` 原地執行（見 `graph-node-contracts.md` 的「範圍界定」），若未來該階段需要 Infrastructure retry 或 fallback model，需要額外一輪 Graph 化評估。
3. **無正式 Audit Log 系統**：`node_results` 提供執行軌跡但非正式 audit trail（見 `graph-security-design.md`）。
4. **`eval/rag_eval.py` 對照驗證屬人工步驟**：本次交付以 pytest 自動化測試為主；flag on/off 的 eval score 對照建議在合入主線前由人工執行一次（見 Test Evidence）。
5. **Checkpoint/Resume 為 Deferred 而非 Not Needed**：目前判斷不需要，但若後續 MAX_ITERATIONS 或流程複雜度上升，需回頭實作（見 `graph-reliability-design.md`）。

## Next Migration Step（下一個候選，本次不擴大實作範圍）

**VoltAgent WebSearchAgent 路徑**（即時資訊查詢 + 潛在的高風險內容判斷）具備比 F4 更高的 Human-in-the-loop 需求評分（見 `graph-candidate-analysis.md`）。建議下一階段：
1. 先分析 `services/voltagent-career/src/agents/web-search.ts` 現行流程與其呼叫的外部搜尋工具。
2. 評估是否需要在「回傳即時資訊」前插入 confidence/風險 Gate（例如資訊來源不明確時降級或標記）。
3. 若確認需要跨 session 的長時間等待（人工複核已抓取的網路內容），才需要重新評估是否升級到具持久化能力的 Workflow Engine（見上方「何時應該重新評估」）。

本次任務**不**執行上述分析與實作，僅記錄作為下一階段起點。
