# VoltAgent Career — 職涯多代理人層

TypeScript VoltAgent 服務，提供多代理人協作與職涯主題路由，透過 HTTP 呼叫 Career KB API 取得 RAG 答案。

---

## 架構

```
SupervisorAgent (CareerLeadAgent)
│   model: Ollama gemma3:12b
│   tools: [queryCareerKB]
│
├── ResumeAgent        — 履歷撰寫、ATS、自傳
├── InterviewAgent     — 面試準備、STAR 方法、緊張處理
├── CareerPlanAgent    — 轉職、升遷、職涯方向
└── SalaryAgent        — 薪資行情、談判策略、offer 評估
```

路由流程：SupervisorAgent 分析問題 → 路由到對應 sub-agent → sub-agent 呼叫 `queryCareerKB` tool → Career KB API 回傳 RAG 答案 → 生成專業回應

---

## 目錄結構

```
src/
├── agents/
│   ├── supervisor.ts       # CareerLeadAgent（路由 + 整合）
│   ├── resume.ts           # ResumeAgent
│   ├── interview.ts        # InterviewAgent
│   ├── career-plan.ts      # CareerPlanAgent
│   └── salary.ts           # SalaryAgent
├── tools/
│   ├── kb-client.ts        # 共用 fetchCareerKB() HTTP helper
│   ├── query-career-kb.ts  # queryCareerKB tool
│   ├── analyze-resume.ts   # analyzeResume tool
│   └── generate-questions.ts
├── config.ts               # 環境變數設定
└── index.ts                # VoltAgent server entry（port 3141）
```

---

## 環境變數

從 repo root `.env` 與 `services/voltagent-career/.env` 載入（repo root 優先）：

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `CAREER_API_TOKEN` | — | KB API 的 JWT token（必填）|
| `KB_API_URL` | `http://localhost:8000` | Career KB API 位址 |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama 位址（自動加 `/v1`）|
| `VOLTAGENT_MODEL` | `gemma3:12b` | Agent 推理模型 |
| `PORT` | `3141` | VoltAgent server port |

取得 `CAREER_API_TOKEN`：

```bash
curl -X POST http://localhost:8000/api/auth/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=<ADMIN_PASSWORD>"
# 複製回傳的 access_token 填入 .env
```

---

## 本地開發

```bash
cd services/voltagent-career

npm install

# 開發模式（hot reload）
npm run dev
```

確認 Career KB API 已啟動（`http://localhost:8000/health`），且 Ollama 正在運行。

---

## 建置與生產啟動

```bash
npm run build          # tsc → dist/
npm start              # node dist/index.js
```

---

## Docker

```bash
# 從 repo root
docker compose --profile voltagent up -d voltagent

# 查看 logs
docker compose logs -f voltagent
```

---

## 測試

呼叫 VoltAgent HTTP API：

```bash
# 健康檢查
curl http://localhost:3141/health

# 呼叫 SupervisorAgent
curl -X POST http://localhost:3141/agents/career-lead/invoke \
  -H "Content-Type: application/json" \
  -d '{"input": "我想準備外商面試，應該怎麼做？", "sessionId": "test-001"}'
```

---

## 依賴

| 套件 | 版本 | 用途 |
|------|------|------|
| `@voltagent/core` | ^2.7.0 | Agent 框架 |
| `@ai-sdk/openai` | ^3.0.0 | Ollama OpenAI-compatible 介面 |
| `zod` | ^3.22.0 | Tool 參數 schema 驗證 |
| `dotenv` | ^16.0.0 | 環境變數載入 |
