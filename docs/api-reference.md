# API 參考

> 道輝 系統完整 API 文件。

**最後更新：2026-03-20**

---

## 基本資訊

- **基礎 URL**: `http://localhost:8000`（本機開發）或 `http://localhost/api`（生產環境反向代理）
- **認證**: JWT Bearer Token
- **Content-Type**: `application/json`

---

## 認證（Auth）

### 1. 用戶註冊

**端點**: `POST /api/auth/register`

**請求**:
```json
{
  "username": "john_doe",
  "password": "SecurePassword123!"
}
```

**回應** (201 Created):
```json
{
  "id": 1,
  "username": "john_doe",
  "role": "user",
  "created_at": "2026-03-20T10:30:00Z"
}
```

**錯誤**:
- `409 Conflict`: 帳號已存在
- `400 Bad Request`: 密碼過弱

---

### 2. 用戶登入

**端點**: `POST /api/auth/login`

**請求**:
```json
{
  "username": "john_doe",
  "password": "SecurePassword123!"
}
```

**回應** (200 OK):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 28800
}
```

**使用 Token**:
```bash
curl -H "Authorization: Bearer <access_token>" http://localhost:8000/api/chat/query
```

**錯誤**:
- `401 Unauthorized`: 帳號或密碼錯誤
- `404 Not Found`: 用戶不存在

---

### 3. 刷新 Token

**端點**: `POST /api/auth/refresh`

**請求**:
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIs..."
}
```

**回應** (200 OK):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer",
  "expires_in": 28800
}
```

---

## 聊天（Chat）

### 1. 串流問答

**端點**: `POST /api/chat/query`

**請求**:
```json
{
  "question": "三寶是什麼？",
  "session_id": "uuid-string-optional"
}
```

**回應** (200 OK, `text/event-stream`):
```
data: 三\n\n
data: 寶\n\n
data: 者\n\n
...
data: [DONE]\n\n
```

**說明**:
- 使用 Server-Sent Events 進行串流
- 每個 token 以 `data: <token>\n\n` 格式推送
- 最後發送 `data: [DONE]\n\n` 表示完成
- `session_id` 可選；若不提供系統會建立新 Session

**錯誤**:
- `400 Bad Request`: 問題未通過安全檢查（Prompt Injection）
- `403 Forbidden`: Session 不存在或無權訪問
- `401 Unauthorized`: 未登入

**範例**（使用 JavaScript）:
```javascript
const response = await fetch('/api/chat/query', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`
  },
  body: JSON.stringify({
    question: '三寶是什麼？',
    session_id: 'my-session-id'
  })
});

const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
  const { done, value } = await reader.read();
  if (done) break;

  const text = decoder.decode(value);
  // 處理 SSE 格式
  const lines = text.split('\n');
  lines.forEach(line => {
    if (line.startsWith('data: ')) {
      const token = line.slice(6);
      console.log(token);
    }
  });
}
```

---

### 2. 同步問答

**端點**: `POST /api/chat/query/sync`

**請求**:
```json
{
  "question": "三寶是什麼？",
  "session_id": "uuid-string-optional"
}
```

**回應** (200 OK):
```json
{
  "answer": "三寶者，天道之根本也...",
  "session_id": "uuid",
  "sources": [
    {
      "source": "基礎教義總覽.docx",
      "section": "第一章",
      "content": "三寶者，天道之根本也..."
    },
    ...
  ],
  "timestamp": "2026-03-20T10:35:00Z"
}
```

---

## 文件管理（Documents）

### 1. 上傳文件

**端點**: `POST /api/documents/ingest`

**請求** (multipart/form-data):
```
file: <binary PDF/DOCX/PPTX file>
```

**回應** (201 Created):
```json
{
  "id": "doc_abc123",
  "file_path": "data/raw/典籍.pdf",
  "doc_hash": "sha256_hash",
  "chunk_count": 42,
  "created_at": "2026-03-20T10:40:00Z"
}
```

**支援格式**:
- PDF (`.pdf`)
- Word (`.docx`)
- PowerPoint (`.pptx`)

**錯誤**:
- `400 Bad Request`: 檔案格式不支援
- `409 Conflict`: 文件已存在（doc_hash 重複）
- `413 Payload Too Large`: 檔案過大
- `401 Unauthorized`: 未登入
- `403 Forbidden`: 無上傳權限（非管理員）

---

### 2. 列出文件

**端點**: `GET /api/documents/list?page=1&page_size=20`

**回應** (200 OK):
```json
[
  {
    "id": "doc_abc123",
    "file_path": "data/raw/典籍.pdf",
    "doc_hash": "sha256_hash",
    "chunk_count": 42,
    "created_at": "2026-03-20T10:40:00Z"
  },
  ...
]
```

**查詢參數**:
- `page` (int, 預設 1): 頁碼
- `page_size` (int, 預設 20): 每頁筆數

---

### 3. 刪除文件

**端點**: `DELETE /api/documents/{doc_id}`

**回應** (204 No Content):
```
(empty)
```

**錯誤**:
- `404 Not Found`: 文件不存在
- `403 Forbidden`: 無刪除權限（非管理員）

---

## Session 管理（Sessions）

### 1. 列出 Session

**端點**: `GET /api/sessions?page=1&page_size=20`

**回應** (200 OK):
```json
[
  {
    "id": 1,
    "title": "三寶的含義",
    "message_count": 5,
    "created_at": "2026-03-20T10:00:00Z",
    "updated_at": "2026-03-20T10:35:00Z"
  },
  ...
]
```

---

### 2. 建立 Session

**端點**: `POST /api/sessions`

**請求**:
```json
{
  "title": "新對話"
}
```

**回應** (201 Created):
```json
{
  "id": 2,
  "title": "新對話",
  "message_count": 0,
  "created_at": "2026-03-20T10:50:00Z",
  "updated_at": "2026-03-20T10:50:00Z"
}
```

**錯誤**:
- `403 Forbidden`: Session 數已超過使用者限制

---

### 3. 更新 Session

**端點**: `PATCH /api/sessions/{session_id}`

**請求**:
```json
{
  "title": "重新命名的對話"
}
```

**回應** (200 OK):
```json
{
  "id": 1,
  "title": "重新命名的對話",
  "message_count": 5,
  "created_at": "2026-03-20T10:00:00Z",
  "updated_at": "2026-03-20T10:55:00Z"
}
```

---

### 4. 刪除 Session

**端點**: `DELETE /api/sessions/{session_id}`

**回應** (204 No Content):
```
(empty)
```

---

## 管理員（Admin）

### 1. 列出所有使用者

**端點**: `GET /api/admin/users?page=1&page_size=20`

**需要**: Admin 角色

**回應** (200 OK):
```json
[
  {
    "id": 1,
    "username": "john_doe",
    "role": "user",
    "max_sessions": 5,
    "created_at": "2026-03-20T10:00:00Z"
  },
  ...
]
```

---

### 2. 建立使用者

**端點**: `POST /api/admin/users`

**需要**: Admin 角色

**請求**:
```json
{
  "username": "new_user",
  "password": "SecurePassword123!",
  "role": "user",
  "max_sessions": 5
}
```

**回應** (201 Created):
```json
{
  "id": 10,
  "username": "new_user",
  "role": "user",
  "max_sessions": 5,
  "created_at": "2026-03-20T11:00:00Z"
}
```

---

### 3. 編輯使用者

**端點**: `PATCH /api/admin/users/{user_id}`

**需要**: Admin 角色

**請求** (所有欄位可選):
```json
{
  "password": "NewPassword123!",
  "role": "admin",
  "max_sessions": 10
}
```

**回應** (200 OK):
```json
{
  "id": 10,
  "username": "new_user",
  "role": "admin",
  "max_sessions": 10,
  "created_at": "2026-03-20T11:00:00Z"
}
```

---

### 4. 刪除使用者

**端點**: `DELETE /api/admin/users/{user_id}`

**需要**: Admin 角色

**回應** (204 No Content):
```
(empty)
```

**錯誤**:
- `400 Bad Request`: 無法刪除唯一的管理員

---

## 系統端點（System）

### 1. 健康檢查

**端點**: `GET /health`

**回應** (200 OK):
```json
{
  "status": "ok",
  "timestamp": "2026-03-20T11:05:00Z"
}
```

---

### 2. Prometheus 指標

**端點**: `GET /metrics`

**回應** (200 OK, `text/plain`):
```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{method="POST",path="/api/chat/query",status="200"} 125.0
...
```

---

### 3. API 文件（開發環境）

**端點**: `GET /docs`

**回應**: 互動式 Swagger UI

---

## 錯誤處理

### 標準錯誤回應

```json
{
  "detail": "錯誤描述訊息"
}
```

### 常見 HTTP 狀態碼

| 狀態碼 | 含義 |
|--------|------|
| 200 | 成功 |
| 201 | 建立成功 |
| 204 | 刪除成功（無回應內容） |
| 400 | 請求格式錯誤或驗證失敗 |
| 401 | 未認証（Token 缺失或無效） |
| 403 | 無權限（權限不足） |
| 404 | 資源不存在 |
| 409 | 衝突（例如帳號已存在） |
| 429 | 請求過於頻繁（Rate Limit） |
| 500 | 伺服器錯誤 |

---

## Rate Limiting

系統根據來源 IP 進行速率限制：

- **聊天 API**: 每分鐘 100 個請求
- **上傳 API**: 每分鐘 10 個請求
- **其他 API**: 預設無限制

超過限制時會返回 `429 Too Many Requests`。

---

## 認證流程範例

### 完整使用者旅程

```bash
# 1. 註冊帳號
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "password": "Alice@12345"
  }'

# 回應：
# {
#   "id": 5,
#   "username": "alice",
#   "role": "user",
#   "created_at": "2026-03-20T11:10:00Z"
# }

# 2. 登入取得 Token
RESPONSE=$(curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "alice",
    "password": "Alice@12345"
  }')

TOKEN=$(echo $RESPONSE | jq -r '.access_token')

# 3. 建立新 Session
curl -X POST http://localhost:8000/api/sessions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "我的第一個對話"}'

# 回應：
# {
#   "id": 3,
#   "title": "我的第一個對話",
#   "message_count": 0,
#   ...
# }

# 4. 發送問題
curl -X POST http://localhost:8000/api/chat/query \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "question": "三寶是什麼？",
    "session_id": "3"
  }'
```

---

## 範例實作

### Python 客戶端

```python
import requests
import json

class DaohuiClient:
    def __init__(self, base_url="http://localhost:8000", username=None, password=None):
        self.base_url = base_url
        self.token = None
        if username and password:
            self.login(username, password)

    def login(self, username: str, password: str):
        resp = requests.post(
            f"{self.base_url}/api/auth/login",
            json={"username": username, "password": password}
        )
        resp.raise_for_status()
        self.token = resp.json()["access_token"]

    def ask(self, question: str, session_id: str = None) -> str:
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.post(
            f"{self.base_url}/api/chat/query/sync",
            headers=headers,
            json={"question": question, "session_id": session_id}
        )
        resp.raise_for_status()
        return resp.json()["answer"]

    def ask_stream(self, question: str, session_id: str = None):
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = requests.post(
            f"{self.base_url}/api/chat/query",
            headers=headers,
            json={"question": question, "session_id": session_id},
            stream=True
        )
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line.startswith(b"data: "):
                token = line[6:].decode()
                if token != "[DONE]":
                    yield token

# 使用範例
client = DaohuiClient(username="alice", password="Alice@12345")
answer = client.ask("三寶是什麼？")
print(answer)

# 串流使用
for token in client.ask_stream("十條大願是什麼？"):
    print(token, end="", flush=True)
```

---

## 安全注意事項

1. **Token 保管**：不要將 Token 暴露在前端程式碼中；使用 HttpOnly Cookie 或 Secure Storage
2. **CORS**：確保 `CORS_ORIGINS` 環境變數設定正確，勿設為 `*`
3. **HTTPS**：生產環境必須使用 HTTPS 傳輸敏感資訊
4. **Rate Limiting**：觀察自己的應用是否超過速率限制，調整使用模式
5. **輸入驗證**：所有 API 均會執行安全檢查；不要依賴前端驗證

---

## 更新日誌

- **2026-03-20**: 初版文件，包含全部 API 端點
- Session 管理 API 已上線
- 管理員 API 已上線
- 文件上傳端點已上線
