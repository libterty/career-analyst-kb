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
5. **Feature Flag 切換**：新增 `AppSettings.mode: Literal["Agentic", "Graph"] = "Agentic"`（環境變數 `MODE`），預設 `"Agentic"`（沿用既有 inline 實作）；設為 `"Graph"` 才會切換到 Graph 版本。
6. **Shadow Mode — 本次不引入執行期 Shadow Mode，原因見下方獨立段落**。
7. **低風險流量導入**：Phase 1 交付後，建議先在**非生產環境**（或以 `?debug=true` 之類的內部開關）啟用 flag 進行人工驗證＋跑一次 `eval/rag_eval.py`／`eval/latency_bench.py` 比較分數與延遲。
8. **觀察指標**：`retrieval_iterations` 分布、`relevance_sufficient` 比例、P50/P95 latency（透過既有 Langfuse trace + 新增的 `node_results` 觀察逐節點耗時）。
9. **逐步增加流量**：確認指標與 flag-off 版本一致後，將預設值改為 `True`（獨立 PR，附上觀察期數據）。
10. **快速 Rollback**：全程只需將環境變數 `MODE` 改回 `Agentic` 並重啟服務，無需 revert 程式碼（因為兩條路徑同時存在於程式碼庫中）。
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
- ✅ 加入 Feature Flag（`AppSettings.mode`，環境變數 `MODE`，`"Agentic"` \| `"Graph"`）
- ✅ 更新文件（本系列 9 份文件）
- ✅ 執行既有及新增測試，確認全部通過

## Remaining Risks（尚未解決）

1. **既有安全缺口延續**：`agentic=True` 路徑（無論 flag 開關）目前**未經過** `SecurityGuardrail.check_input()`（詳見 `graph-security-design.md`）。這是本次重構前就存在的既有行為，本次刻意不修正以控制變更範圍，但應在下一個獨立 PR 修正。
2. **`GenerateAnswerNode` 未 Graph 化**：LLM 生成階段仍在 `AgenticRAGPipeline.query()` 原地執行（見 `graph-node-contracts.md` 的「範圍界定」），若未來該階段需要 Infrastructure retry 或 fallback model，需要額外一輪 Graph 化評估。
3. **無正式 Audit Log 系統**：`node_results` 提供執行軌跡但非正式 audit trail（見 `graph-security-design.md`）。
4. **`eval/rag_eval.py` 對照驗證屬人工步驟**：本次交付以 pytest 自動化測試為主；flag on/off 的 eval score 對照建議在合入主線前由人工執行一次（見 Test Evidence）。
5. **Checkpoint/Resume 為 Deferred 而非 Not Needed**：目前判斷不需要，但若後續 MAX_ITERATIONS 或流程複雜度上升，需回頭實作（見 `graph-reliability-design.md`）。

## Next Migration Step — 已完成實際程式碼分析（結論：更新，非原先猜測）

Phase 1 交付時，本文件原先推測「VoltAgent WebSearchAgent 路徑具備更高的 HITL 需求」，屬於**尚未讀程式碼的猜測**。後續實際閱讀 `services/voltagent-career/src/agents/web-search.ts`、`tools/web-search.ts`、`middleware/routing-classifier.ts`、`middleware/confidence-gate.ts`、`judges/answer-quality.ts` 後，結論**修正如下**：

### 實際發現

1. **`WebSearchAgent` 本身是一個 2-step 的 leaf agent**（呼叫 `webSearchTool` 取得 SearXNG 搜尋結果 → LLM 整合成回答），沒有內部條件分支、沒有 retry/repair loop，不滿足「3 個以上處理階段 + 明確條件分支」的候選門檻。
2. **Supervisor 層級已經是一個運作良好、隱性的 Graph**：
   - `routing-classifier.ts` 用 structured output（enum `agent` + `confidence: number`）分類——**已符合**任務要求「LLM Router 必須用有限 enum、不允許輸出任意 node name」。
   - `confidence-gate.ts` 是一個 deterministic threshold router（`confidence < 0.7 → fallback 直接回答`），**已經是**條件分支的 Edge。
   - `answer-quality.ts` 是一個 bounded retry gate（`MAX_RETRIES = 1`，score `< 3` 才重試），並用 fire-and-forget 方式記錄 `score ≤ 2` 的 knowledge gap——**已經符合**「有限重試 + 不吞例外 + 明確 fallback」的設計原則，且**同時適用於 WebSearchAgent 的輸出**（output middleware 是全域套用，不是 per-agent）。
   - 這些middleware 全部已經是本任務所定義的 Node/Edge/Retry 語意，只是實作在 VoltAgent 框架的 middleware 機制裡，而非獨立的 Graph engine。
3. **真正的既有缺口不是「缺少 Graph」，而是一個單點可靠性問題**：`tools/web-search.ts::webSearchTool.execute()` 對 SearXNG 的 `fetch()` 呼叫**沒有 retry、沒有 fallback**——非 2xx 回應直接 `throw`，會讓整個 Agent 呼叫失敗並經由 supervisor 往上拋。這是一次外部 I/O 呼叫的錯誤處理缺陷，**不是**「需要 Graph 化的多階段流程」。

### 修正後的評分（依 `graph-candidate-analysis.md` 相同量表）

| 項目 | 分數 | 說明 |
|---|---|---|
| 條件分支複雜度 | 1 | Agent 內部無分支；分支邏輯已在 supervisor middleware 完成 |
| 錯誤恢復需求 | 2 | 僅需單次 HTTP 呼叫的 retry/fallback，非多節點 repair loop |
| 長時間執行需求 | 0 | 單次 fetch，15s timeout |
| 狀態持久化需求 | 0 | 無跨請求狀態 |
| HITL 需求 | 1 | 全域 `answerQualityGate` 已提供事後品質把關；無新增高風險操作（刪除/付款/發布） |
| 平行化價值 | 1 | 可平行送出中英文兩組關鍵字搜尋，但屬於 Agent-loop 內部的 tool call 次數優化，非流程級平行分支 |
| AI/不確定性決策程度 | 2 | 已有 routing-classifier + confidence-gate + answer-quality judge 三層把關 |
| 可觀測性收益 | 1 | 既有 middleware 結構已可觀測（VoltAgent trace） |
| 重構風險 | 2 | 改動涉及 shared middleware 鏈，牽動所有 agent 的輸出品質把關 |

**結論：不列入 Graph 化候選**（分數遠低於 F4，且真正的問題是一個局部可靠性缺陷，不是流程建模問題）。

### 建議動作（非 Graph 化，屬一般程式碼修復，供另立 PR 處理）

在 `webSearchTool.execute()` 加上：
1. 對 `fetch()` 的 timeout/連線錯誤做 1 次重試（無 backoff，SearXNG 為內部服務）。
2. 重試後仍失敗時回傳一個結構化的「搜尋不可用」結果（而非 `throw`），讓 `WebSearchAgent` 的 LLM 能誠實告知使用者「即時資訊暫時無法取得，以下改用職涯教練知識庫的一般建議」，而不是讓整個請求 500。

此修復規模小、風險低，**不需要**新增 Graph 抽象；已記錄於此供未來獨立處理，本次分析任務不擴大實作範圍。

### 目前已無其他 Graph 化候選

在完成 F4（Agentic RAG Retrieval）與本次 WebSearchAgent 分析後，本專案**目前沒有其他流程符合 Graph 化門檻**（`graph-candidate-analysis.md` 評分表中其餘流程均已評估為不列入）。下一次應該重新評估 Graph 化的觸發條件，見本文件上方「何時應該重新評估」：MAX_ITERATIONS 提高、出現真正的 HITL 需求、需要背景化長時間執行、或出現第二個結構相似的候選流程。
