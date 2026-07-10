# Frontend Next.js 遷移設計文件

**Author**: Albert
**Date**: 2026-07-09
**關聯規劃**: [frontend-nextjs-planning.md](./frontend-nextjs-planning.md)
**關聯系統設計**: [../current/design-career-analyst-kb.md](../current/design-career-analyst-kb.md)

---

## 背景

現有 `services/kb-web/` 只有兩個靜態 HTML 檔（index.html、admin.html），依賴 CDN 載入 Tailwind CSS、marked.js，透過 `fetch` 直接呼叫 kb-api。目標是將其遷移為 Next.js 應用，納入 monorepo，與 kb-api、voltagent-career 並列。

---

## 現有 Frontend 功能盤點

### `index.html` — Chat UI（Career Analyst）

| 功能 | 說明 |
|------|------|
| 對話介面 | 使用者輸入職涯問題，bot 回應，支援 Markdown 渲染 |
| 側欄 | 對話歷史列表，可建立新對話、切換、刪除 |
| 打字指示器 | 三點動畫，等待回應期間顯示 |
| 認證 | JWT token 存 localStorage，未登入導向 login |
| 登入頁 | username/password 登入表單 |
| 串流回應 | EventSource / fetch stream 接收 SSE |
| Agent 模式切換 | 直連 FastAPI / 經 VoltAgent（待實作） |

### `admin.html` — 管理後台

| 功能 | 說明 |
|------|------|
| 使用者管理 | 列表、新增、刪除、角色切換（admin/user） |
| 文件管理 | 知識庫文件列表、ingest 新影片字幕、刪除 |
| 系統 Prompt 管理 | 查看/編輯各 agent 的 system prompt |
| Tab 切換 | Users / Documents / System Prompts |
| Toast 通知 | 操作成功/失敗的即時回饋 |

---

## 目標架構

```
services/kb-web/
├── src/
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── page.tsx              ← Chat UI（原 index.html）
│   │   ├── login/
│   │   │   └── page.tsx
│   │   └── admin/
│   │       └── page.tsx          ← Admin Panel（原 admin.html）
│   ├── components/
│   │   ├── chat/
│   │   │   ├── ChatBox.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── TypingIndicator.tsx
│   │   │   └── ConversationSidebar.tsx
│   │   ├── admin/
│   │   │   ├── UsersTab.tsx
│   │   │   ├── DocumentsTab.tsx
│   │   │   └── PromptsTab.tsx
│   │   └── ui/
│   │       ├── Toast.tsx
│   │       ├── Modal.tsx
│   │       └── Badge.tsx
│   ├── lib/
│   │   ├── api.ts                ← fetch wrapper，base URL 從 env
│   │   └── auth.ts               ← JWT token 管理
│   └── types/
│       └── index.ts
├── public/
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

---

## 架構決策

### A-1：API 接入模式

Career Analyst KB 支援兩種查詢路徑：

| 模式 | 端點 | 說明 |
|------|------|------|
| 直連模式 | `POST /api/chat/query` (SSE) | 直接呼叫 FastAPI，無 agent routing |
| VoltAgent 模式 | `POST /agents/career-lead/invoke` | 經 VoltAgent supervisor，有 4 sub-agent 路由 |

Next.js 前端在 Chat UI 提供模式切換，預設 VoltAgent 模式（有 routing + quality judge）。

### A-2：SSE 串流處理

使用 `fetch` + `ReadableStream`，不用 `EventSource`（相容性更好）：

```typescript
const res = await fetch(`${API_URL}/api/chat/query`, {
  method: "POST",
  headers: { Authorization: `Bearer ${getToken()}` },
  body: JSON.stringify({ question, session_id }),
});
const reader = res.body!.getReader();
// 逐 chunk decode，append 到 message state
```

### A-3：Docker 整合

Phase F1 後，Next.js 獨立為 `kb-web` Docker service，nginx 路由 `/` → `kb-web:3000`，FastAPI 不再 serve 靜態檔案：

```yaml
# docker-compose.yml
kb-web:
  build:
    context: ../services/kb-web
    dockerfile: Dockerfile
  ports:
    - "3000:3000"
  environment:
    NEXT_PUBLIC_API_URL: http://localhost:80
  depends_on:
    - app
```

```nginx
# nginx.conf
location / {
    proxy_pass http://kb-web:3000;
}
location /agents/ {
    proxy_pass http://voltagent:3141;
}
location /api/ {
    proxy_pass http://app:8000;
}
```

### A-4：認證策略

- 維持 JWT + localStorage（與現有 FastAPI auth 相容）
- `lib/auth.ts`：`getToken()` / `setToken()` / `clearToken()`
- layout.tsx 的 auth guard：無 token → redirect `/login`

---

## 遷移對照表

| 原 HTML | Next.js 對應 | 說明 |
|---------|-------------|------|
| `<div id="login-screen">` | `app/login/page.tsx` | 獨立路由 |
| `<div id="chat-screen">` | `app/page.tsx` + `ChatBox.tsx` | |
| `<div id="sidebar">` | `ConversationSidebar.tsx` | |
| `#toast` + `showToast()` | `ui/Toast.tsx` | |
| `marked.js` | `react-markdown` | npm 套件 |
| CDN Tailwind | `tailwind.config.ts` | 本地 PostCSS |
| Admin HTML tab 切換 | `app/admin/page.tsx` + `UsersTab/DocumentsTab/PromptsTab` | |

---

## 成功標準

- [ ] Chat UI 功能 100% 對等（對話、歷史、SSE 串流、Markdown 渲染）
- [ ] Admin Panel 功能 100% 對等（Users / Documents / System Prompts 三個 Tab）
- [ ] VoltAgent 模式 / 直連模式切換正常
- [ ] Docker Compose 可啟動 kb-web，nginx 路由正確
- [ ] TypeScript strict 無錯誤
- [ ] `npm run build` 通過
