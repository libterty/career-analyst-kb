# RAG 系統入門說明

> 給不熟悉 RAG 的人看的快速概覽。深入技術細節請參考 [rag-deep-dive.md](./rag-deep-dive.md)。

---

## 這個 RAG 系統分兩大流程

---

## 流程一：把文本存進向量資料庫（Ingestion）

```
PDF / DOCX 文件
       ↓
   [1] 解析 (DocumentParser)
       ↓
   [2] 切塊 (SmartChunker)
       ↓
   [3] 嵌入向量 (EmbeddingService)
       ↓
   [4] 儲存到 Milvus 向量資料庫
```

### [1] 解析文件 — `src/ingestion/pdf_parser.py`

把 PDF/DOCX 讀成純文字，並計算 `doc_hash`（文件指紋，用來識別是否重複匯入）。

### [2] 切塊 — `src/ingestion/chunker.py`

文本不能整篇丟進去，要切成小段落（Chunk）。這個系統針對一貫道典籍特別設計了分隔點：

```python
_YIGUANDAO_SEPARATORS = [
    r"\n第X章",   # 優先從章節分割
    r"\n第X節",
    r"\n(1)",     # 條目
    "\n\n",       # 段落
    "\n",         # 換行
]
```

**切塊規則：**
- 每塊最多 **512 tokens**（約 600-800 中文字）
- 相鄰塊重疊 **64 tokens**（保留上下文連貫性，避免答案被切斷）
- 每塊記錄：`chunk_id`、`source`（來源文件）、`section`（章節）、`content`（正文）

### [3] 嵌入向量 — `src/ingestion/embedder.py`

這是 RAG 的核心魔法：

```
"三寶是什麼" 這段文字
       ↓  Embedding Model（nomic-embed-text 或 OpenAI）
[0.12, -0.34, 0.88, ...]  ← 768 維的浮點數向量
```

**語意相近的文字，向量方向也會相近**。這就是後來能做語意搜尋的原因。

### [4] 儲存到 Milvus — `src/ingestion/embedder.py`

Milvus 是向量資料庫，建立時設定了 **IVF_FLAT + Inner Product** 索引：

```
每筆資料 = {
  chunk_id,        # 唯一識別碼
  doc_hash,        # 文件指紋
  source,          # 來源文件名
  section,         # 章節名
  content,         # 原文文字（最多 4096 字）
  token_count,     # token 數量
  embedding,       # 向量 [float × 768]
}
```

`nlist=128` 是索引參數，把向量空間分成 128 個群組，加速搜尋時不用比較全部向量。

---

## 流程二：使用者問問題 → 搜尋 → 生成回答

```
使用者問題
       ↓
   [1] 查詢優化 (PromptOptimizer)
       ↓
   [2] 問題向量化 (embed_query)
       ↓
   [3] 向量搜尋 Milvus → 取前 20 筆
       ↓
   [4] BM25 關鍵字搜尋（在那 20 筆上）
       ↓
   [5] RRF 融合打分，取前 5 筆
       ↓
   [6] 組裝 Prompt → 送 LLM 生成回答
       ↓
   串流輸出給使用者
```

### [1] 查詢優化 — `src/finetuning/prompt_optimizer.py`

先把使用者用語正規化，把俗稱換成標準術語：

```python
ALIAS_MAP = {
    "老母": "無極老母",
    "彌勒": "彌勒祖師",
    ...
}
# "老母的慈悲" → "無極老母的慈悲"
```

這樣搜尋時更容易找到典籍裡的標準寫法。

### [2] + [3] 向量搜尋（Dense Search）— `src/rag/retriever.py`

把問題轉成向量，在 Milvus 裡用 **Inner Product（內積）** 找最相近的 20 筆：

```
問題向量 · 文本向量 = 相似度分數
分數越高 = 語意越接近
```

### [4] BM25 關鍵字搜尋（Sparse Search）— `src/rag/hybrid_search.py`

在那 20 筆候選結果上，再跑傳統的 **BM25 關鍵字比對**：

```
BM25 = 關鍵字出現頻率 × 文件長度權重
```

BM25 特別擅長找「精確用詞」，彌補向量搜尋的不足（例如搜特定人名、術語）。

### [5] RRF 融合打分 — `src/rag/hybrid_search.py`

兩種搜尋各自排名，用 **Reciprocal Rank Fusion (RRF)** 融合：

```
RRF 分數 = 1/(60 + 向量排名) + 1/(60 + BM25排名)
```

舉例：

| 段落 | 向量排名 | BM25 排名 | RRF 總分 |
|------|---------|----------|---------|
| A | #1 → 0.0164 | #3 → 0.0159 | 0.0323 |
| B | #2 → 0.0161 | #1 → 0.0164 | **0.0325** ← 第一 |

`k=60` 是常數，讓排名靠前的塊貢獻更大但不壓過其他，兩路結果都兼顧。最終取分數最高的 **5 筆**。

### [6] 組裝 Prompt + LLM 生成 — `src/rag/pipeline.py`

```
System Prompt = 你是道輝助理 + 【參考段落】top-5 原文
HumanMessage  = 使用者問題
```

LLM 只能依據這 5 段原文回答，有效防止「幻覺」（hallucination）。系統保留最近 **10 輪對話記憶**，讓問答可以連貫。

---

## 整體架構總結

```
                    ┌─── 存入 ───────────────────────────┐
                    │  PDF → 切塊 → 向量化 → Milvus DB   │
                    └────────────────────────────────────┘

使用者問題
    ↓ 術語正規化
    ↓ 轉向量
    ├── Dense Search（語意相似）──┐
    │   Milvus 取前 20 筆         ├→ RRF 融合 → 前 5 筆 → LLM → 回答
    └── Sparse BM25（關鍵字精確）─┘
        在 20 筆候選上計算
```

**關鍵設計重點：**
- **Hybrid Search** — 語意 + 關鍵字，兩種優點都保留
- **RRF** — 不依賴分數絕對值，只看排名來融合，更穩定
- **chunk_overlap 64 tokens** — 避免答案剛好在切塊邊界被切斷
- **典籍專屬分隔符** — 尊重原文章節結構，不在章節中間亂切
