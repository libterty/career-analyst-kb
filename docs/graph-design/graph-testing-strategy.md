# Graph Testing Strategy — Agentic RAG Retrieval

**Date**: 2026-08-03 · **Test location**: `services/kb-api/tests/unit/graph/`

## 原則

- 既有測試（`test_agentic_pipeline.py`、`test_relevance_checker.py`、`test_query_rewriter.py`、`test_rag_pipeline.py`）**必須全部繼續通過，不刪除、不降低斷言標準**。
- 新測試**不重複驗證** `RelevanceChecker`/`QueryRewriter` 的內部邏輯（已有既有測試覆蓋），只驗證 Graph Node 對它們的呼叫方式與資料傳遞是否正確。
- Feature flag 關閉時（預設），既有 `AgenticRAGPipeline._retrieve()` 的行為與測試**完全不變**——這是本次重構「不破壞現有 API」的可驗證證明。

## Node Unit Tests（`tests/unit/graph/test_nodes.py`)

| Node | 測項 |
|---|---|
| `EnhanceQueryNode` | 正常輸入 → 呼叫 `PromptOptimizer.enhance_query`；`PromptOptimizer` 拋例外 → fallback 回原始問題，不中斷 |
| `RetrieveNode` | 正常回傳 chunk 列表；`search()` 拋 `ConnectionError` → 觸發 1 次重試；重試後仍失敗 → 回傳空列表且不拋出；`search()` 拋非 retryable 例外（如 `ValueError`）→ 不重試，直接回傳空列表並記錄 error_category |
| `MergeChunksNode` | 單一來源；多來源有重疊 `chunk_id`（驗證去重）；多來源全不重疊；空輸入列表；輸入超過 `final_top_k`（驗證截斷） |
| `RelevanceCheckNode` | 委派給 `RelevanceChecker.check()` 並正確映射到 `sufficient`/`missing_aspects`；`RelevanceChecker` fallback 時，Node 記錄 `error_category=MODEL_FALLBACK`（既有測試 `test_relevance_checker.py` 已覆蓋 `RelevanceChecker` 本身邏輯，此處只驗證 Node adapter） |
| `RewriteQueryNode` | 委派給 `QueryRewriter.rewrite()`；驗證 `retry_count` 正確 +1；驗證改寫後查詢寫入 `normalized_input` |
| `BuildContextNode` | 委派給既有 `_build_context()`；空 `chunk_pool` → fallback 文案 |

## Router Tests（`tests/unit/graph/test_routing.py`）

覆蓋 `route_after_relevance_check()` 的所有分支：

| 情境 | 輸入 | 預期路由 |
|---|---|---|
| 正常路徑 | `sufficient=True, retry_count=0` | → `BuildContextNode` |
| Retry 路徑 | `sufficient=False, retry_count=0`（MAX_ITERATIONS=2） | → `RewriteQueryNode` |
| Retry 耗盡路徑 | `sufficient=False, retry_count=1`（已達上限） | → `BuildContextNode`（fallback，`relevance_sufficient=False`） |
| Fallback 路徑（Node 錯誤） | `RetrieveNode` 回傳空列表且 `error_category=INFRA` | → 仍進入 `RelevanceCheckNode`（空列表天然判定 insufficient，既有邏輯） |
| Budget/Timeout 路徑 | Graph 整體執行超過 overall timeout（見 `graph-reliability-design.md`） | → 直接用當前 `chunk_pool` 進 `BuildContextNode`（不再等待下一輪） |

註：本 Graph 沒有 Human approval 路徑（見 `target-graph-design.md` 說明），故不列入 Router 測試。

## Graph Integration Tests（`tests/unit/graph/test_retrieval_graph.py`）

| 情境 | 驗證重點 |
|---|---|
| Happy path（單問題，第一輪即 sufficient） | `node_results` 恰好包含 `Enhance→Retrieve→Merge→RelevanceCheck→BuildContext`，`retry_count=0` |
| Node failure（`RetrieveNode` 拋非預期例外） | Graph 不整個崩潰，該輪 chunk_pool 為空，仍能走到 `BuildContextNode` 產出 fallback context |
| Partial failure（sub-question fan-out 中一個分支失敗） | `MergeChunksNode` 仍能合併其餘成功分支的結果，不因單一分支失敗整體失敗 |
| Retry success（第一輪 insufficient，第二輪 sufficient） | `retry_count=1`，`node_results` 顯示完整第二輪節點序列，`missing_aspects` 在第一輪後被填入、第二輪後保留供除錯 |
| Retry exhausted（兩輪都 insufficient） | 最終 `relevance_sufficient=False`，仍產出 `final_context`（不是空答案） |
| Duplicate sub-question chunk（重複事件） | 兩個 sub-question 回傳相同 `chunk_id` → `MergeChunksNode` 去重，驗證不會把同一段落重複塞進 context 兩次 |
| Parallel Node completion order 不同 | 用 `asyncio.gather` 模擬其中一個分支比另一個慢完成，驗證合併結果與完成順序無關（純粹依 `chunk_id` 去重，不依賴先後順序，除了「先出現的保留」的既有 dict 語意——需與 inline 版行為一致） |
| Feature flag 關閉 | `agentic_retrieval_graph_enabled=False` 時，`AgenticRAGPipeline._retrieve()` 走既有 inline 程式碼路徑，`node_results` 不產生（因為沒有經過 Graph runner），驗證與 Graph 路徑在**相同輸入**下產出**相同的 `(context, chunks, RetrievalMeta)`**（Shadow 對照測試，非執行期 Shadow Mode，是測試期的一次性等價性驗證，見 `graph-migration-plan.md`） |

**Checkpoint resume / Process restart**：本 Phase 不實作跨 process Checkpoint（見 `graph-reliability-design.md`），故不需要對應整合測試；若未來啟用該功能，需在此文件補上對應的 resume 測試案例。

## Regression Tests

| 項目 | 驗證方式 |
|---|---|
| API Contract 不變 | `services/kb-api/tests/integration/test_api.py` 既有測試繼續通過；新增一則 `test_agentic_sync_endpoint_contract_unchanged`，比較 flag on/off 兩種情況下 `ChatResponseDTO` 的欄位集合與型別完全相同 |
| Business result 一致 | Graph Integration Tests 中的「Feature flag 關閉」對照測試 |
| Authorization 行為一致 | 不變更 — `chat.py` 的 `get_current_user` 依賴保持不動 |
| Tenant isolation 一致 | N/A（單租戶） |
| Error response 相容 | `_chat_query_sync_agentic()` 的例外處理（`HTTPException 500`）不變 |
| 關鍵效能沒有明顯退化 | 手動執行 `eval/latency_bench.py --url ... ` 比較 flag on/off 的 P50/P95（本次交付以 pytest 測試為主，latency bench 為建議的驗收步驟，記錄於 `graph-migration-plan.md`） |

## LLM Node 的測試斷言（非純文字比較）

- `RelevanceCheckNode`／`RewriteQueryNode` 測試使用既有的 Mock LLM（`MagicMock` 回傳固定 `RelevanceResult`/字串），**不**對真實 LLM 做完整文字輸出比較。
- 斷言重點：
  - Structured output schema：`RelevanceResult(sufficient: bool, missing_aspects: list[str], confidence: float)` 的型別與欄位存在性。
  - Routing result：給定 `sufficient=True/False` 組合，驗證 `route_after_relevance_check()` 回傳的下一個 Node 名稱（deterministic assertion，非字串相似度）。
  - Tool usage：驗證 `RelevanceChecker.check()`／`QueryRewriter.rewrite()` 被呼叫的**次數與參數**（`assert_called_once_with(...)`），而非驗證它們回傳的自然語言內容。
  - Safety：驗證 `RelevanceChecker._parse()` 對非預期格式輸出的 fallback 行為（既有測試已覆蓋，本次新增 Node 層是否正確傳遞 fallback 結果）。
- Golden dataset／eval case：本次 Graph 化不改變 `eval/rag_eval.py` 的 LLM-as-judge 評分邏輯；建議在 Shadow 驗證期間（見 migration plan）額外跑一次 `eval/rag_eval.py` 比較 flag on/off 的分數是否在合理誤差範圍內（因為兩者共用完全相同的底層 `RelevanceChecker`/`QueryRewriter`/LLM，理論上分數應相同或極接近）。

## 實際執行指令

```bash
cd services/kb-api
pytest tests/unit/graph/ -v                      # 新增的 Node/Router/Graph 測試
pytest tests/unit/test_agentic_pipeline.py -v     # 既有測試必須繼續通過
pytest tests/unit/ -v                             # 全部單元測試
pytest tests/integration/ -v                      # 既有整合測試必須繼續通過
```
