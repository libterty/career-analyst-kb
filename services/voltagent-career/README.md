# VoltAgent Career — 職涯多代理人層

TypeScript VoltAgent 服務，提供多代理人協作與職涯主題路由，透過 HTTP 呼叫 Career KB API 取得 RAG 答案。

---

## 架構

```
SupervisorAgent (CareerLeadAgent)
│   model: qwen3:14b（VOLTAGENT_MODEL）
│   tools: [delegate_task]
│
├── ResumeAgent        — 履歷撰寫、ATS、自傳
│     tools: [analyzeResume, queryCareerKB]
├── InterviewAgent     — 面試準備、STAR 方法、JD 分析、模擬問答
│     tools: [analyzeJobDescription, mockInterviewSession, generateInterviewQuestions, queryCareerKB]
├── CareerPlanAgent    — 轉職、升遷、技能 Gap 分析
│     tools: [queryCareerKB]
└── SalaryAgent        — 薪資行情、談判策略、offer 評估
      tools: [queryCareerKB]
```

路由流程：SupervisorAgent 分析問題 → `delegate_task` 路由到對應 sub-agent → sub-agent 呼叫工具取得 RAG 答案 → 生成專業回應

---

## 目錄結構

```
src/
├── agents/
│   ├── supervisor.ts           # CareerLeadAgent（路由 + 整合）
│   ├── resume.ts               # ResumeAgent
│   ├── interview.ts            # InterviewAgent
│   ├── career-plan.ts          # CareerPlanAgent
│   └── salary.ts               # SalaryAgent
├── tools/
│   ├── kb-client.ts            # 共用 fetchCareerKB() HTTP helper
│   ├── query-career-kb.ts      # queryCareerKB — RAG 查詢
│   ├── analyze-resume.ts       # analyzeResume — 履歷解析
│   ├── analyze-job-description.ts  # analyzeJobDescription — JD 分析
│   ├── mock-interview-session.ts   # mockInterviewSession — 模擬面試
│   └── generate-questions.ts   # generateInterviewQuestions — 出題
├── gateway/
│   └── model-gateway.ts        # Model tier 統一管理
├── config.ts                   # 環境變數設定
└── index.ts                    # VoltAgent server entry（port 3141）
```

---

## 工具說明

| 工具 | 所屬 Agent | 說明 |
|------|-----------|------|
| `queryCareerKB` | 全部 | 查詢 Career KB RAG，回傳相關影片片段 |
| `analyzeResume` | ResumeAgent | 解析履歷內容、找出 ATS 關鍵字缺漏 |
| `analyzeJobDescription` | InterviewAgent | 分析 JD 必要技能、面試題方向、準備策略；可搭配履歷做 gap 分析 |
| `mockInterviewSession` | InterviewAgent | 模擬面試：評估候選人回答、STAR 架構分析、追問建議 |
| `generateInterviewQuestions` | InterviewAgent | 針對特定職位生成面試題目 |

---

## 環境變數

| 變數 | 預設值 | 說明 |
|------|--------|------|
| `CAREER_API_TOKEN` | — | KB API 的 JWT token（必填）|
| `KB_API_URL` | `http://localhost:8000` | Career KB API 位址 |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama 位址 |
| `VOLTAGENT_MODEL` | `qwen3:14b` | SupervisorAgent 用模型 |
| `SPECIALIST_MODEL` | `qwen3:14b` | Sub-agent 用模型（預設同 VOLTAGENT_MODEL）|
| `PORT` | `3141` | VoltAgent server port |
| `LANGFUSE_PUBLIC_KEY` | — | Langfuse tracing（可選）|
| `LANGFUSE_SECRET_KEY` | — | Langfuse tracing（可選）|

> **記憶體注意（M3 Max 36GB）**：qwen3:14b 約 11GB VRAM，兩個 tier 共用同一個 model instance（Ollama 負責排程），不會同時佔用 22GB。

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
npm run dev   # hot reload via tsx watch，port 3141
```

確認 Career KB API 已啟動（`http://localhost:8000/health`），且 Ollama 正在運行。

---

## Docker

VoltAgent 已是 docker-compose 預設服務（無需 `--profile`）：

```bash
# 從 repo root
cd docker
docker compose up -d voltagent

# 查看 logs
docker compose logs -f voltagent
```

---

## 測試

```bash
# 健康檢查
curl http://localhost:3141/agents

# 呼叫 SupervisorAgent（SSE 串流）
curl -X POST http://localhost:3141/agents/CareerLeadAgent/stream \
  -H "Content-Type: application/json" \
  -d '{"input": "我想準備後端工程師面試，請幫我分析這份 JD：Django、PostgreSQL、Docker，3 年經驗", "options": {"conversationId": "test-001"}}'
```

或直接在 `http://localhost:3000` Chat UI 開啟 **VoltAgent 多 Agent 路由模式** toggle 測試。

---

## 依賴

| 套件 | 用途 |
|------|------|
| `@voltagent/core` | Agent 框架 |
| `@ai-sdk/openai` | Ollama OpenAI-compatible 介面 |
| `zod` | Tool 參數 schema 驗證 |
| `dotenv` | 環境變數載入 |
