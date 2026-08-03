# Graph State Schema — Agentic RAG Retrieval

**Date**: 2026-08-03 · **Implementation**: `services/kb-api/src/rag/graph/state.py`

## 設計原則

State 只保存**驅動路由決策**與**跨 Node 傳遞**所需的資料。大型內容（完整 chunk 全文、LLM 完整輸出）以 dataclass 欄位保存於記憶體內（單一 request 生命週期內），但**不落地到日誌或外部儲存**；未來若要接 Checkpoint 持久化（見 `graph-reliability-design.md`），必須先把 `chunk_pool` 換成 chunk_id 參照 + 從 Milvus 重查，而不是整包序列化寫進 DB。

## 完整欄位評估

| 欄位 | 是否需要（Phase 1 實作） | 說明 |
|---|---|---|
| `execution_id` | **必要** | 每次 `_retrieve()` 呼叫產生一個 UUID，用於 log/trace 關聯；不落地持久化（迴圈執行時間 < 30s，不需要跨 process 恢復） |
| `request_id` | Optional（暫不實作，Phase 1 沿用既有 Langfuse `trace_id`） | 若日後接 HTTP correlation id middleware，可從 `langfuse_trace_id_var` 帶入 |
| `tenant_id` | 不需要 | 目前系統是單租戶（單一組織的知識庫），無 multi-tenant 需求 |
| `user_id` | 不需要（在此 Graph 範圍外） | `user_id` 屬於 `ChatService`/router 層級，不進入 retrieval graph state；避免 Node 拿到不必要的權限範圍 |
| `input` (question) | **必要** | 使用者原始問題，唯讀 |
| `normalized_input` | **必要**（`enhanced_query`） | `PromptOptimizer.enhance_query()` 輸出，供搜索使用 |
| `sub_questions` | **必要** | 複合問題拆解結果（由呼叫端傳入，非本 Graph 產生） |
| `intent` / `plan` | 不需要 | 本 Graph 不做意圖分類或多步計畫；路由規則是 deterministic，不需要「計畫」欄位 |
| `current_step` | **必要**（`current_node`） | 供 observability 與錯誤訊息定位 |
| `status` | **必要** | enum：`running` / `succeeded` / `failed` |
| `chunk_pool` | **必要，但只能覆寫（見下）** | 目前一輪的 `SearchResult` 清單；只存 `chunk_id` + metadata（`source`/`section`/`score`），不存整份原文重複拷貝（`SearchResult` 本身已含 `content`，此處不額外複製） |
| `node_results` | **必要，append-only** | 每個 Node 執行的 `NodeResult`（name/duration/route/error_category），供 `graph-testing-strategy.md` 的整合測試與未來 metrics 使用 |
| `retry_count` | **必要，可覆寫** | Self-reflection 迴圈目前輪數，驅動 `route_after_relevance_check` |
| `missing_aspects` | **必要，可覆寫** | `RelevanceChecker` 輸出，供 `RewriteQueryNode` 使用 |
| `relevance_sufficient` | **必要** | 對外契約欄位（`ChatResponseDTO.relevance_sufficient`），Graph 結束時填入 |
| `errors` | **必要，append-only** | 每個 Node 若發生非阻斷性錯誤（fallback 觸發），記錄 `(node, error_category, message)`，不記錄完整 stack trace（避免洩漏內部細節到跨 Node 傳遞的 state；stack trace 只進 loguru） |
| `started_at` / `updated_at` | **必要** | 用於計算 end-to-end latency 與逐 Node duration |
| `deadline` | Optional（Phase 1 用固定 per-request timeout，非逐 Node deadline） | 見 `graph-reliability-design.md` 的 timeout 設計；欄位保留但目前只在 Graph 層做一次性 overall timeout |
| `latency_budget` / `token_budget` / `cost_budget` | 不需要（Phase 1） | 目前無成本控管需求（本地 Ollama 推論無外部計費）；欄位在 dataclass 中保留為 `Optional[None]` 佔位，供未來若切換到 OpenAI/Anthropic 計費模型時啟用，不需要改 State schema |
| `approval_status` | 不需要 | 本 Graph 無 Human-in-the-loop 節點（見 `target-graph-design.md`） |
| `audit_trail` | 不需要（獨立欄位） | Node 進出已記錄於 `node_results`，不需要額外的 audit_trail 欄位；若接上真正的 audit log 系統，直接消費 `node_results` |
| `final_result` | **必要**（`context`, `chunk_pool`, `RetrievalMeta`） | Graph 執行完的輸出，交還給 `AgenticRAGPipeline.query()` 組裝 LLM 訊息 |

## 欄位覆寫規則

| 欄位 | 規則 |
|---|---|
| `chunk_pool` | **允許覆寫**（每輪 retrieve 後被新結果取代或合併），但**不可變更歷史**——每次覆寫前的值已寫入對應的 `NodeResult.output_meta`，可回溯 |
| `node_results` | **只能 append**，不可修改既有項目（審計用途） |
| `errors` | **只能 append** |
| `retry_count` | 只能單向遞增（`+= 1`），不可重設 |
| `missing_aspects` | 允許覆寫（每輪 relevance check 後更新） |
| `status` | 只能沿著 `running → (succeeded | failed)` 單向轉移，不可從終態轉回 `running` |
| 其他（`input`, `sub_questions`, `execution_id`, `started_at`） | **不可變**（Immutable，符合使用者全域規則） |

## 平行 Node 如何合併 State（避免 concurrent update）

Sub-question 平行檢索（`R1 -- Yes` 分支）用 `asyncio.gather()` 同時執行多個 `RetrieveNode`，**每個平行分支拿到的是 State 的唯讀快照（`question`, `sub_question`, `search_engine` 等），不共享可變欄位**。各分支各自回傳獨立的 `list[SearchResult]`，由單一的 `MergeChunksNode`（Join 節點）**在合併點以單一 coroutine 依序寫回** `state.chunk_pool`（先 dedupe by `chunk_id` 再截斷至 `final_top_k`）。因為 Python asyncio 是單執行緒協作式排程，合併點本身不會有 race condition；**規則是：只有 Join 節點可以寫入共享 State，Fan-out 的平行分支只能回傳純值，不得直寫 State**。

## State 是否包含敏感資料

- `input`（使用者問題）可能包含 PII（如公司名稱、薪資數字）；State 只存在單次 request 的記憶體生命週期內，**不落地持久化、不寫入日誌全文**（loguru 只記錄長度與雜湊化摘要，見 `graph-security-design.md`）。
- `chunk_pool` 來源是公開 YouTube 影片逐字稿，非機密資料。
- `errors` 只記錄 `error_category` 與經過清理的訊息，不記錄 LLM 完整 raw response（避免洩漏 prompt injection 內容或內部 prompt 結構到 log）。

## 哪些資料應該儲存 reference 而非完整內容

- `chunk_pool` 目前存 `SearchResult` dataclass（含 `content` 全文），因為：(a) 此欄位活在單一 request 記憶體內，不落地；(b) 下游 `BuildContextNode` 需要全文組 context，若只存 reference 需要多一次 Milvus round-trip，得不到明顯好處。**若未來 Checkpoint 落地持久化**，必須改成只存 `chunk_id` + `score`，由恢復時的 Node 重新從 Milvus 撈原文（見 `graph-reliability-design.md` 的 Resume 設計）。
- `node_results[].output_meta` 只存 metadata（chunk 數量、iteration 編號、耗時），不存完整 chunk 內容或完整 LLM 輸出。

## State Versioning 與 Migration

Phase 1 的 `RetrievalGraphState` 是**單一請求生命週期內的暫態物件**，不持久化，因此**目前不需要 schema version migration**。若後續（Phase 2+）引入跨 process 的 Checkpoint 持久化，屆時：
1. 在 dataclass 加上 `schema_version: int = 1` 欄位。
2. Checkpoint 讀取時依 `schema_version` 走對應的 upgrade 函式（`_migrate_v1_to_v2()` 之類），沒有欄位的用預設值填補，多出來的欄位丟棄。
3. 在 `graph-migration-plan.md` 記錄每次 schema 變更的相容性策略。

## 實作對照（`services/kb-api/src/rag/graph/state.py`）

```python
@dataclass
class RetrievalGraphState:
    # Immutable inputs
    execution_id: str
    question: str
    sub_questions: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.monotonic)

    # Mutable — overwritten each iteration
    normalized_input: str = ""
    chunk_pool: list[SearchResult] = field(default_factory=list)
    missing_aspects: list[str] = field(default_factory=list)
    relevance_sufficient: bool = False
    current_node: str = ""
    status: Literal["running", "succeeded", "failed"] = "running"

    # Mutable — monotonic increment only
    retry_count: int = 0

    # Append-only
    node_results: list[NodeResult] = field(default_factory=list)
    errors: list[GraphError] = field(default_factory=list)

    # Output
    final_context: str = ""
    updated_at: float = field(default_factory=time.monotonic)
```
