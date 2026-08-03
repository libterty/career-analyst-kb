# Graph Candidate Analysis

**Date**: 2026-08-03 · **Branch**: `feat/graph-agentic-retrieval`

Scoring scale 0–5 per dimension (0 = not applicable/low, 5 = strongly applicable/high). "Graph 化候選" 只有在 (收益總分) 明顯高於 (重構風險) 時才成立。

## 評分表

| 流程 | 條件分支複雜度 | 錯誤恢復需求 | 長時間執行需求 | 狀態持久化需求 | HITL 需求 | 平行化價值 | AI/不確定性決策程度 | 可觀測性收益 | 重構風險 | 結論 |
|---|---|---|---|---|---|---|---|---|---|---|
| **F4 Agentic RAG Retrieval**（self-reflection loop） | 4 | 3 | 1 | 1 | 2（僅未來擴充點） | 4（sub-question fan-out） | 4（relevance check + rewrite 皆為 LLM 判斷） | 4 | **2**（有既有測試、可 feature-flag、輸出契約不變） | **Graph 化候選（Phase 1）** |
| F2/F3 標準 Chat（非 agentic） | 1（僅快取命中短路） | 1 | 0 | 1（session memory，已有） | 0 | 0 | 1（僅 LLM 生成，非路由決策） | 1 | 3（觸碰主要生產路徑，回歸風險高） | 不列入 — 收益不足以覆蓋風險 |
| F5/F6 VoltAgent Supervisor | 3 | 2 | 1 | 1 | 1 | 2 | 4 | 3 | 4（框架已提供對等能力，重寫等於重複造輪） | 不列入 — 框架已內建 Node/Edge 語意 |
| F7 Ingestion Pipeline | 1 | 2 | 2（大量文件時） | 1 | 0 | 3（多檔案可平行） | 0（無 LLM 決策，分類器是 deterministic/轻量模型但非流程路由） | 1 | 2 | 不列入 — 目前規模小、CLI-driven、無條件分支需求；若未來規模擴大可重新評估 |
| F1/F8 Auth/CRUD | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 不列入 — 明確排除（普通 CRUD） |
| F9 Eval Harness | 1 | 1 | 1 | 0 | 0 | 2 | 2 | 1 | 1 | 不列入 — 非 production runtime |

## 為什麼選 F4（Agentic RAG Retrieval）

1. **三個以上處理階段**：Query Enhance → (Sub-question Fan-out) → Hybrid Search → Relevance Check → 條件 Rewrite-and-Retry → Context Build → LLM Generation。
2. **明確條件分支**：`sufficient` vs `insufficient`；`insufficient` 又分「還有重試額度」vs「已達上限」。
3. **呼叫多個外部系統**：Milvus（向量+BM25）、Ollama fastLLM（relevance check + rewrite）、Ollama/OpenAI 主 LLM（生成）、Embedding service。
4. **有 retry/repair 需求**：rewrite-and-retry 本質就是一個 bounded repair loop。
5. **可平行執行的工作**：sub-question 目前是序列 search，屬於「應該平行但還沒平行」的段落——Graph 化時可用 Fan-out/Join 明確表達。
6. **需要追蹤每一步狀態、成本、結果**：目前只有迴圈結束後一次 log，缺乏逐節點 observability，這正是 Graph 化在 Observability 上的直接收益。
7. **包含 LLM／不確定性決策**：`RelevanceChecker`、`QueryRewriter` 都是 LLM-based 判斷節點，適合明確建模為有限 enum 輸出的 Node，而不是散落在函式內的字串解析。
8. **重構風險可控**：已有 4 個既有單元測試檔（`test_agentic_pipeline.py`、`test_relevance_checker.py`、`test_query_rewriter.py`、`test_rag_pipeline.py`）作為回歸防護網；對外 API 契約（`ChatResponseDTO`）完全不變；可用 feature flag 讓 Graph 版本與現行 inline 版本並存。

## 為什麼其他流程不列入本次候選

- **F2/F3（標準 Chat）**：本質是線性 pipeline（validate → enhance → cache-check → search → generate），唯一分支是快取命中短路，不構成「條件路由」的複雜度；這條路徑是最高流量的生產路徑，任何重構的風險/收益比都不利。維持現狀。
- **F5/F6（VoltAgent Supervisor）**：VoltAgent 框架的 `subAgents` delegation 與 `inputMiddlewares`/`outputMiddlewares` 鏈**本身就是**一種 Node/Edge 抽象（middleware = deterministic/LLM node，subAgent delegation = conditional edge）。在此之上再疊一層自製 Graph 框架，只會增加維護面而不會增加能力。若未來要做「Human-in-the-loop 批准」或「跨 session 的長時間 workflow」，可評估用 durable engine 包住整個 VoltAgent 呼叫，但這超出目前需求。
- **F7（Ingestion）**：目前是 CLI 觸發的批次 ETL，步驟固定、無條件分支、無需人工介入；資料量尚小（YouTube 逐字稿），rewrite 成本不划算。列為 Phase N+1 觀察對象（若未來加入「OCR 失敗 → 人工複核」或「多來源並行下載」才重新評估）。
- **F1/F8**：明確排除的 CRUD 類型，符合任務要求的「不得把普通 CRUD 改成 Agent」。
- **F9**：Eval 腳本是離線工具，不在 production 請求路徑上，不需要 checkpoint/resume。

## Next candidate（供下一階段參考，不在本次範圍內執行）

若 F4 Graph 化驗證成功且需要擴充：**VoltAgent 的 WebSearchAgent 路徑**（即時資訊查詢 + 可能的高風險內容發布）具備更高的 Human-in-the-loop 需求（例如：對外發布內容前需要批准），屆時建議評估在 VoltAgent 層之上或之下引入具持久化 checkpoint 的 Graph/Workflow 層。詳見 `docs/graph-migration-plan.md` 的「Next Migration Step」。
