#!/usr/bin/env bash
# Phase D — Event-Driven Ingest Loop
#
# Downloads subtitles for any new @hrjasmin videos not yet in data/subtitles/,
# converts VTT → text, then runs the incremental ingest into Milvus.
#
# Designed to run as a cron job:
#   0 2 * * * /path/to/repo/scripts/check_new_videos.sh >> /path/to/repo/logs/check_new_videos.log 2>&1
#
# Usage:
#   ./scripts/check_new_videos.sh
#   ./scripts/check_new_videos.sh --dry-run   # fetch + convert, skip Milvus write
#   ./scripts/check_new_videos.sh --force     # re-ingest already-seen videos
#
# Dependencies: yt-dlp (any recent version), python3 (with kb-api venv)

set -euo pipefail

# ── Paths ────────────────────────────────────────────────────────────────────

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUBTITLE_DIR="$REPO_ROOT/data/subtitles"
LOG_DIR="$REPO_ROOT/logs"
RUN_LOG="$LOG_DIR/check_new_videos.log"
ARCHIVE_FILE="$SUBTITLE_DIR/.yt_dlp_archive"

KB_API_DIR="$REPO_ROOT/services/kb-api"
PYTHON="$KB_API_DIR/venv/bin/python"

CHANNEL_URL="https://www.youtube.com/@hrjasmin"

# ── Args ─────────────────────────────────────────────────────────────────────

DRY_RUN=0
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    --force)   FORCE=1 ;;
  esac
done

# ── Helpers ──────────────────────────────────────────────────────────────────

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

die() { log "ERROR: $*" >&2; exit 1; }

require_cmd() { command -v "$1" &>/dev/null || die "'$1' not found in PATH"; }

# Send a Slack (or generic) webhook notification if SLACK_WEBHOOK_URL is set.
# Usage: notify "message text"
notify() {
  local msg="$1"
  if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
    return 0
  fi
  curl -s -o /dev/null -X POST "$SLACK_WEBHOOK_URL" \
    -H "Content-Type: application/json" \
    -d "{\"text\": \"$msg\"}" \
    || log "WARNING: Slack notification failed (non-fatal)"
}

# ── Load .env (optional) ─────────────────────────────────────────────────────
# Sources SLACK_WEBHOOK_URL and other overrides if present.

[[ -f "$REPO_ROOT/.env" ]] && set -a && source "$REPO_ROOT/.env" && set +a || true

# ── Preflight ─────────────────────────────────────────────────────────────────

mkdir -p "$LOG_DIR" "$SUBTITLE_DIR"

require_cmd yt-dlp
[[ -x "$PYTHON" ]] || die "Python venv not found at $KB_API_DIR/venv — run: cd $KB_API_DIR && python -m venv venv && pip install -e ."

log "=== check_new_videos start (dry_run=$DRY_RUN force=$FORCE) ==="

# ── Step 1: Download new subtitles ───────────────────────────────────────────
# yt-dlp archive prevents re-downloading already-fetched videos.
# --date-after prevents fetching the entire backlog on first run
# (set to a date before the earliest existing VTT to include everything).

EARLIEST_VTT=$(ls "$SUBTITLE_DIR"/*.vtt 2>/dev/null \
  | sed -E 's|.*/([0-9]{8})_.*|\1|' | sort | head -1 || true)
DATE_AFTER="${EARLIEST_VTT:-20221001}"

log "Fetching subtitle list for $CHANNEL_URL (date_after=$DATE_AFTER) ..."

# Build yt-dlp flags
YTDLP_FLAGS=(
  --skip-download
  --write-auto-sub
  --sub-lang "zh-TW,zh-Hant,zh"
  --convert-subs vtt
  --output "$SUBTITLE_DIR/%(upload_date)s_%(id)s_%(title)s.%(ext)s"
  --restrict-filenames
  --date-after "$DATE_AFTER"
  --ignore-errors
  --no-warnings
  --quiet
)

# Use archive file to skip already-downloaded videos (idempotent)
if [[ $FORCE -eq 0 ]]; then
  YTDLP_FLAGS+=(--download-archive "$ARCHIVE_FILE")
fi

if [[ $DRY_RUN -eq 1 ]]; then
  log "[dry-run] Would run: yt-dlp ${YTDLP_FLAGS[*]} $CHANNEL_URL/videos"
else
  # Count VTTs before
  BEFORE=$(ls "$SUBTITLE_DIR"/*.vtt 2>/dev/null | wc -l | tr -d ' ')

  yt-dlp "${YTDLP_FLAGS[@]}" "$CHANNEL_URL/videos" \
    || log "yt-dlp exited non-zero (some videos may have no subtitles — normal)"

  AFTER=$(ls "$SUBTITLE_DIR"/*.vtt 2>/dev/null | wc -l | tr -d ' ')
  NEW_VTT=$(( AFTER - BEFORE ))
  log "Subtitle download complete: $BEFORE → $AFTER VTTs (+$NEW_VTT new)"

  if [[ $NEW_VTT -eq 0 && $FORCE -eq 0 ]]; then
    log "No new videos found. Exiting."
    exit 0
  fi
fi

# ── Step 2: Convert VTT → plain text ─────────────────────────────────────────

log "Converting VTT → text ..."

if [[ $DRY_RUN -eq 1 ]]; then
  log "[dry-run] Would run: $PYTHON $KB_API_DIR/scripts/vtt_to_text.py"
else
  "$PYTHON" "$KB_API_DIR/scripts/vtt_to_text.py"
fi

# ── Step 3: Incremental ingest into Milvus ────────────────────────────────────

INGEST_FLAGS=(--incremental)
if [[ $DRY_RUN -eq 1 ]]; then
  INGEST_FLAGS+=(--dry-run)
fi

log "Running incremental ingest (flags: ${INGEST_FLAGS[*]}) ..."

(
  cd "$KB_API_DIR"
  "$PYTHON" scripts/ingest_youtube.py "${INGEST_FLAGS[@]}"
) && log "Ingest complete." || { log "Ingest failed — check above for errors."; exit 1; }

notify ":new: career-analyst-kb: ingested *$NEW_VTT* new @hrjasmin video(s) into Milvus ($(date '+%Y-%m-%d %H:%M'))"

log "=== check_new_videos done ==="
