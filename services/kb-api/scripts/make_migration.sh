#!/usr/bin/env bash
# 建立新的 Alembic migration 並自動產生對應的 SQL 檔案。
#
# 用法：
#   ./scripts/make_migration.sh "add xxx column to users"
#
# 執行後會在以下位置產生兩個檔案：
#   migrations/versions/YYYYMMDD_HHMM_<rev>_<slug>.py  — Python migration
#   migrations/sql/<rev>_<slug>.sql                     — 對應的 SQL (upgrade only)
#
# 需要 DATABASE_URL 環境變數（或 .env 檔案）。

set -euo pipefail

# ── 參數檢查 ─────────────────────────────────────────────
if [ $# -eq 0 ]; then
    echo "用法：$0 \"migration 描述\"" >&2
    echo "範例：$0 \"add email column to users\"" >&2
    exit 1
fi

MESSAGE="$1"

# ── 切換到專案根目錄 ──────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# ── 載入 .env（若存在）─────────────────────────────────────
if [ -f ".env" ]; then
    set -a
    # shellcheck source=/dev/null
    source .env
    set +a
fi

# ── 確認 DATABASE_URL 已設定 ──────────────────────────────
if [ -z "${DATABASE_URL:-}" ]; then
    echo "錯誤：DATABASE_URL 未設定" >&2
    exit 1
fi

# ── 取得目前 head revision（用來計算 upgrade range）──────
PREV_HEAD=$(alembic heads --verbose 2>/dev/null | grep '(head)' | awk '{print $2}' || echo "")

# ── 產生 Python migration 檔案 ────────────────────────────
echo "產生 migration：$MESSAGE"
alembic revision --autogenerate -m "$MESSAGE"

# ── 取得新的 head revision ────────────────────────────────
NEW_HEAD=$(alembic heads --verbose 2>/dev/null | grep '(head)' | awk '{print $2}')

if [ -z "$NEW_HEAD" ]; then
    echo "無法取得新的 revision ID" >&2
    exit 1
fi

# ── 產生 SQL 檔案 ────────────────────────────────────────
mkdir -p migrations/sql

# slug：從 migration 檔名中提取描述部分
MIGRATION_FILE=$(ls migrations/versions/*_"${NEW_HEAD}"_*.py 2>/dev/null | head -1)
if [ -n "$MIGRATION_FILE" ]; then
    SLUG=$(basename "$MIGRATION_FILE" .py | sed "s/.*${NEW_HEAD}_//")
else
    SLUG=$(echo "$MESSAGE" | tr ' ' '_' | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_]//g')
fi

SQL_FILE="migrations/sql/${NEW_HEAD}_${SLUG}.sql"

echo "產生 SQL 檔案：$SQL_FILE"

# upgrade range：prev_head:new_head（若無 prev_head 則從頭產生）
if [ -n "$PREV_HEAD" ] && [ "$PREV_HEAD" != "$NEW_HEAD" ]; then
    RANGE="${PREV_HEAD}:${NEW_HEAD}"
else
    RANGE="${NEW_HEAD}"
fi

alembic upgrade "$RANGE" --sql 2>/dev/null > "$SQL_FILE"

echo ""
echo "完成！"
echo "  Python: migrations/versions/$(basename "$MIGRATION_FILE")"
echo "  SQL:    $SQL_FILE"
