# Target Graph Design — Agentic RAG Retrieval

**Date**: 2026-08-03 · **Branch**: `feat/graph-agentic-retrieval`
**Scope**: `services/kb-api/src/rag/agentic_pipeline.py::AgenticRAGPipeline._retrieve()`

---

## 2.1 Current Flow（依實際程式碼繪製）

來源：`services/kb-api/src/rag/agentic_pipeline.py` `_retrieve()` / `_do_retrieve()`（第 153-227 行）。

```mermaid
flowchart TD
    Start([query 呼叫]) --> Enhance[PromptOptimizer.enhance_query]
    Enhance --> HasSub{sub_questions?}
    HasSub -- 是 --> SeqLoop["for sq in sub_questions:\nenhance→embed→search (序列)"]
    SeqLoop --> Dedup[chunk_map 去重合併\ntake final_top_k]
    HasSub -- 否 --> SingleSearch[embed + search 主問題]
    Dedup --> LoopStart
    SingleSearch --> LoopStart

    LoopStart[["for i in range(MAX_ITERATIONS=2)"]] --> Check[RelevanceChecker.check]
    Check --> Suff{sufficient\nOR i==last?}
    Suff -- 是 --> BuildCtx[_build_context]
    Suff -- 否 --> Rewrite[QueryRewriter.rewrite]
    Rewrite --> ReSearch[embed + search 改寫後查詢]
    ReSearch --> LoopStart

    BuildCtx --> ReturnMeta[回傳 context, chunks, RetrievalMeta]
    ReturnMeta --> LLM[LLM.astream 生成]
    LLM --> SaveMem[memory.save_context]
    SaveMem --> End([回傳 tokens])
```

**觀察**：
- Sub-question 迴圈是**序列**執行（可平行化但未平行化）。
- Self-reflection 迴圈的終止條件（`sufficient` / `i == MAX_ITERATIONS-1`）與「要不要繼續」耦合在一個 for-loop 的 if 判斷裡，沒有獨立的 Router。
- 沒有任何 checkpoint；一次 process crash 等於整個 retrieval 重來。
- 沒有逐節點 trace，只有一個外層 Langfuse span 包住整個 `_do_retrieve()`。

---

## 2.2 Target Graph

```mermaid
flowchart TD
    START([START]) --> N1[EnhanceQueryNode]
    N1 --> R1{sub_questions\n非空?}

    R1 -- Yes --> N2P1[RetrieveNode\nsub_question 1]
    R1 -- Yes --> N2P2[RetrieveNode\nsub_question 2]
    R1 -- Yes --> N2P3[RetrieveNode\nsub_question N]
    N2P1 --> J1[[Join: MergeChunksNode]]
    N2P2 --> J1
    N2P3 --> J1

    R1 -- No --> N2S[RetrieveNode\n主問題]
    N2S --> J1

    J1 --> CP1{{Checkpoint:\nchunk_pool 快照}}
    CP1 --> N3[RelevanceCheckNode]

    N3 --> R2{router: relevance}
    R2 -- sufficient=True --> N5[BuildContextNode]
    R2 -- sufficient=False AND\nretryCount < MAX_ITERATIONS --> N4[RewriteQueryNode]
    R2 -- sufficient=False AND\nretryCount >= MAX_ITERATIONS --> N5
    R2 -- node error（不可重試） --> FB[[Fallback:\n沿用現有 chunk_pool]]
    R2 -- deadline/latency budget exceeded --> TO[[Timeout Handler:\n沿用現有 chunk_pool]]

    N4 --> N2R[RetrieveNode\n改寫後查詢]
    N2R --> CP2{{Checkpoint:\nretry 後 chunk_pool}}
    CP2 --> N3

    N5 --> N6[GenerateAnswerNode\nLLM.astream]
    FB --> N6
    TO --> N6

    N6 --> R3{LLM 呼叫\n成功?}
    R3 -- Yes --> N7[PersistMemoryNode]
    R3 -- No，且未達 retry 上限 --> RetryLLM[[Retry Edge:\nInfrastructure retry]]
    RetryLLM --> N6
    R3 -- No，已達上限 --> ERR[[Terminal: ERROR]]

    N7 --> END([END: SUCCESS])
    ERR --> ENDERR([END: FAILED])

    style CP1 fill:#333,stroke:#999,color:#fff
    style CP2 fill:#333,stroke:#999,color:#fff
    style FB fill:#553,stroke:#996,color:#fff
    style TO fill:#553,stroke:#996,color:#fff
    style RetryLLM fill:#353,stroke:#696,color:#fff
    style END fill:#144,stroke:#4a4,color:#fff
    style ENDERR fill:#411,stroke:#a44,color:#fff
```

**圖例對應**：

| 元素 | 圖上標記 |
|---|---|
| START/END | `([...])` 圓角節點 |
| Node | 方框（`N1`–`N7`） |
| Deterministic edge | 無標籤箭頭（如 `J1 → CP1`） |
| Conditional edge | `R1`/`R2`/`R3` 決策點上的分支標籤 |
| Retry edge | `RetryLLM`、`N4 → N2R → CP2 → N3`（rewrite-retry 迴圈） |
| Failure/Fallback edge | `FB`、`ERR` |
| Parallel branch | `R1 -- Yes` 下的 `N2P1/N2P2/N2P3` |
| Join point | `J1` |
| Checkpoint | `CP1`、`CP2`（雙線框） |
| Terminal state | `END`、`ENDERR` |

**注意**：此版本**沒有** Human-in-the-loop 節點——F4 是唯讀檢索流程，不涉及刪除資料、付款、對外發布等高風險操作，因此 Phase 1 不引入 approval gate（符合任務原則「不要為了用 Graph 而加不必要的節點」）。若未來 `relevance_sufficient=False` 且已達重試上限的比例持續偏高，可在 `N5`（BuildContextNode）之後、`N6`（生成）之前插入一個 `LowConfidenceEscalationNode`（見 `graph-migration-plan.md`），但本次不實作。

---

## 對照：Graph 化前後差異

| 面向 | Before | After |
|---|---|---|
| Sub-question 檢索 | 序列 for-loop | 平行 Node + Join（同一 event loop 內用 `asyncio.gather`） |
| 迴圈終止條件 | 埋在 for-loop if/else | 獨立 deterministic router `route_after_relevance_check()` |
| 逐輪 observability | 迴圈結束後一次 log | 每個 Node 進出都記錄 `node_name/duration/route_decision` |
| 錯誤處理 | try/except silent fallback（`sufficient=True`） | Node 內部仍保留相同 fallback 語義，但**明確標記為 `error_category`**，可與「內容真的夠」區分 |
| 對外 API 契約 | `ChatResponseDTO(retrieval_iterations, relevance_sufficient)` | 不變 |
| 切換方式 | N/A | `AppSettings.agentic_retrieval_graph_enabled`（預設 `False`） |

State Schema、Node Contract、Router 規則細節見對應文件：`graph-state-schema.md`、`graph-node-contracts.md`。
