# Database Migration 指南

本專案使用 **Alembic** 管理 PostgreSQL schema 變更。
每次 migration 會同時產生兩個檔案：
- `migrations/versions/YYYYMMDD_HHMM_<rev>_<slug>.py` — Python migration（由 Alembic 執行）
- `migrations/sql/<rev>_<slug>.sql` — 對應的純 SQL（供審查與手動執行）

---

## 日常操作

### 新增 migration（改完 ORM model 後）

```bash
./scripts/make_migration.sh "描述這次變更"
# 範例：
./scripts/make_migration.sh "add email column to users"
```

會自動產生：
```
migrations/versions/20260318_1700_abc123_add_email_column_to_users.py
migrations/sql/abc123_add_email_column_to_users.sql
```

### 套用 migration 到資料庫

```bash
# 升級到最新版本
alembic upgrade head

# 升級一版
alembic upgrade +1

# 升級到指定版本
alembic upgrade <rev>
```

### 回退 migration

```bash
# 回退一版
alembic downgrade -1

# 回退到指定版本
alembic downgrade <rev>

# 回退到最初狀態
alembic downgrade base
```

### 查看目前狀態

```bash
# 目前版本
alembic current

# 所有版本歷史
alembic history --verbose

# 待執行的 migration
alembic heads
```

---

## 手動新增 migration（不連線 DB）

若不想連線 DB（例如在 CI 環境中只看 SQL 差異），可改用手動方式：

```bash
# 建立空白 migration，自己填 upgrade/downgrade 內容
alembic revision -m "描述"

# 再手動產生對應 SQL
alembic upgrade <prev_rev>:<new_rev> --sql 2>/dev/null > migrations/sql/<rev>_<slug>.sql
```

---

## 應用程式啟動時自動執行

`src/api/main.py` 的 lifespan 會在啟動時呼叫 `run_migrations()`，
等同於執行 `alembic upgrade head`。若 DB 已是最新版本，此步驟不做任何事。

---

## 環境變數

`DATABASE_URL` 需設定為 `postgresql+asyncpg://` 格式：

```dotenv
DATABASE_URL=postgresql+asyncpg://beeinventor:secret@localhost:5437/beeinventor_kb
```

Alembic 會從 `.env` 或環境變數自動讀取，不需要在 `alembic.ini` 中設定。

---

## 目錄結構

```
migrations/
├── env.py              # Alembic 環境設定（async SQLAlchemy）
├── script.py.mako      # migration 檔案模板
├── migration.md        # 本文件
├── versions/           # Python migration 檔案（請納入 git）
│   └── YYYYMMDD_HHMM_<rev>_<slug>.py
└── sql/                # 對應的純 SQL 檔案（請納入 git，供審查用）
    └── <rev>_<slug>.sql
```