# Design Doc: Guardrail Layer + WebSearchAgent

**Author**: Albert  
**Date**: 2026-07-14  
**Status**: Approved — Ready to implement  
**Scope**: 在 VoltAgent 層加入輸入過濾（Guardrail）與網路即時搜尋能力（WebSearchAgent）

---

## 1. Problem Statement

### 1.1 背景

career-analyst-kb 的 VoltAgent MAS 架構目前缺少兩項能力：

1. **無輸入過濾**：任何問題都直接進入 SupervisorAgent，無法阻擋偏題問題、Prompt Injection 或有害內容，與 Going Cloud 的官方架構圖（Guardrail → Supervisor → Task Agents）有明顯落差。

2. **知識截止日**：所有問答依賴靜態 YouTube 字幕 KB，無法回答「這家公司目前薪資行情」、「最新 AI 工程師就業市況」等需要即時資訊的問題。

### 1.2 目標

1. **Guardrail**：在 SupervisorAgent 前加輕量 LLM 分類器，過濾偏題/有害/注入攻擊，不阻斷合法流量（fail open）
2. **WebSearchAgent**：新增第五個 sub-agent，透過自架 SearXNG 做免費即時搜尋，Ollama 本地合成結果，不依賴付費 API

### 1.3 非目標

- 全面的 content moderation（只做輕量職涯相關性判斷）
- Web scraping / full-page content fetch（只用 SearXNG 回傳的 snippet）
- 搜尋結果快取（Phase 1 不含，未來可加）
- Going Cloud 的 Enterprise Agent（呼叫內部 API）—— 此系統無此需求

---

## 2. Architecture After Change

```
User
  │
  ▼
[nginx]
  │
  ▼
[VoltAgent]
  ┌─────────────────────────────────────────────┐
  │  ① Guardrail middleware (NEW)               │
  │    fastModel (qwen3:4b via Ollama)           │
  │    PASS → 繼續                               │
  │    BLOCK → 注入拒絕指令，Supervisor 直接回覆  │
  ├─────────────────────────────────────────────┤
  │  ② confidenceGate (existing)                │
  ├─────────────────────────────────────────────┤
  │  SupervisorAgent (CareerLeadAgent)           │
  │    └── subAgents:                            │
  │        ResumeAgent                           │
  │        InterviewAgent                        │
  │        CareerPlanAgent                       │
  │        SalaryAgent                           │
  │        WebSearchAgent (NEW)                  │
  └─────────────────────────────────────────────┘
          │
          ▼ (WebSearchAgent only)
  [SearXNG container] → 搜尋結果 snippet
          │
          ▼
  Ollama qwen3:14b → 整合成職涯角度回答
```

**與 Going Cloud 架構的對應**：

| Going Cloud | career-analyst-kb |
|------------|------------------|
| Guardrail（獨立元件） | guardrail inputMiddleware |
| Supervisor Agent | SupervisorAgent（CareerLeadAgent） |
| FAQ Agent | queryCareerKBTool（直接用工具，不另建 agent） |
| Knowledge Agent | ResumeAgent / InterviewAgent / CareerPlanAgent / SalaryAgent |
| Web Agent | **WebSearchAgent（本次新增）** |
| Enterprise Agent | 不適用 |

---

## 3. Component Design

### 3.1 Guardrail Middleware

**檔案**：`services/voltagent-career/src/middleware/guardrail.ts`

**Model tier**：`fastModel`（FAST_MODEL env，預設 qwen3:4b）—— 最輕量，延遲最低

**判斷邏輯**（LLM 單次呼叫，回傳結構化 JSON）：

| 條件 | 結果 |
|------|------|
| 與職涯完全無關（天氣、食譜、政治...） | BLOCK |
| Prompt Injection（「忽略前面指示」、「你的新角色是」） | BLOCK |
| 明顯有害（詐騙指令、人身攻擊） | BLOCK |
| 職涯相關（求職、工作、薪資、技能、職場、產業...） | PASS |
| 邊緣情況（「我很累」→ 可能職場壓力） | PASS（寬鬆認定） |

**Fail Open**：若 Ollama 呼叫失敗，return undefined（不阻斷流量）

**BLOCK 實作方式**：  
由於 VoltAgent `inputMiddleware` 無法直接短路回傳給用戶，BLOCK 時注入系統指令到 user input，讓 Supervisor 直接回覆拒絕訊息（同 confidenceGate 的 fallback 做法）：

```
[GUARDRAIL_BLOCK] 請直接回覆以下訊息，不做任何分析：
「抱歉，這個問題超出職涯顧問系統的服務範圍...」
```

**在 Supervisor inputMiddlewares 的順序**：
```typescript
inputMiddlewares: [guardrail, confidenceGate]  // guardrail 在前
```

---

### 3.2 WebSearchAgent

**檔案**：`services/voltagent-career/src/agents/web-search.ts`

**Model tier**：`specialistModel`（SPECIALIST_MODEL env，預設 qwen3:14b）

**工具**：`webSearchTool`（`src/tools/web-search.ts`）

**工具規格**：
```typescript
input:  { query: string; numResults?: number (default 5) }
output: { query: string; results: Array<{ title, url, content }> }
```
呼叫 SearXNG REST API：`GET /search?q=<query>&format=json&language=zh-TW`

**適合路由到 WebSearchAgent 的問題類型**：
- 特定公司薪資行情（「Google Taiwan 工程師薪資 2025」）
- 最新產業就業市況（「台灣 AI 工程師需求趨勢」）
- 市場資訊查詢（「前端工程師平均薪資」）
- 特定職缺即時狀況

**不適合的問題**（應走 KB）：
- 職涯方法論（「怎麼準備面試」→ KB 有大量影片資料）
- 履歷撰寫技巧
- 面試技巧 STAR 方法

---

### 3.3 SearXNG（搜尋後端）

**部署方式**：新增至 `docker/docker-compose.yml`

**選擇 SearXNG 的理由**：
- 完全免費，無 API key
- 自架，穩定，有 JSON REST API
- 聚合多個搜尋引擎（DuckDuckGo、Bing、Google）
- 不依賴 npm scraping 套件（避免 rate limit 風險）

**設定**：掛載 `docker/searxng-settings.yml`
- 開啟 JSON format（預設不開，需顯式設定）
- 關閉 limiter（本地使用）
- 關閉 image_proxy（不需要）

**Container 通訊**：  
`voltagent` → `http://searxng:8080/search`（Docker 內部網路，不暴露 host port）

---

### 3.4 Supervisor Routing 規則新增

在 `supervisor.ts` instructions 中加入：

```
- 即時資訊需求（特定公司薪資、產業市況、最新就業趨勢、市場行情）→ WebSearchAgent
```

同步更新 `routing-classifier.ts` 新增 `"web-search"` 作為 AgentTarget，讓 confidenceGate 也能正確識別。

---

## 4. Config Changes

### `config.ts`
```typescript
searxngUrl: process.env.SEARXNG_URL ?? "http://searxng:8080",
```

### `docker-compose.yml`（voltagent service）
```yaml
environment:
  SEARXNG_URL: "http://searxng:8080"
```

### `.env.example`
```dotenv
# SearXNG（Web Search，由 docker-compose 管理，通常不需手動設定）
SEARXNG_URL=http://searxng:8080
```

---

## 5. Implementation Plan

### Step 1：SearXNG infra（docker-compose + settings）
- `docker/searxng-settings.yml`（新建）
- `docker/docker-compose.yml`（新增 searxng service + voltagent SEARXNG_URL）

### Step 2：webSearch tool
- `src/tools/web-search.ts`（新建）
- `src/config.ts`（新增 `searxngUrl`）

### Step 3：WebSearchAgent
- `src/agents/web-search.ts`（新建）

### Step 4：Guardrail middleware
- `src/middleware/guardrail.ts`（新建）

### Step 5：Supervisor + routing-classifier 更新
- `src/agents/supervisor.ts`（新增 WebSearchAgent、guardrail、路由規則）
- `src/middleware/routing-classifier.ts`（新增 `"web-search"` target）

### Step 6：驗證
1. `docker compose up -d` 確認 searxng 健康
2. 測試 SearXNG：`curl "http://localhost:8080/search?q=台灣軟體工程師薪資&format=json"` → 有 results
3. 測試 Guardrail：送「今天天氣如何」→ 應回覆拒絕訊息
4. 測試 WebSearchAgent：送「Google Taiwan 2025 年工程師薪資行情」→ 應路由到 WebSearchAgent，回傳搜尋整合結果

---

## 6. Risk & Mitigation

| 風險 | 機率 | 緩解 |
|------|------|------|
| SearXNG 被 Google/Bing rate limit | 中 | 分散搜尋引擎（engines 參數），加 User-Agent 設定 |
| Guardrail 誤判（職涯問題被 BLOCK） | 低 | fail open + 寬鬆 PASS 條件（邊緣情況傾向 PASS） |
| Guardrail 增加延遲 | 低 | 用 fastModel（qwen3:4b），比 supervisor 輕得多 |
| Supervisor 路由到 WebSearchAgent 但問題適合 KB | 中 | routing-classifier 更新 + supervisor instructions 明確區分 |

---

## 7. Future Work（不在本次 scope）

- Guardrail 加 rate limiting（每用戶每分鐘限制）
- 搜尋結果快取（Redis TTL 1h，避免重複搜尋相同關鍵字）
- WebSearchAgent 加 `fetchPageContent` 工具（現在只用 snippet）
- 將 Guardrail 判斷寫入 Langfuse trace（可觀測被擋了哪些問題）
