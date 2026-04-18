# 道輝 完整文檔索引

> 一貫道內部知識庫系統 (yiguandao-kb) 官方文檔。

**上次更新：2026-03-20**

---

## 快速導覽

### 我是...

- **新手使用者** → [聊天介面使用](./features-and-deployment.md#聊天介面)
- **管理員** → [管理員面板指南](./features-and-deployment.md#管理員面板)
- **開發者** → [系統架構總覽](./architecture.md)
- **DevOps** → [部署檢查清單](./features-and-deployment.md#部署檢查清單)
- **API 集成方** → [API 參考](./api-reference.md)

---

## 文檔列表

### 1. 核心文檔

| 文件 | 內容 | 讀者 |
|------|------|------|
| [architecture.md](./architecture.md) | 系統分層架構、Tech Stack、目錄結構、API 路由、環境變數 | 開發者、架構師 |
| [architecture-solid.md](./architecture-solid.md) | Repository Pattern、Service 層、依賴注入、SOLID 原則應用 | 後端開發者 |
| [rag-intro.md](./rag-intro.md) | 給不熟悉 RAG 的人看的快速概覽 | 新手 |
| [rag-deep-dive.md](./rag-deep-dive.md) | RAG 六步完整流程、混合搜索、RRF 融合、Milvus 原理 | 深入學習 |

### 2. 功能與部署文檔

| 文件 | 內容 | 讀者 |
|------|------|------|
| [features-and-deployment.md](./features-and-deployment.md) | 核心功能、角色權限、聊天/管理介面、部署檢查清單、常見問題 | 所有人 |
| [api-reference.md](./api-reference.md) | 完整 API 端點文檔、請求/回應範例、認證流程、錯誤處理 | API 使用者 |

### 3. 資料庫文檔

| 文件 | 內容 | 讀者 |
|------|------|------|
| [db-schema.sql](./db-schema.sql) | PostgreSQL 表結構定義（使用者、文件、Session、訊息等） | DBA、開發者 |

---

## 按用途分類

### 我要快速上手

1. 閱讀根目錄 [README.md](../README.md) — 5 分鐘快速開始
2. 如果是開發環境，按 Step 1-5 操作
3. 訪問 `http://localhost` 開始聊天

### 我要理解系統架構

1. [架構總覽](./architecture.md) — 分層、Tech Stack、目錄結構
2. [SOLID 架構](./architecture-solid.md) — Repository Pattern、Service 層
3. [RAG 概覽](./rag-intro.md) — 快速概念介紹
4. [RAG 深度解析](./rag-deep-dive.md) — 深入技術細節

### 我要部署到生產

1. [部署檢查清單](./features-and-deployment.md#部署檢查清單)
2. [環境變數設定](./architecture.md#環境變數)
3. [效能調優建議](./features-and-deployment.md#效能最佳化建議)

### 我要調用 API

1. [API 參考](./api-reference.md) — 完整端點文檔
2. [API 範例實作](./api-reference.md#範例實作) — Python 客戶端範例

### 我要管理使用者和文件

1. [管理員面板指南](./features-and-deployment.md#管理員面板)
2. [使用者角色與權限](./features-and-deployment.md#使用者角色與權限)
3. [管理員 API](./api-reference.md#管理員admin)

### 我遇到了問題

→ 查看 [常見問題](./features-and-deployment.md#常見問題)

---

## 系統概覽

### 五個 Phase

```
Phase 1 — 文件匯入（Ingestion）
  PDF/DOCX/PPTX → 解析 → 分段 → 向量化 → Milvus
  詳見：architecture.md

Phase 2 — 智慧問答（RAG）
  查詢 → 術語強化 → 向量搜索 + BM25 融合 → LLM 生成 → 串流輸出
  詳見：rag-intro.md、rag-deep-dive.md

Phase 3 — 微調輔助（Fine-tuning）
  領域詞彙表、查詢優化、QA 資料集生成
  詳見：architecture.md

Phase 4 — 安全防護（Security）
  Prompt Injection 偵測、內容過濾、輸入/輸出消毒
  詳見：architecture.md

Phase 5 — Web 應用（FastAPI）
  認證、路由、API 端點、前端靜態檔案
  詳見：architecture.md、api-reference.md
```

### 核心組件

| 組件 | 位置 | 責任 |
|------|------|------|
| **API 層** | `src/api/` | HTTP 協議處理、路由掛載 |
| **服務層** | `src/application/` | 業務邏輯、Service 實作 |
| **Repository 層** | `src/infrastructure/repositories/` | 資料庫存取抽象 |
| **RAG 管道** | `src/rag/` | 混合搜索、LLM 生成 |
| **文件匯入** | `src/ingestion/` | 解析、分段、向量化 |
| **安全防護** | `src/security/` | Prompt Injection、內容過濾 |

---

## 環境與部署

### 開發環境

```bash
# 1. 複製 .env
cp .env.example .env

# 2. 啟動服務
cd docker && docker compose up -d

# 3. 訪問
open http://localhost
```

詳見：[README.md](../README.md)

### 生產環境

- 使用 Docker Compose + Nginx 反向代理
- 設定 HTTPS / SSL
- 環境變數通過 secrets 注入（不提交 .env）
- 啟用 Prometheus 監控

詳見：[部署檢查清單](./features-and-deployment.md#部署檢查清單)

---

## 關鍵技術棧

| 層 | 技術 | 說明 |
|-----|------|------|
| **LLM** | Ollama Gemma3:12b（預設）或 Grok / OpenAI | 語言模型 |
| **Embedding** | Ollama nomic-embed-text（768 dim） | 向量化模型 |
| **向量 DB** | Milvus 2.4 | 向量搜索 |
| **關聯 DB** | PostgreSQL 16 | 結構化資料 |
| **Web 框架** | FastAPI + Python 3.11 | 非同步 HTTP |
| **前端** | HTML + Tailwind CSS | Web UI |
| **容器化** | Docker + Docker Compose | 部署 |

---

## 常用命令

### 開發

```bash
# 啟動開發環境
cd docker && docker compose up -d

# 檢視日誌
docker compose logs -f app

# 進入容器
docker compose exec app bash

# 執行 migration
docker compose exec app alembic upgrade head

# 生成 QA 資料集
python3.11 scripts/generate_qa_dataset.py --file data/raw/典籍.pdf
```

### 測試

```bash
# 運行測試
pytest tests/ -v

# 測試覆蓋率
pytest tests/ --cov=src --cov-report=html
```

### 部署

```bash
# 構建鏡像
docker compose build

# 推送到 Registry
docker tag yiguandao-kb:latest myregistry.com/yiguandao-kb:latest
docker push myregistry.com/yiguandao-kb:latest
```

---

## 貢獻指南

1. 代碼遵循 SOLID 原則
2. 新功能需附帶單元測試（>80% 覆蓋率）
3. 修改文件結構需更新本文檔
4. Commit 訊息遵循 Conventional Commits 格式

詳見：[README.md](../README.md)

---

## 版本歷史

| 版本 | 日期 | 主要變更 |
|------|------|--------|
| 1.0.0 | 2026-03-20 | 初版發佈：RAG 系統、Session 管理、Admin 面板 |

---

## 獲取幫助

### 問題排查

1. **系統無法啟動** → 檢查 Docker 與 Ollama 是否運行
2. **文件匯入失敗** → 見 [常見問題 Q2](./features-and-deployment.md#q2-文件匯入失敗怎麼辦)
3. **記憶體不足** → 見 [常見問題 Q1](./features-and-deployment.md#效能最佳化建議)
4. **Milvus 維度衝突** → 見 [常見問題 Q3](./features-and-deployment.md#q3-更換-embedding-模型報錯怎麼辦)

### 聯絡方式

- GitHub Issues: [yiguandao-kb/issues](https://github.com/your-org/yiguandao-kb/issues)
- Email: support@example.com

---

## 文檔地圖

```
docs/
├── INDEX.md                    ← 您正在這裡
├── architecture.md             ← 系統架構
├── architecture-solid.md       ← SOLID 架構設計
├── rag-intro.md                ← RAG 概述
├── rag-deep-dive.md            ← RAG 深度解析
├── features-and-deployment.md  ← 功能與部署
├── api-reference.md            ← API 文檔
└── db-schema.sql               ← 資料庫結構
```

---

## 關鍵概念速查表

### RAG（檢索增強生成）

```
問題 → 術語強化 → 向量化 → 混合搜索（向量 + BM25 + RRF）→ LLM → 回答
```

詳見：[rag-intro.md](./rag-intro.md)

### Session（對話）

```
每個 Session 獨立對話歷史
支援多輪連貫對話（最近 10 輪用於上下文）
訊息存儲於 PostgreSQL，支援持久化
```

詳見：[api-reference.md#session-管理sessions](./api-reference.md#session-管理sessions)

### Repository Pattern

```
HTTP 路由 → Service 層 → Repository 介面 → SQLAlchemy 實作 → PostgreSQL
```

詳見：[architecture-solid.md](./architecture-solid.md)

### 混合搜索（Hybrid Search）

```
[Dense 搜索] Milvus 向量搜索 top-20
    ↓
[Sparse 搜索] BM25 關鍵字搜索於 top-20
    ↓
[融合] RRF 融合排名
    ↓
取 top-5 進入 LLM
```

詳見：[rag-deep-dive.md#6-step-3--混合搜索hybrid-search](./rag-deep-dive.md#6-step-3--混合搜索hybrid-search)

---

## 下一步

- [ ] 部署到開發環境
- [ ] 匯入典籍文件
- [ ] 訪問聊天介面並測試
- [ ] 建立管理員帳號
- [ ] 邀請使用者
- [ ] 監控系統健康（/metrics）
- [ ] 規劃生產部署

---

**文檔完成度**：100% | **最後維護者**：@maintainer | **下次審核日期**：2026-06-20
