# kb-web — 職涯 AI Chat UI

Next.js 15 前端，提供職涯問答 Chat UI 與 Admin Panel，支援直連 KB API 與 VoltAgent 多 Agent 兩種模式。

---

## 功能

- **雙模式切換**（右下角 Toggle）
  - 直連 KB API SSE 模式：問題直接送 FastAPI RAG pipeline
  - VoltAgent 多 Agent 路由模式：問題由 SupervisorAgent 路由到 ResumeAgent / InterviewAgent / CareerPlanAgent / SalaryAgent
- **主題篩選**：履歷 / 面試 / 薪資 / 職涯規劃 / 求職 / 升遷 / 職場 / 技能發展
- **對話歷程**：左側欄位顯示歷史對話，可切換繼續
- **訊息 Feedback**：對 AI 回答按 👍 / 👎

**Admin Panel**（需 admin 帳號）：

| Tab | 功能 |
|-----|------|
| Documents | 管理知識庫文件、觸發 ingest |
| System Prompts | 管理 KB API 的 system prompt |
| Knowledge Gaps | 分析使用者問題找出知識缺口 |
| Users | 管理使用者帳號 |

---

## 環境變數

| 變數 | 說明 |
|------|------|
| `NEXT_PUBLIC_API_URL` | KB API 位址（留空代表同 origin，走 nginx proxy）|
| `VOLTAGENT_URL` | VoltAgent 位址（Docker 內須設 `http://voltagent:3141`，本地預設 `http://localhost:3141`）|

---

## 本地開發

```bash
cd services/kb-web
npm install
npm run dev        # port 3000
```

需要同時啟動：
- KB API（`http://localhost:8000`）
- VoltAgent（`http://localhost:3141`，VoltAgent 模式才需要）

---

## Docker

```bash
# 從 repo root
cd docker
docker compose up -d kb-web
```

Container 內 `VOLTAGENT_URL` 已設為 `http://voltagent:3141`（Docker 內部 hostname）。

---

## 路由

| 路徑 | 說明 |
|------|------|
| `/` | Chat 主介面（需登入）|
| `/login` | 登入頁 |
| `/admin` | Admin Panel（需 admin role）|

nginx 在 port 80 統一代理：`/api/` → KB API，`/agents/` → VoltAgent，`/` → kb-web。
