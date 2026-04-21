# Career Analyst KB Request Flow

這份文件描述目前 repo 實際運作中的問答架構，分成兩條路徑：

- 直接呼叫 FastAPI backend
- 經過 VoltAgent 再呼叫 FastAPI backend

重點先講清楚：

- 真正的 RAG engine 在 `services/kb-api/src/*` 的 Python backend
- `services/voltagent-career/*` 是 orchestration layer，不直接做 Milvus 檢索
- 若經過 VoltAgent，最後仍是呼叫 FastAPI 的 `/api/chat/query/sync`

## 1. 元件分工

### Python backend: `services/kb-api/*`

負責：

- HTTP API
- 問答流程協調
- embedding
- Milvus dense retrieval
- BM25 sparse retrieval
- RRF fusion
- 組 context
- 呼叫 backend LLM 生成答案
- 回傳 citations / sources

核心檔案：

- [chat.py](/Users/liyuncheng/workspace/me/career-analyst-kb/services/kb-api/src/api/routers/chat.py)
- [dependencies.py](/Users/liyuncheng/workspace/me/career-analyst-kb/services/kb-api/src/api/dependencies.py)
- [chat_service.py](/Users/liyuncheng/workspace/me/career-analyst-kb/services/kb-api/src/application/services/chat_service.py)
- [hybrid_search.py](/Users/liyuncheng/workspace/me/career-analyst-kb/services/kb-api/src/rag/hybrid_search.py)
- [retriever.py](/Users/liyuncheng/workspace/me/career-analyst-kb/services/kb-api/src/rag/retriever.py)

### VoltAgent layer: `services/voltagent-career/*`

負責：

- agent routing
- sub-agent orchestration
- 用 tool 呼叫 Career KB API
- 將 backend 回答包成 agent 回覆

核心檔案：

- [supervisor.ts](/Users/liyuncheng/workspace/me/career-analyst-kb/services/voltagent-career/src/agents/supervisor.ts)
- [query-career-kb.ts](/Users/liyuncheng/workspace/me/career-analyst-kb/services/voltagent-career/src/tools/query-career-kb.ts)
- [kb-client.ts](/Users/liyuncheng/workspace/me/career-analyst-kb/services/voltagent-career/src/tools/kb-client.ts)

## 2. 直接呼叫 Backend 的 Flow

適用情境：

- 前端直接打 FastAPI
- 管理工具或測試腳本直接呼叫 `/api/chat/query` 或 `/api/chat/query/sync`

### High-Level Flow

```text
client
-> FastAPI /api/chat/query or /api/chat/query/sync
-> ChatService
-> input validation
-> query enhancement
-> embed query
-> HybridSearchEngine
   -> Milvus dense search
   -> BM25 sparse search
   -> RRF fusion
-> top-k chunks
-> build context
-> backend LLM generation
-> answer + sources
```

### Step-by-Step

1. Client 呼叫 chat API。

- 串流端點：`POST /api/chat/query`
- 同步端點：`POST /api/chat/query/sync`

對應實作在 [chat.py](/Users/liyuncheng/workspace/me/career-analyst-kb/services/kb-api/src/api/routers/chat.py)。

2. Router 將請求交給 `ChatService`。

`ChatService` 由 [dependencies.py](/Users/liyuncheng/workspace/me/career-analyst-kb/services/kb-api/src/api/dependencies.py) 建立，會注入：

- `MilvusRetriever`
- `HybridSearchEngine`
- `EmbeddingService`
- `PromptOptimizer`
- `SecurityGuardrail`
- LLM provider 建出的 backend LLM

3. `ChatService.stream_answer()` 執行問答主流程。

對應實作在 [chat_service.py](/Users/liyuncheng/workspace/me/career-analyst-kb/services/kb-api/src/application/services/chat_service.py)。

主要步驟：

- 驗證與清洗輸入
- 強化 query
- 將 query 轉 embedding
- 呼叫 search engine
- 組 context
- 加上 system prompt 與對話歷史
- 呼叫 LLM 串流生成
- 儲存 session / message

4. `HybridSearchEngine` 執行檢索。

對應實作在 [hybrid_search.py](/Users/liyuncheng/workspace/me/career-analyst-kb/services/kb-api/src/rag/hybrid_search.py)。

它不是純向量搜尋，而是 hybrid RAG：

- dense retrieval: `MilvusRetriever`
- sparse retrieval: `BM25Okapi`
- rank fusion: `RRF`

5. `MilvusRetriever` 負責 dense retrieval。

對應實作在 [retriever.py](/Users/liyuncheng/workspace/me/career-analyst-kb/services/kb-api/src/rag/retriever.py)。

行為：

- 去 Milvus collection `career_kb` 查詢 embedding
- 回傳 chunk metadata
- 支援 `topic` filter，會轉成 Milvus `expr`

6. `HybridSearchEngine` 合併 dense 與 BM25 結果。

目前邏輯：

- dense 先取 `dense_top_k=50`
- BM25 取關鍵字候選
- 用 `RRF` 合併兩路排名
- 最後回傳 `final_top_k=5`

7. `ChatService` 把檢索結果組成 context。

目前 context 會帶影片引用資訊，包含：

- `video_title`
- `url`
- `upload_date`

8. backend LLM 根據 context 生成答案。

也就是說，最終回答不是 VoltAgent 直接憑空生成，而是 Python backend 在有檢索上下文時產生 grounded answer。

9. API 回傳答案與 sources。

- `/query` 走 SSE 串流 token
- `/query/sync` 回傳完整 JSON

## 3. 經過 VoltAgent 的 Flow

適用情境：

- 前端先打 `services/voltagent-career`
- 希望由 supervisor agent 判斷問題類型，再轉給對應 agent

### High-Level Flow

```text
client
-> VoltAgent
-> supervisor agent
-> queryCareerKB tool
-> FastAPI /api/chat/query/sync
-> ChatService
-> Hybrid RAG
-> backend LLM grounded answer
-> VoltAgent formats final reply
-> client
```

### Step-by-Step

1. Client 呼叫 VoltAgent。

VoltAgent server entry 在 [index.ts](/Users/liyuncheng/workspace/me/career-analyst-kb/services/voltagent-career/src/index.ts)。

2. `CareerLeadAgent` 判斷問題類型。

對應實作在 [supervisor.ts](/Users/liyuncheng/workspace/me/career-analyst-kb/services/voltagent-career/src/agents/supervisor.ts)。

可能的去向：

- 直接用 `queryCareerKB`
- 路由到 `ResumeAgent`
- 路由到 `InterviewAgent`
- 路由到 `CareerPlanAgent`
- 路由到 `SalaryAgent`

3. Agent 呼叫 `queryCareerKB` tool。

tool 定義在 [query-career-kb.ts](/Users/liyuncheng/workspace/me/career-analyst-kb/services/voltagent-career/src/tools/query-career-kb.ts)。

4. `queryCareerKB` 透過 `fetchCareerKB()` 呼叫 backend。

HTTP client 在 [kb-client.ts](/Users/liyuncheng/workspace/me/career-analyst-kb/services/voltagent-career/src/tools/kb-client.ts)。

目前會打：

- `POST /api/chat/query/sync`

並附上：

- `Authorization: Bearer ${CAREER_API_TOKEN}`
- `question`
- `session_id`
- optional `topic`

5. FastAPI backend 執行真正的 RAG。

這部分和「直接呼叫 Backend 的 Flow」完全相同：

- `ChatService`
- `EmbeddingService`
- `HybridSearchEngine`
- `MilvusRetriever`
- `BM25`
- `RRF`
- backend LLM generation

6. VoltAgent 收到 backend 的 `answer + sources` 後再整理回覆。

因此 VoltAgent 的角色是：

- 問題分類
- agent routing
- tool orchestration
- 回覆包裝

不是：

- 直接從 Milvus 查資料
- 直接執行核心 RAG 檢索流程

## 4. Topic Filter 在哪裡生效

`topic` 目前會一路往下傳：

- API request DTO
- `ChatService`
- `HybridSearchEngine.search(..., topic=topic)`
- `MilvusRetriever.search(..., topic=topic)`

效果：

- Milvus dense search 會用 metadata filter 篩 section
- BM25 若指定 topic，會在該 topic 子語料上重建 scoped index 再搜尋

這表示 topic filter 不是只影響 prompt，而是直接影響 retrieval scope。

## 5. 一句話總結

目前系統的核心邏輯是：

```text
VoltAgent = orchestration layer
Python backend = actual RAG engine
```

如果沒有 VoltAgent：

```text
client -> FastAPI -> Hybrid RAG -> backend LLM
```

如果有 VoltAgent：

```text
client -> VoltAgent -> FastAPI -> Hybrid RAG -> backend LLM
```

## 6. 補充說明

- `services/voltagent-career/*` 和 `services/kb-api/src/*` 會互相溝通，但方式是 HTTP，不是直接 import code
- 真正的知識來源在 Milvus / transcript chunks，不在 VoltAgent prompt 本身
- Phase 4 若前端改接 VoltAgent，RAG 核心仍然會留在 Python backend，不需要搬到 TypeScript
