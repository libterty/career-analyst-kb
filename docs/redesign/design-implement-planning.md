# Design Implement Planning: Mono-Repo + Frontend 遷移

**Author**: Albert
**Date**: 2026-07-09
**關聯設計文件**: [../current/design-career-analyst-kb.md](../current/design-career-analyst-kb.md)
**關聯請求流程**: [../current/request-flow.md](../current/request-flow.md)

---

## 目標

career-analyst-kb 的 Mono-Repo 結構（`services/kb-api/` + `services/voltagent-career/`）已完成，本文補全以下工作：

1. **Frontend 遷移**：將根目錄 `frontend/` 搬移至 `services/kb-web/`，與 kb-api、voltagent-career 並列
2. **Next.js 升級**：靜態 HTML → Next.js App（見 frontend-nextjs-design.md）
3. **Docker 整合**：更新 Dockerfile、docker-compose.yml、nginx.conf

---

## 現有 Mono-Repo 結構（Phase 1–8 完成後）

```
career-analyst-kb/          ← git root
├── services/
│   ├── kb-api/             ← Python FastAPI + RAG pipeline ✅
│   ├── voltagent-career/   ← TypeScript VoltAgent layer ✅
│   └── kb-web/             ← Static HTML frontend（搬移中 → 未來 Next.js）
├── docker/
│   ├── docker-compose.yml
│   └── nginx.conf
├── eval/                   ← golden_dataset.jsonl, rag_eval.py
├── data/
└── docs/
```

---

## Phase F0 — Frontend 目錄搬移（✅ 完成）

> **原則**：只搬移靜態 HTML 檔案，不修改業務邏輯。搬完驗證服務正常啟動。

### F0.1 搬移檔案

```
frontend/
  admin.html  →  services/kb-web/admin.html
  index.html  →  services/kb-web/index.html
  static/     →  services/kb-web/static/
  templates/  →  services/kb-web/templates/
```

### F0.2 需修改的設定檔

#### `services/kb-api/Dockerfile`

```dockerfile
# Before
COPY frontend/ ./frontend/

# After
COPY services/kb-web/ ./services/kb-web/
```

#### `docker/docker-compose.yml`

```yaml
# app service 的 volume mount 從 frontend/ 改為 services/kb-web/
volumes:
  - ../services/kb-web:/app/services/kb-web      # 熱重載（原 ../frontend:/app/frontend）
```

#### `services/kb-api/src/api/main.py`

```python
# REPO_ROOT 尋找 services/kb-web（原本尋找 frontend）
REPO_ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "services" / "kb-web").is_dir()),
    Path(__file__).resolve().parents[2],
)
# ...
frontend_path = REPO_ROOT / "services" / "kb-web"  # 原本 REPO_ROOT / "frontend"
```

#### `services/kb-api/src/core/config.py`

```python
# 同上，.env 讀取路徑依據 REPO_ROOT
REPO_ROOT = next(
    (p for p in Path(__file__).resolve().parents if (p / "services" / "kb-web").is_dir()),
    Path(__file__).resolve().parents[2],
)
```

#### `.gitignore`

```
services/kb-web/node_modules/*
services/kb-web/.next/*
```

### F0.3 驗證清單

- [ ] `docker compose up -d` 所有容器正常啟動
- [ ] `curl http://localhost:80/health` 回傳 200
- [ ] `curl -X POST http://localhost:80/api/auth/login ...` 正常取得 JWT
- [ ] `http://localhost:80` 開啟 Chat UI
- [ ] `http://localhost:80/admin` 開啟 Admin Panel
- [ ] 問一個問題，確認 RAG 回答正常

---

## Phase F1 — Next.js 升級（待規劃）

> **原則**：用 Next.js 取代靜態 HTML，在不改動 API 層的前提下遷移 UI。

見 [frontend-nextjs-design.md](./frontend-nextjs-design.md) 與 [frontend-nextjs-planning.md](./frontend-nextjs-planning.md)。

### 目標架構

```
services/kb-web/             ← Next.js App（未來）
├── src/
│   ├── app/
│   │   ├── page.tsx         ← Chat UI（原 index.html）
│   │   ├── login/page.tsx
│   │   └── admin/page.tsx   ← Admin Panel（原 admin.html）
│   ├── components/
│   │   ├── chat/
│   │   └── admin/
│   └── lib/
│       ├── api.ts
│       └── auth.ts
├── package.json
├── next.config.ts
└── tailwind.config.ts
```

### Nginx 整合（Phase F1）

```nginx
# /agents/* → VoltAgent
location /agents/ {
    proxy_pass http://voltagent:3141;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection 'upgrade';
}

# / → Next.js（Phase F1 後取代 FastAPI 靜態服務）
location / {
    proxy_pass http://kb-web:3000;
}
```

---

## 里程碑

| Phase | 內容 | 狀態 |
|-------|------|------|
| F0 | Frontend 目錄搬移（`frontend/` → `services/kb-web/`） | ✅ 完成 |
| F1 | Next.js 升級（靜態 HTML → React/TypeScript） | ⏳ 待規劃 |
| F2 | VoltAgent 模式切換（Chat UI 支援直連 / VoltAgent 兩種模式） | ⏳ 待規劃 |

---

## 執行前 Checklist

- [x] `frontend/` 內容搬移至 `services/kb-web/`
- [x] `services/kb-api/Dockerfile` 更新 COPY 路徑
- [x] `docker/docker-compose.yml` 更新 volume mount
- [x] `services/kb-api/src/api/main.py` 更新 REPO_ROOT 邏輯
- [x] `services/kb-api/src/core/config.py` 更新 REPO_ROOT 邏輯
- [x] `.gitignore` 加入 `services/kb-web/node_modules/*` 與 `.next/*`
- [ ] Docker Compose 重啟驗證
