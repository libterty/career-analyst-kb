# Frontend Next.js 實作規劃

**Author**: Albert
**Date**: 2026-07-09
**關聯設計文件**: [frontend-nextjs-design.md](./frontend-nextjs-design.md)

---

## 目標

將 `services/kb-web/` 的靜態 HTML 升級為 Next.js App，功能完全對等，支援 VoltAgent 模式切換。

**成功標準**：
- Chat UI 功能 100% 對等（對話、歷史、SSE 串流、Markdown 渲染）
- Admin Panel 功能 100% 對等（Users / Documents / System Prompts 三個 Tab）
- VoltAgent 模式 / 直連模式切換正常
- Docker Compose 可啟動 kb-web，nginx 路由正確
- TypeScript strict 無錯誤

---

## Phase F1 — 專案初始化

> 建立 Next.js 專案骨架，確認 dev server 可啟動

### F1.1 建立 Next.js 專案

```bash
# 先備份現有靜態 HTML（已在 services/kb-web/ 中）
cd services
# 新建 Next.js 覆蓋 kb-web（注意 kb-web 目前只有靜態 HTML）
npx create-next-app@latest kb-web \
  --typescript \
  --tailwind \
  --eslint \
  --app \
  --no-src-dir \
  --import-alias "@/*"
```

> **注意**：執行前確認 `services/kb-web/` 的靜態 HTML 已備份到 `docs/redesign/` 或 git stash。

### F1.2 調整目錄結構

```bash
cd kb-web
mkdir -p src/app/login src/app/admin
mkdir -p src/components/chat src/components/admin src/components/ui
mkdir -p src/lib src/types
```

### F1.3 建立 .env.local

```bash
echo "NEXT_PUBLIC_API_URL=http://localhost:80" > .env.local
```

### F1.4 驗證

```bash
npm run dev   # http://localhost:3000 可開啟
npm run build # 無錯誤
```

---

## Phase F2 — 共用基礎設施

> 型別定義、API wrapper、Auth helper、共用 UI 元件

### F2.1 型別定義 `src/types/index.ts`

```typescript
export interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
}

export interface Source {
  video_id: string;
  title: string;
  channel: string;
  chunk_index: number;
  score: number;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
}

export interface User {
  id: number;
  username: string;
  role: "admin" | "user";
  is_active: boolean;
}

export interface Document {
  id: number;
  filename: string;
  created_at: string;
}
```

### F2.2 API wrapper `src/lib/api.ts`

- base URL 從 `NEXT_PUBLIC_API_URL` 讀取
- 自動附加 `Authorization: Bearer <token>`
- 統一錯誤處理（401 → redirect /login）

### F2.3 Auth helper `src/lib/auth.ts`

```typescript
export const getToken = () => localStorage.getItem("jwt_token");
export const setToken = (token: string) => localStorage.setItem("jwt_token", token);
export const clearToken = () => localStorage.removeItem("jwt_token");
export const isAuthenticated = () => !!getToken();
```

### F2.4 共用 UI 元件

| 元件 | 對應原 HTML |
|------|------------|
| `ui/Toast.tsx` | `#toast` + `showToast()` |
| `ui/Modal.tsx` | `.modal-backdrop` + `.modal-box` |
| `ui/Badge.tsx` | `.badge-admin` / `.badge-user` / `.badge-active` |

---

## Phase F3 — 登入頁

> `src/app/login/page.tsx`

- username / password 表單
- 呼叫 `POST /api/auth/token`，存 JWT，redirect `/`
- 對應原 index.html 的 `#login-screen`

---

## Phase F4 — Chat UI

> `src/app/page.tsx` + `src/components/chat/`

### 元件拆分

| 元件 | 責任 |
|------|------|
| `ConversationSidebar.tsx` | 對話歷史列表、New Chat 按鈕、刪除 |
| `ChatBox.tsx` | 訊息串列、輸入框、送出邏輯、Agent 模式切換 |
| `MessageBubble.tsx` | 單一訊息氣泡，user/bot 樣式、sources citations |
| `TypingIndicator.tsx` | 三點打字動畫 |

### Agent 模式切換

```typescript
// ChatBox.tsx
const [mode, setMode] = useState<"direct" | "voltagent">("voltagent");

const endpoint = mode === "voltagent"
  ? `${API_URL}/agents/career-lead/invoke`
  : `${API_URL}/api/chat/query`;
```

### SSE 串流

```typescript
const res = await fetch(`${API_URL}/api/chat/query`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Authorization: `Bearer ${getToken()}`,
  },
  body: JSON.stringify({ question, session_id }),
});
const reader = res.body!.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  const chunk = decoder.decode(value);
  // append chunk to current assistant message
}
```

### 功能檢核清單

- [ ] 新對話 → session_id 建立
- [ ] 問答 SSE 串流正常 → Markdown 渲染
- [ ] Sources citations 顯示（video_id、title）
- [ ] 對話歷史側欄 → 可切換、刪除
- [ ] Agent 模式切換（VoltAgent / 直連）

---

## Phase F5 — Admin Panel

> `src/app/admin/page.tsx` + `src/components/admin/`

### 元件拆分

| 元件 | 責任 |
|------|------|
| `UsersTab.tsx` | 使用者列表、新增、刪除、角色切換 |
| `DocumentsTab.tsx` | 文件列表、ingest 新影片、刪除 |
| `PromptsTab.tsx` | 系統 Prompt 查看/編輯（per agent） |

### 功能檢核清單

- [ ] Users Tab：列表 / 新增 / 刪除 / 角色切換
- [ ] Documents Tab：列表 / 新增 / 刪除
- [ ] System Prompts Tab：4 個 agent 的 prompt 查看/編輯
- [ ] Toast 通知（成功/失敗）

---

## Phase F6 — Docker 整合

### F6.1 Dockerfile (`services/kb-web/Dockerfile`)

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

### F6.2 next.config.ts

```typescript
const nextConfig = {
  output: "standalone",  // Docker 最小化輸出
};
export default nextConfig;
```

### F6.3 docker-compose.yml 更新

```yaml
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

### F6.4 nginx.conf 更新

```nginx
# / → Next.js kb-web（取代 FastAPI 靜態服務）
location / {
    proxy_pass http://kb-web:3000;
    proxy_set_header Host $host;
    proxy_http_version 1.1;
}

# /agents/ → VoltAgent
location /agents/ {
    proxy_pass http://voltagent:3141;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
}

# /api/ → FastAPI kb-api（維持不動）
location /api/ {
    proxy_pass http://app:8000;
    proxy_set_header Host $host;
}
```

### F6.5 驗證清單

- [ ] `docker compose up -d` 所有容器啟動
- [ ] `http://localhost:80` → Next.js Chat UI
- [ ] `http://localhost:80/admin` → Admin Panel
- [ ] `/api/health` 仍回 200（FastAPI 直連）
- [ ] `/agents/career-lead/invoke` 正常（VoltAgent mode）
- [ ] FastAPI 的 StaticFiles mount 移除（不再 serve 靜態檔）

---

## 完整里程碑

| Phase | 內容 | 前置 | 狀態 |
|-------|------|------|------|
| F1 | Next.js 專案初始化 | F0（靜態 HTML 搬移✅）| ⏳ 待做 |
| F2 | 共用基礎設施（型別 + API + Auth + UI） | F1 | ⏳ 待做 |
| F3 | 登入頁 | F2 | ⏳ 待做 |
| F4 | Chat UI（SSE + Agent 模式切換） | F2, F3 | ⏳ 待做 |
| F5 | Admin Panel | F2 | ⏳ 待做 |
| F6 | Docker 整合 + Nginx 更新 | F4, F5 | ⏳ 待做 |
