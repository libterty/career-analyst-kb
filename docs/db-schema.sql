-- =====================================================================
-- 一貫道知識庫系統（Yiguandao-KB）PostgreSQL 資料庫 Schema v1.0
-- =====================================================================
-- 此檔案為參考用 DDL，與 SQLAlchemy ORM（src/infrastructure/persistence/models.py）保持同步。
-- 實際建表由 SQLAlchemy + Alembic 管理，此 DDL 供開發者快速理解資料模型。
--
-- 執行方式（僅需手動初始化時）：
--     psql -U yiguandao -d yiguandao_kb -f docs/db-schema.sql
-- =====================================================================


-- ── 1. users：系統使用者 ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id               SERIAL        PRIMARY KEY,
    username         VARCHAR(50)   NOT NULL UNIQUE,
    hashed_password  VARCHAR(128)  NOT NULL,          -- bcrypt 雜湊，絕不儲存明文
    role             VARCHAR(20)   NOT NULL DEFAULT 'viewer'
                                   CHECK (role IN ('viewer', 'editor', 'admin')),
    created_at       TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- 依使用者名稱查詢索引（登入時常用）
CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);

COMMENT ON TABLE  users                  IS '系統使用者，含角色存取控制';
COMMENT ON COLUMN users.role             IS 'viewer: 只能查詢 | editor: 可上傳文件 | admin: 完整權限';
COMMENT ON COLUMN users.hashed_password  IS 'bcrypt 雜湊（passlib），不儲存明文密碼';


-- ── 2. chat_sessions：對話 Session ───────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_sessions (
    id          SERIAL       PRIMARY KEY,
    session_id  VARCHAR(64)  NOT NULL UNIQUE,         -- UUID 字串，由前端或後端產生
    user_id     INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_session_id ON chat_sessions (session_id);
CREATE INDEX IF NOT EXISTS idx_chat_sessions_user_id    ON chat_sessions (user_id);

COMMENT ON TABLE  chat_sessions            IS '群組多輪對話的 session，對應一次連續對話';
COMMENT ON COLUMN chat_sessions.session_id IS 'UUID 字串，前端或後端自動產生';
COMMENT ON COLUMN chat_sessions.user_id    IS 'NULL 表示匿名對話';


-- ── 3. chat_messages：對話訊息 ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chat_messages (
    id          SERIAL       PRIMARY KEY,
    session_id  VARCHAR(64)  NOT NULL
                             REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    role        VARCHAR(16)  NOT NULL CHECK (role IN ('user', 'assistant')),
    content     TEXT         NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_session_id ON chat_messages (session_id);

COMMENT ON TABLE  chat_messages       IS '每條問答訊息，role 區分使用者輸入與 AI 回答';
COMMENT ON COLUMN chat_messages.role  IS 'user: 使用者輸入 | assistant: AI 回答';


-- ── 4. documents：已匯入文件的 Metadata ──────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id           SERIAL        PRIMARY KEY,
    filename     VARCHAR(255)  NOT NULL,
    doc_hash     VARCHAR(32)   NOT NULL UNIQUE,        -- SHA-256 前 16 碼，用於去重
    pages        INTEGER       NOT NULL DEFAULT 0 CHECK (pages >= 0),
    chunk_count  INTEGER       NOT NULL DEFAULT 0 CHECK (chunk_count >= 0),
    uploaded_by  INTEGER       REFERENCES users(id) ON DELETE SET NULL,
    uploaded_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_doc_hash    ON documents (doc_hash);
CREATE INDEX IF NOT EXISTS idx_documents_uploaded_at ON documents (uploaded_at DESC);

COMMENT ON TABLE  documents             IS '已匯入文件的管理資訊；向量內容儲存於 Milvus';
COMMENT ON COLUMN documents.doc_hash    IS 'SHA-256 指紋（前 16 碼），防止重複匯入同一文件';
COMMENT ON COLUMN documents.chunk_count IS '切塊後的段落總數，對應 Milvus 中的向量數量';
COMMENT ON COLUMN documents.uploaded_by IS 'NULL 表示系統批次匯入（非使用者上傳）';


-- =====================================================================
-- Milvus 向量資料表（參考，非 PostgreSQL）
-- =====================================================================
-- Collection: yiguandao_kb（在 Milvus 中建立，非 PostgreSQL）
--
-- Schema:
--   chunk_id    VARCHAR(64)   NOT NULL  -- 唯一識別碼 (doc_hash + 序號)
--   doc_hash    VARCHAR(32)   NOT NULL  -- 對應 documents.doc_hash
--   source      VARCHAR(255)  NOT NULL  -- 來源文件名稱
--   section     VARCHAR(255)            -- 所屬章節（如「第三章」）
--   content     VARCHAR(65535)          -- 切塊文字內容（最長 65535 bytes）
--   token_count INTEGER                 -- tiktoken 計算的 token 數量
--   embedding   FLOAT_VECTOR(768)       -- nomic-embed-text 向量（768 維）
--
-- Index: IVF_FLAT, metric_type=IP（Inner Product，等同正規化後的 Cosine 相似度）
-- nlist=128, nprobe=16（128 個 cluster，查詢時掃描 16 個）
-- =====================================================================
