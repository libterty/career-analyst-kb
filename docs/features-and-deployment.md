# 功能與部署指南

> 本文件整理 道輝 系統的核心功能和部署步驟。

**最後更新：2026-03-20**

---

## 目錄

1. [核心功能](#核心功能)
2. [使用者角色與權限](#使用者角色與權限)
3. [聊天介面](#聊天介面)
4. [管理員面板](#管理員面板)
5. [部署檢查清單](#部署檢查清單)
6. [常見問題](#常見問題)

---

## 核心功能

### 1. RAG 智慧問答系統

基於混合搜索（Dense Vector + BM25 + RRF）的檢索增強生成系統：

- **向量搜索**：使用 Milvus 進行快速語意搜索
- **關鍵字搜索**：BM25 演算法精確匹配
- **結果融合**：RRF 算法融合兩種搜索結果
- **串流輸出**：使用 Server-Sent Events 實時推送回答

### 2. 多輪對話與 Session 管理

- 每個 Session 保留最近 100 條訊息
- 系統 memory 支援最近 10 輪對話連貫性
- 使用者可建立多個獨立 Session
- Session 自動分頁列表展示

### 3. 文件管理

- 支援格式：PDF、DOCX、PPTX
- 自動去重（doc_hash 指紋）
- 批次匯入與單檔上傳
- 文件版本追蹤

### 4. 安全防護

- **Prompt Injection 偵測**：識別並拒絕惡意注入
- **內容過濾**：違禁詞彙過濾
- **輸入/輸出消毒**：在 HTTP 層檢查，逐 token 輸出消毒
- **JWT 認證**：所有 API 端點均需登入

### 5. 用戶管理與權限控制

- **角色區分**：user / admin
- **Session 限制**：管理員可限制使用者最多建立多少 Session
- **密碼管理**：安全雜湊存儲，支援密碼重置

---

## 使用者角色與權限

### User（普通使用者）

| 功能 | 權限 |
|------|------|
| 聊天問答 | ✅ 可自由提問 |
| Session 管理 | ✅ 可建立、編輯、刪除自己的 Session |
| 文件檢視 | ✅ 可查看已匯入文件列表（只讀） |
| 系統管理 | ❌ 無權訪問管理員面板 |

### Admin（管理員）

| 功能 | 權限 |
|------|------|
| 聊天問答 | ✅ 同上 |
| Session 管理 | ✅ 同上 |
| 文件檢視 | ✅ 同上 |
| 文件上傳 | ✅ 可上傳新文件進行匯入 |
| 文件刪除 | ✅ 可刪除已匯入的文件 |
| 用戶管理 | ✅ 建立、編輯、刪除使用者帳號 |
| 用戶角色指派 | ✅ 設定使用者為 user 或 admin |
| 用戶 Session 限制 | ✅ 限制使用者最多開幾個 Session |

---

## 聊天介面

### URL

```
http://localhost
```

或

```
http://localhost/
```

### 功能

1. **側邊欄（Sidebar）**
   - 「新對話」按鈕：建立新 Session
   - Session 列表：點選切換對話
   - Session 操作：刪除、重新命名

2. **聊天區（Chat Box）**
   - 訊息顯示：使用者訊息（右側藍色氣泡），機器人回答（左側灰色氣泡）
   - Markdown 渲染：回答支援 Markdown 格式（粗體、代碼、清單等）
   - 打字指示：機器人生成中顯示「...」動畫

3. **輸入框**
   - 文字輸入
   - 送出按鈕（或 Ctrl+Enter）
   - 清除按鈕

4. **頂部欄（Header）**
   - Session 標題顯示
   - 登出按鈕

---

## 管理員面板

### URL

```
http://localhost/admin
```

### 功能分區

#### 用戶管理標籤

**列表視圖：**
- 顯示所有使用者（帳號、角色、建立時間）
- 分頁（每頁 20 項）
- 搜尋（按帳號搜尋）

**建立新使用者：**
- 表單欄位：帳號、密碼、角色（user / admin）
- 確認按鈕

**編輯使用者：**
- 可修改：密碼、角色、最大 Session 數
- 刪除按鈕（附確認彈出）

#### 文件管理標籤

**已匯入文件列表：**
- 檔案名稱、上傳時間、分段數
- 分頁
- 刪除按鈕

**上傳新文件：**
- 拖曳上傳區域
- 支援檔案類型：PDF、DOCX、PPTX
- 上傳進度條
- 成功/失敗提示

---

## 部署檢查清單

### 本機開發環境

- [ ] Ollama 已安裝並執行（`ollama serve` 後台運行）
- [ ] 必要模型已拉取：
  - [ ] `ollama pull gemma3:12b` （或 4b / 2b）
  - [ ] `ollama pull nomic-embed-text`
- [ ] `.env` 已複製並設定
  - [ ] `ADMIN_PASSWORD` 已修改（不用預設值）
  - [ ] `SECRET_KEY` 已設定為強隨機值
- [ ] Docker & Docker Compose 已安裝
- [ ] `cd docker && docker compose up -d` 已執行
- [ ] 容器健康：
  ```bash
  docker compose ps
  docker compose logs app | head -50
  ```
- [ ] 數據庫初始化完成
  ```bash
  curl http://localhost:8000/health
  ```

### 生產環境

- [ ] **SSL/HTTPS 已設定**（Nginx 反向代理）
- [ ] **SECRET_KEY 已設為強隨機值**（不可硬編碼）
  ```bash
  python3 -c "import secrets; print(secrets.token_hex(32))"
  ```
- [ ] **ADMIN_PASSWORD 已變更**
- [ ] **環境變數**已通過安全方式注入（不提交 `.env` 至版本控制）
- [ ] **APP_ENV=production**（關閉 `/docs`）
- [ ] **CORS_ORIGINS 已設定為實際前端域名**
- [ ] **日誌已配置**為外部儲存（不填滿容器磁碟）
- [ ] **定期備份**：
  - PostgreSQL 資料庫
  - Milvus 向量資料庫
  - 匯入的文件（`data/raw/`）
- [ ] **監控告警**已啟用：
  - `/metrics` Prometheus 指標暴露
  - 容器 CPU、記憶體、磁碟監控
  - 應用程式錯誤日誌告警

### 效能調優

| 項目 | 建議 |
|------|------|
| 記憶體（Ollama） | gemma3:12b 需 10GB；記憶體不足改用 4b 或 2b |
| Milvus 搜索參數 | `nprobe=16` 可調高至 32 提高準確度但降低速度 |
| RRF 融合係數 | k=60 是推薦值，無特殊需求不改 |
| Dense top_k | 20 條候選通常夠用；知識庫大可改 50 |
| Final top_k | 5 條進入 LLM 是語意完整與速度平衡點 |

---

## 常見問題

### Q1: 如何重置密碼？

**管理員重置使用者密碼：**
```bash
# 通過管理員面板編輯使用者 → 修改密碼 → 確認
```

**直接透過 API：**
```bash
curl -X PATCH http://localhost:8000/api/admin/users/{user_id} \
  -H "Authorization: Bearer <ADMIN_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"password": "new_password"}'
```

### Q2: 文件匯入失敗怎麼辦？

**常見原因：**

1. **格式不支援** → 確保是 PDF / DOCX / PPTX
2. **文件已存在**（doc_hash 重複） → 刪除舊版本後重新上傳
3. **Milvus 向量維度衝突** → 見「Q3」
4. **Embedding 模型未拉取** → `ollama pull nomic-embed-text`

### Q3: 更換 Embedding 模型報錯怎麼辦？

**症狀：** Milvus 報錯「dimension mismatch」

**解決方案：**
```bash
# 1. 刪除舊 Collection（所有向量）
python3.11 scripts/reset_knowledge_base.py --vectors-only --yes

# 2. 修改 .env
EMBEDDING_MODEL=mxbai-embed-large   # 換成 1024 維模型

# 3. 重新匯入
python3.11 scripts/ingest_documents.py --path data/raw/
```

### Q4: 對話歷史保存在哪裡？

- **內存存儲**：RAG Pipeline 記憶（最近 10 輪）用於上下文連貫
- **持久化存儲**：PostgreSQL `chat_messages` 表存儲所有訊息
- **Milvus**：只存向量與文件 metadata，不存對話

### Q5: 如何清空知識庫但保留使用者帳號？

```bash
# 清空 Milvus 向量（不刪對話紀錄）
python3.11 scripts/reset_knowledge_base.py --vectors-only --yes

# 清空 Milvus + 對話紀錄（保留用戶）
python3.11 scripts/reset_knowledge_base.py --yes --include-chat-history
```

### Q6: 系統支援多少使用者？

- **併發使用者**：取決於 Ollama 機器的 VRAM（gemma3:12b 約 10GB）
- **總使用者數**：無限制（PostgreSQL 可存百萬級記錄）
- **同時聊天**：建議 Ollama 同時只跑 1-2 個推理（視 VRAM）

### Q7: 如何監控系統健康？

```bash
# 應用健康
curl http://localhost/health

# Prometheus 指標
curl http://localhost/metrics | grep -E "http_requests_total|response_time"

# 容器日誌
docker compose logs -f app
docker compose logs postgres
docker compose logs milvus-standalone
```

### Q8: 支援多個 LLM 模型切換嗎？

支援。修改 `.env`：

```dotenv
# 用本機 Ollama
LLM_PROVIDER=ollama
LLM_MODEL=gemma3:12b

# 改用 Grok
LLM_PROVIDER=grok
GROK_API_KEY=xai-...

# 改用 OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
```

重啟應用後生效。Embedding 也可獨立配置。

### Q9: 前端是否支援暗模式？

是。聊天介面已包含暗模式樣式，管理員面板使用 Tailwind 的暗色主題。

### Q10: 如何自訂系統 Prompt？

修改 `src/rag/pipeline.py` 的 `_SYSTEM_PROMPT` 常數：

```python
_SYSTEM_PROMPT = """你是一位熟悉一貫道教義的智慧助理，名為「道輝」。
...（自訂內容）
"""
```

改好後重啟應用。

---

## 效能最佳化建議

### 減少延遲

1. **調整 Milvus 搜索參數**
   ```python
   # src/rag/retriever.py
   "nprobe": 16  # 調高至 32 提高準確度但變慢
   ```

2. **減少 top_k**
   ```python
   # src/rag/hybrid_search.py
   self.final_top_k = 3  # 改從 5 條改為 3 條
   ```

3. **啟用回應快取**（可選）
   - 對相同問題快取 RAG 結果
   - 需實作 Redis 層

### 降低記憶體使用

1. **用輕量化模型**
   ```dotenv
   # gemma3:12b（10GB）→ gemma3:4b（4GB）
   LLM_MODEL=gemma3:4b
   ```

2. **調整 Session 訊息保留數**
   ```python
   # src/infrastructure/persistence/models.py
   MAX_MESSAGES_PER_SESSION = 50  # 改從 100 改為 50
   ```

---

## 後續功能規劃

- [ ] 文件分組與標籤化
- [ ] 使用者反饋與評分（改進 RAG 效果）
- [ ] 細粒度權限控制（文件級別存取）
- [ ] 批量 Session 管理與分享
- [ ] Webhook 支援第三方整合
- [ ] 多語言介面（英文、簡體中文）
