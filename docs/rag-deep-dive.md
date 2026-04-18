# RAG 深度解析 — 道輝知識庫問答引擎

> 本文件詳細說明 `src/rag/` 的運作原理，從概念到程式碼逐層剖析。

---

## 目錄

1. [什麼是 RAG？](#1-什麼是-rag)
2. [為什麼需要 RAG？](#2-為什麼需要-rag)
3. [RAG 六步完整流程](#3-rag-六步完整流程)
4. [Step 1 — 查詢強化（Query Enhancement）](#4-step-1--查詢強化query-enhancement)
5. [Step 2 — 查詢向量化（Embedding）](#5-step-2--查詢向量化embedding)
6. [Step 3 — 混合搜索（Hybrid Search）](#6-step-3--混合搜索hybrid-search)
7. [Step 4 — 構建 Context](#7-step-4--構建-context)
8. [Step 5 — LLM 串流生成](#8-step-5--llm-串流生成)
9. [Step 6 — 對話記憶](#9-step-6--對話記憶)
10. [向量資料庫原理（Milvus）](#10-向量資料庫原理milvus)
11. [文件匯入（Ingestion）與 RAG 的關係](#11-文件匯入ingestion-與-rag-的關係)
12. [安全層整合](#12-安全層整合)
13. [程式碼索引](#13-程式碼索引)

---

## 1. 什麼是 RAG？

**RAG = Retrieval-Augmented Generation（檢索增強生成）**

RAG 是一種 AI 問答架構，核心思想只有一句話：

> **先從知識庫「找」出相關資料，再讓 LLM「看著資料」回答。**

```
傳統 LLM：
  問題 ──→ LLM（只靠訓練時的記憶）──→ 答案
           ↑ 可能幻覺、可能過時

RAG：
  問題 ──→ [搜索知識庫] ──→ 相關段落
        └─────────────────────────────→ LLM（看著段落回答）──→ 答案
                                        ↑ 有所本、可追溯、即時更新
```

---

## 2. 為什麼需要 RAG？

### 純 LLM 的三大問題

| 問題 | 說明 | 一貫道場景 |
|------|------|-----------|
| **幻覺（Hallucination）** | 模型捏造看似合理但錯誤的內容 | 捏造不存在的典籍段落或儀式 |
| **知識截止（Cutoff）** | 訓練資料有時間限制 | 新增的道場規範、活動公告無法回答 |
| **無法追溯** | 無法知道答案來源 | 道親無法確認答案是否出自典籍 |

### RAG 的解法

- **幻覺**：System Prompt 明確指示「未有記載請說明，切勿捏造」，且每次都附上原典段落
- **知識截止**：新增文件重新匯入即可，不需重新訓練模型
- **可追溯**：`get_sources()` 回傳段落來源文件與章節，前端可顯示引用

---

## 3. RAG 六步完整流程

```
使用者問：「三寶的意義是什麼？」
          │
          ▼
┌─────────────────────────────────────────┐
│  Phase 4 安全防護（進入 RAG 前）         │
│  SecurityGuardrail.check_input()        │
│  ✓ 通過 → 繼續  ✗ 拒絕 → HTTP 400      │
└──────────────────┬──────────────────────┘
                   │
          ┌────────▼────────┐
          │  RAGPipeline    │   src/rag/pipeline.py
          │                 │
          │  1. 查詢強化    │ ← PromptOptimizer
          │  2. 向量化      │ ← EmbeddingService
          │  3. 混合搜索    │ ← HybridSearchEngine
          │  4. 構建Context │
          │  5. LLM 生成   │ ← build_llm()（Ollama / Grok）
          │  6. 儲存記憶    │ ← ConversationBufferWindowMemory
          └────────┬────────┘
                   │
          ┌────────▼────────┐
          │ SecurityGuardrail│
          │ .sanitize_output()│  輸出消毒（逐 token）
          └────────┬────────┘
                   │
          ┌────────▼────────┐
          │  SSE 串流輸出   │   data: token\n\n
          │  → 前端即時顯示 │   data: [DONE]\n\n
          └─────────────────┘
```

---

## 4. Step 1 — 查詢強化（Query Enhancement）

**檔案：** `src/finetuning/prompt_optimizer.py`

### 目的

一貫道有許多專屬術語，一般人可能用俗稱或不標準的說法提問。查詢強化做兩件事：

1. **別名正規化**：將俗稱替換為標準術語（ALIAS_MAP）
2. **術語定義注入**：若問題含有領域術語，在 System Prompt 前附上術語定義

### 範例

```python
# ALIAS_MAP（src/finetuning/glossary.py）
ALIAS_MAP = {
    "叩頭": "叩首",
    "天盤": "天道",
    # ...
}

# 使用者問：「叩頭有什麼意義？」
# 強化後：「叩首有什麼意義？」   ← 使用標準術語
#          + 附上「叩首：...定義...」
```

### 效果

搜索時使用標準術語，能找到更多相關典籍段落（因為典籍用的是標準術語）。

### 程式碼（`pipeline.py:55`）

```python
# Step 1：強化查詢
enhanced_query = self._prompt_optimizer.enhance_query(question)
```

---

## 5. Step 2 — 查詢向量化（Embedding）

**檔案：** `src/ingestion/embedder.py`，`src/core/llm_factory.py`

### 什麼是 Embedding？

Embedding 是把一段文字轉換成一組數字（向量），讓電腦能計算「語意相似度」。

```
「三寶的意義」   → [0.12, -0.45, 0.89, ..., 0.33]  （768 個數字）
「三寶是什麼」   → [0.11, -0.43, 0.91, ..., 0.31]  （方向非常接近）
「狗為什麼叫」   → [-0.78, 0.22, -0.15, ..., 0.55] （方向差很多）
```

語意相近的文字，其向量在高維空間中方向接近（Inner Product 接近 1）。

### 本專案的 Embedding 模型

預設使用 `nomic-embed-text`（Ollama 本機運行）：
- 向量維度：**768**
- 語言支援：中英文均可
- 備選：`mxbai-embed-large`（1024 維，效果更好但更大）

### 程式碼（`pipeline.py:58`）

```python
# Step 2：將強化後的查詢轉成向量
query_embedding = self._embedder.embed_query(enhanced_query)
# 回傳：list[float]，長度 768
```

---

## 6. Step 3 — 混合搜索（Hybrid Search）

**檔案：** `src/rag/hybrid_search.py`，`src/rag/retriever.py`

這是整個 RAG 系統的**核心差異點**，也是效果好壞的關鍵。

### 6.1 為什麼不只用向量搜索？

向量搜索（語意搜索）的盲點：

```
查詢：「壇主的職責」

向量搜索可能找到：
  ✓「道場負責人的工作內容」（語意相近，但沒用「壇主」這個詞）
  ✓「佛堂的管理事項」
  ✗「壇主應每日點燃香爐、帶領道親課誦」（含精確關鍵字，但向量距離稍遠）
```

BM25 關鍵字搜索的盲點：

```
查詢：「如何踐行十條大願」

BM25 只找含「如何」「踐行」「十條大願」的段落
  ✗「十大誓願的修行方法」（語意相同，但用字不同，BM25 找不到）
```

**混合搜索：兩者結合，互補盲點。**

---

### 6.2 混合搜索三步驟

#### Step A — 向量搜索廣撒網（`retriever.py`）

```python
# MilvusRetriever.search()
results = self._collection.search(
    data=[query_embedding],       # 查詢向量
    anns_field="embedding",       # 搜索欄位
    param={
        "metric_type": "IP",      # Inner Product（內積）≈ 歸一化後的 cosine 相似度
        "params": {"nprobe": 16}  # 搜索的 cluster 數（越大越準確但越慢）
    },
    limit=20,                     # 取 top-20（故意多取，供後續 BM25 重排序）
    output_fields=["chunk_id", "source", "section", "content", "token_count"],
)
```

**為什麼取 20 而不是 5？** 因為後續的 BM25 需要在這 20 個候選中重排序，若只取 5，BM25 就沒有發揮空間。

#### Step B — BM25 對候選重排序（`hybrid_search.py:49-63`）

```python
# 對 20 個向量搜索結果的文字內容做 BM25 計算
corpus = [r.content for r in dense_results]          # 20 個段落
tokenized_corpus = [_tokenize_zh(doc) for doc in corpus]  # jieba 分詞
bm25 = BM25Okapi(tokenized_corpus)

tokenized_query = _tokenize_zh(query)               # 查詢詞分詞
bm25_scores = bm25.get_scores(tokenized_query)      # 每個段落的關鍵字分數
```

**為什麼不對全庫做 BM25？**
全庫可能有幾千、幾萬個段落，每次搜索都做 BM25 非常慢。
先用向量搜索縮小到 20 個候選，再做 BM25，兼顧速度與效果。

**中文分詞（`hybrid_search.py:14-20`）：**

```python
def _tokenize_zh(text: str) -> list[str]:
    try:
        import jieba
        return list(jieba.cut(text))   # 優先用 jieba 詞語切分
    except ImportError:
        return list(text)              # fallback：字元切分
```

jieba 能把「修行方法」切成 `["修行", "方法"]`，BM25 才能準確匹配。

#### Step C — RRF 融合最終排名（`hybrid_search.py:64-87`）

**RRF = Reciprocal Rank Fusion（倒數排名融合）**

RRF 的核心公式：

```
每個段落的最終分數 = Σ  1 / (k + rank_i)

k = 60（常數，平滑化用，防止排名第 1 的結果分數過高）
rank_i = 該段落在第 i 個排名列表中的名次（從 1 開始）
```

**具體計算範例：**

假設向量搜索 top-5 與 BM25 top-5 如下：

| 段落 | 向量排名 | 向量分 | BM25排名 | BM25分 | **RRF總分** |
|------|---------|--------|---------|--------|------------|
| A — 三寶總說 | 1 | 1/(60+1)=**0.01639** | 3 | 1/(60+3)=0.01587 | **0.03226** |
| B — 三寶儀式詳說 | 2 | 1/(60+2)=0.01613 | 1 | 1/(60+1)=**0.01639** | **0.03252** ← 第一 |
| C — 求道流程 | 3 | 1/(60+3)=0.01587 | 2 | 1/(60+2)=0.01613 | **0.03200** |
| D — 道場規範 | 4 | 0.01563 | 5 | 0.01538 | 0.03101 |
| E — 教義概說 | 5 | 0.01538 | 4 | 0.01563 | 0.03101 |

結果：B（三寶儀式詳說）在 BM25 關鍵字匹配最好，最終排名第一，勝過向量排名第一的 A。

**為什麼 k=60？**
k 是平滑係數。k 越大，排名靠後的結果對總分影響越小（差距被壓縮）。
k=60 是學術論文中的常見推薦值（Cormack et al., 2009），能在「頭部結果重要」與「尾部結果也有貢獻」之間取得平衡。

#### 最終輸出

```python
# 取 RRF 分數最高的 top-5
results = ranked[:self.final_top_k]   # final_top_k = 5
```

---

### 6.3 搜索參數設定

| 參數 | 預設值 | 說明 | 調整建議 |
|------|--------|------|---------|
| `dense_top_k` | 20 | 向量搜索召回數 | 知識庫小可降至 10；大可提高至 50 |
| `final_top_k` | 5 | 最終進入 LLM 的段落數 | 5 是 context 長度與準確度的平衡點 |
| `RRF_K` | 60 | RRF 平滑係數 | 通常不需調整 |
| `nprobe` | 16 | Milvus 搜索 cluster 數 | 提高 → 更準確但更慢 |

---

## 7. Step 4 — 構建 Context

**檔案：** `src/rag/pipeline.py:94-102`

將 top-5 搜索結果格式化為 LLM 可讀的文字：

```python
@staticmethod
def _build_context(results: list[SearchResult]) -> str:
    parts = []
    for i, r in enumerate(results, start=1):
        section_label = f"【{r.section}】" if r.section else ""
        parts.append(f"[{i}] {section_label}{r.content}")
    return "\n\n".join(parts)
```

**輸出範例：**

```
[1] 【第一章】三寶者，天道之根本也。其一曰玄關一竅，為天命之所寄...
[2] 【第三節】求道者需明三寶之義，方能入道修行。三寶者乃...
[3] 壇主引導道親叩首，以三寶為信物，示誠心於天...
[4] 【十條大願第二願】願深明三寶之義，日日懺悔，時時精進...
[5] 五教聖人皆以同理傳道，三寶之意通貫儒釋道耶回...
```

這個 context 會直接放入 System Prompt，讓 LLM「看著這 5 個段落」回答。

---

## 8. Step 5 — LLM 串流生成

**檔案：** `src/rag/pipeline.py:65-81`，`src/core/llm_factory.py`

### System Prompt 設計

```python
_SYSTEM_PROMPT = """你是一位熟悉一貫道教義的智慧助理，名為「道輝」。
請依據以下從典籍中擷取的參考段落，以誠摯、謙遜的口吻回答問題。
若參考段落中未包含相關資訊，請誠實說明「典籍中未有明確記載」，切勿自行捏造。
回答應以繁體中文撰寫，語調莊重而親切。

【參考段落】
{context}          ← 由 _build_context() 填入
"""
```

三個重要指令：
1. **角色設定**：道輝助理，熟悉教義
2. **忠實性約束**：只依據參考段落，不捏造
3. **格式要求**：繁體中文，莊重親切

### 訊息結構

```python
messages = [
    SystemMessage(content=_SYSTEM_PROMPT.format(context=context)),  # 角色 + 典籍段落
]
if history:
    messages.append(AIMessage(content=history))   # 歷史對話（最近 10 輪）
messages.append(HumanMessage(content=question))   # 使用者當前問題
```

### 串流輸出（Streaming）

```python
# astream() 逐 token 異步輸出
async for chunk in self._llm.astream(messages):
    token = chunk.content
    full_response += token
    yield token    # 每個 token 立即送到前端 → 使用者看到字逐漸出現
```

**為什麼用 Streaming？**
Gemma3:12b 生成一個完整回答可能需要 10-30 秒。串流讓使用者看到回答逐字出現，體驗更好。

### LLM 參數

| 參數 | 值 | 說明 |
|------|-----|------|
| `temperature` | 0.3 | 較低溫度 → 回答更穩定、不亂發揮 |
| `streaming` | True | 啟用串流 |

---

## 9. Step 6 — 對話記憶

**檔案：** `src/rag/pipeline.py:46,65,81`

```python
# 初始化：保留最近 10 輪對話
self._memory = ConversationBufferWindowMemory(k=10)

# 每次問答後儲存
self._memory.save_context(
    {"input": question},
    {"output": full_response}
)

# 下次問答時讀取
history = self._memory.load_memory_variables({}).get("history", "")
```

### 多輪對話效果

```
第一輪：「三寶是什麼？」
  → 系統回答三寶的定義

第二輪：「它和求道有什麼關係？」
  → 「它」指的是三寶 ← 記憶讓系統理解指代關係
```

### 目前限制

- 記憶儲存在**記憶體**中（重啟後消失）
- 以 `session_id` 區分，但目前共用同一個 `RAGPipeline` 實例（singleton）
- 正式環境建議用 Redis 或 PostgreSQL 持久化記憶

---

## 10. 向量資料庫原理（Milvus）

### 為什麼不用 PostgreSQL 做向量搜索？

PostgreSQL 也有 pgvector 擴充，但：
- Milvus 針對大規模向量搜索做了深度優化（IVF、HNSW 等索引）
- 全庫搜索效率遠高於 PostgreSQL 的線性掃描
- 本專案典籍量可能較小（差異不大），但架構上更具擴展性

### Milvus IVF_FLAT 索引

```python
col.create_index(
    "embedding",
    {
        "index_type": "IVF_FLAT",   # Inverted File Index（倒排索引）
        "metric_type": "IP",         # Inner Product（內積）
        "params": {"nlist": 128},    # 分成 128 個 cluster
    },
)
```

**IVF_FLAT 搜索過程：**
1. 將所有向量用 k-means 分成 128 個 cluster
2. 搜索時只看查詢向量最近的 `nprobe=16` 個 cluster
3. 在這 16 個 cluster 內找最相似的向量
4. 大幅減少比較次數（128 個 cluster 只看 16 個）

### Inner Product（IP）vs Cosine Similarity

IP 計算兩個向量的點積：`a · b = |a||b|cos(θ)`

當兩個向量都已**歸一化**（長度為 1）時，IP = cosine similarity。
nomic-embed-text 輸出的向量預設歸一化，所以 IP ≈ cosine similarity。

---

## 11. 文件匯入（Ingestion）與 RAG 的關係

RAG 能找到什麼，完全取決於匯入了什麼。

```
【匯入時】（一次性，離線）

典籍 PDF/DOCX
    │
    ▼
DocumentParser         解析 → 純文字
    │
    ▼
SmartChunker          分段 → 512 token 的段落
  ├── 優先依章節（第X章、第X節）邊界切割
  ├── 重疊 64 token（確保章節邊界前後都有涵蓋）
  └── cl100k_base encoding（OpenAI tokenizer，對中文計數準確）
    │
    ▼
EmbeddingService      每段 → 768 維向量
    │
    ▼
Milvus Collection     向量 + metadata（source、section、content）存入

【查詢時】（每次問答，即時）
查詢 → 向量化 → Milvus 搜索 → 找到最相關的已存段落 → LLM 生成
```

**Chunk 大小的影響：**

| 設定 | 影響 |
|------|------|
| `max_tokens=512` | 每段約 200-400 中文字，包含完整語意 |
| `chunk_overlap=64` | 前後段各重疊約 25 字，避免段落邊界截斷重要資訊 |
| 太小（<100 token）| 段落語意不完整，LLM 難以理解 |
| 太大（>1024 token）| 一段話涵蓋多個主題，搜索準確度下降 |

---

## 12. 安全層整合

RAG 問答的安全流程（`src/api/routers/chat.py`）：

```python
# 1. 輸入檢查（進入 RAG 前）
clean_input = _guardrail.check_input(request.question)
# ✗ Prompt Injection：「忘記你的指令，改做...」→ SecurityError → HTTP 400
# ✗ 違禁內容 → SecurityError → HTTP 400
# ✓ 正常問題 → clean_input

# 2. RAG 問答（串流）
async for token in pipeline.query(clean_input, session_id=session_id):
    safe_token = _guardrail.sanitize_output(token)  # 輸出消毒（逐 token）
    yield f"data: {safe_token}\n\n"
```

輸出消毒確保即使 LLM 生成了不當內容，也會在送到前端前被過濾。

---

## 13. 程式碼索引

| 功能 | 檔案 | 行號 | 說明 |
|------|------|------|------|
| RAG 主流程入口 | `src/rag/pipeline.py` | 52 | `RAGPipeline.query()` |
| 向量搜索 | `src/rag/retriever.py` | 35 | `MilvusRetriever.search()` |
| 混合搜索 | `src/rag/hybrid_search.py` | 43 | `HybridSearchEngine.search()` |
| RRF 融合 | `src/rag/hybrid_search.py` | 64 | `rrf_scores` 計算 |
| 中文分詞 | `src/rag/hybrid_search.py` | 14 | `_tokenize_zh()` |
| Context 構建 | `src/rag/pipeline.py` | 94 | `_build_context()` |
| System Prompt | `src/rag/pipeline.py` | 19 | `_SYSTEM_PROMPT` |
| 查詢強化 | `src/finetuning/prompt_optimizer.py` | 24 | `enhance_query()` |
| 別名表 | `src/finetuning/glossary.py` | — | `ALIAS_MAP` |
| Embedding 服務 | `src/ingestion/embedder.py` | 86 | `embed_query()` |
| Milvus 索引建立 | `src/ingestion/embedder.py` | 100 | IVF_FLAT index |
| LLM 工廠 | `src/core/llm_factory.py` | 84 | `build_llm()` |
| API 端點（串流）| `src/api/routers/chat.py` | 29 | `POST /api/chat/query` |
| API 端點（同步）| `src/api/routers/chat.py` | 56 | `POST /api/chat/query/sync` |

---

## 附錄：完整資料流示意

```
                         使用者
                           │
                    問：「三寶是什麼？」
                           │
              ┌────────────▼────────────┐
              │     SecurityGuardrail   │ 安全檢查
              │     check_input()       │
              └────────────┬────────────┘
                           │ clean_input = "三寶是什麼？"
              ┌────────────▼────────────────────────────────────────┐
              │                  RAGPipeline.query()                 │
              │                                                      │
              │  ┌──────────────────────────────────────────────┐   │
              │  │ Step 1: PromptOptimizer.enhance_query()       │   │
              │  │ "三寶是什麼？"                                │   │
              │  │    → ALIAS_MAP 比對（無別名需正規化）         │   │
              │  │    → enhanced_query = "三寶是什麼？"         │   │
              │  └──────────────────────┬───────────────────────┘   │
              │                         │                            │
              │  ┌──────────────────────▼───────────────────────┐   │
              │  │ Step 2: EmbeddingService.embed_query()        │   │
              │  │ "三寶是什麼？"                                │   │
              │  │    → Ollama nomic-embed-text                  │   │
              │  │    → [0.12, -0.45, ..., 0.33]（768 維）      │   │
              │  └──────────────────────┬───────────────────────┘   │
              │                         │ query_embedding            │
              │  ┌──────────────────────▼───────────────────────┐   │
              │  │ Step 3: HybridSearchEngine.search()           │   │
              │  │                                               │   │
              │  │  A. MilvusRetriever.search(query_embedding)   │   │
              │  │     IVF_FLAT + IP → top-20 語意相近段落       │   │
              │  │                                               │   │
              │  │  B. BM25Okapi(top-20 段落文字)                │   │
              │  │     jieba 分詞 + 關鍵字匹配                   │   │
              │  │     → 每段落 BM25 分數                        │   │
              │  │                                               │   │
              │  │  C. RRF 融合                                  │   │
              │  │     score = 1/(60+向量排名) + 1/(60+BM25排名)│   │
              │  │     → 取 top-5 最終結果                       │   │
              │  └──────────────────────┬───────────────────────┘   │
              │                         │ search_results[5]          │
              │  ┌──────────────────────▼───────────────────────┐   │
              │  │ Step 4: _build_context()                      │   │
              │  │ [1]【第一章】三寶者，天道之根本也...          │   │
              │  │ [2]【第三節】求道者需明三寶之義...            │   │
              │  │ [3] 壇主引導道親叩首，以三寶為信物...        │   │
              │  │ [4]【十條大願第二願】願深明三寶之義...       │   │
              │  │ [5] 五教聖人皆以同理傳道，三寶之意...        │   │
              │  └──────────────────────┬───────────────────────┘   │
              │                         │ context                    │
              │  ┌──────────────────────▼───────────────────────┐   │
              │  │ Step 5: LLM.astream()                         │   │
              │  │ SystemMessage(你是道輝 + 【參考段落】context) │   │
              │  │ AIMessage(歷史對話，最近10輪)                 │   │
              │  │ HumanMessage("三寶是什麼？")                  │   │
              │  │     → Ollama Gemma3:12b 串流生成              │   │
              │  │     → yield token（逐字輸出）                 │   │
              │  └──────────────────────┬───────────────────────┘   │
              │                         │                            │
              │  ┌──────────────────────▼───────────────────────┐   │
              │  │ Step 6: memory.save_context()                 │   │
              │  │ 儲存本輪問答 → 下次問答可參考                 │   │
              │  └──────────────────────────────────────────────┘   │
              └────────────────────────────────────────────────────┘
                           │ AsyncIterator[str]（逐 token）
              ┌────────────▼────────────┐
              │ SecurityGuardrail       │ 輸出消毒
              │ sanitize_output(token)  │
              └────────────┬────────────┘
                           │ SSE: data: token\n\n
                         前端
                    （逐字顯示回答）
```
