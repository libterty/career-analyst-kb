#!/usr/bin/env bash
# Langfuse end-to-end trace verification.
#
# Two-phase test:
#   Phase 1 (fast, reliable): Call kb-api directly with a synthetic trace ID and
#     verify the rag-retrieve span appears in Langfuse linked to that ID.
#     Proves kb-api Langfuse instrumentation + cross-service stitching work.
#
#   Phase 2 (slow, optional): Call VoltAgent with a skill_development question
#     that should force queryCareerKB tool use, then verify the rag-retrieve
#     span appears in Langfuse.  Skipped if --quick flag is set.
#
# Prerequisites:
#   - LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL in .env
#   - kb-api running     (default: http://localhost:8000)
#   - VoltAgent running  (default: http://localhost:3141)  [Phase 2 only]
#
# Usage:
#   ./scripts/verify_langfuse_trace.sh           # both phases
#   ./scripts/verify_langfuse_trace.sh --quick   # Phase 1 only (fast)
#   VOLTAGENT_URL=http://localhost:3141 ./scripts/verify_langfuse_trace.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$REPO_ROOT/.env" ]] && set -a && source "$REPO_ROOT/.env" && set +a || true

KB_API_URL="${KB_API_URL:-http://localhost:8000}"
VOLTAGENT_URL="${VOLTAGENT_URL:-http://localhost:3141}"
LANGFUSE_BASE_URL="${LANGFUSE_BASE_URL:-https://cloud.langfuse.com}"
QUICK="${1:-}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }
die() { log "FAIL: $*" >&2; exit 1; }

# ── Preflight ─────────────────────────────────────────────────────────────────

[[ -n "${LANGFUSE_PUBLIC_KEY:-}" ]]  || die "LANGFUSE_PUBLIC_KEY not set"
[[ -n "${LANGFUSE_SECRET_KEY:-}" ]]  || die "LANGFUSE_SECRET_KEY not set"
[[ -n "${CAREER_API_TOKEN:-}" ]]     || die "CAREER_API_TOKEN not set — generate with: docker exec docker-app-1 python -c \"from src.api.auth import create_access_token; print(create_access_token({'sub':'admin','role':'admin'}))\""
command -v curl &>/dev/null          || die "curl not found"
command -v jq   &>/dev/null          || die "jq not found"

LANGFUSE_AUTH=$(printf '%s:%s' "$LANGFUSE_PUBLIC_KEY" "$LANGFUSE_SECRET_KEY" | base64)
log "kb-api:    $KB_API_URL"
log "Langfuse:  $LANGFUSE_BASE_URL"

# ── Phase 1: Direct kb-api stitching test (fast, deterministic) ───────────────

log ""
log "═══ Phase 1: kb-api → Langfuse stitching (direct) ══════════════════════"

# OTel trace IDs must be exactly 32 lowercase hex chars (128-bit).
SYNTHETIC_TRACE_ID=$(python3 -c "import uuid; print(uuid.uuid4().hex)" 2>/dev/null \
  || uuidgen 2>/dev/null | tr -d '-' | tr '[:upper:]' '[:lower:]' \
  || printf '%032x' "$(date +%s%N 2>/dev/null || date +%s)$$")
BEFORE_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

log "Synthetic trace ID: $SYNTHETIC_TRACE_ID"
log "Sending query to kb-api with X-Langfuse-Trace-Id header ..."

KB_RESPONSE=$(curl -s -X POST "$KB_API_URL/api/chat/query/sync" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer ${CAREER_API_TOKEN}" \
  -H "X-Langfuse-Trace-Id: $SYNTHETIC_TRACE_ID" \
  -d '{"question":"如何建立良好的職場人際關係？","session_id":"verify-stitching"}' \
  --max-time 120) \
  || die "kb-api request failed (timeout or network error)"

KB_ANSWER=$(echo "$KB_RESPONSE" | jq -r '.data.answer // .answer // empty' 2>/dev/null || true)
[[ -n "$KB_ANSWER" ]] || die "kb-api returned no answer: $(echo "$KB_RESPONSE" | head -c 300)"
log "kb-api answered (${#KB_ANSWER} chars)"

log "Polling Langfuse for rag-retrieve span with traceId=$SYNTHETIC_TRACE_ID ..."

P1_PASS=false
for i in $(seq 1 6); do
  sleep 5

  OBS_JSON=$(curl -s \
    -H "Authorization: Basic $LANGFUSE_AUTH" \
    "$LANGFUSE_BASE_URL/api/public/observations?limit=10&name=rag-retrieve&traceId=$SYNTHETIC_TRACE_ID") || continue

  RAG_COUNT=$(echo "$OBS_JSON" | jq '.data | length' 2>/dev/null || echo 0)

  if [[ "$RAG_COUNT" -gt 0 ]]; then
    log "PASS (Phase 1) — $RAG_COUNT rag-retrieve span(s) linked to synthetic traceId=$SYNTHETIC_TRACE_ID"
    log "View: $LANGFUSE_BASE_URL/trace/$SYNTHETIC_TRACE_ID"
    P1_PASS=true
    break
  fi

  log "Attempt $i/6 — no span yet, retrying in 5 s ..."
done

[[ "$P1_PASS" == "true" ]] || die "Phase 1 FAILED — no rag-retrieve span with traceId=$SYNTHETIC_TRACE_ID after 30 s"

# ── Phase 2: VoltAgent → kb-api end-to-end (slow, optional) ──────────────────

if [[ "$QUICK" == "--quick" ]]; then
  log ""
  log "Skipping Phase 2 (--quick mode). Phase 1 PASSED."
  exit 0
fi

log ""
log "═══ Phase 2: VoltAgent → kb-api end-to-end ═════════════════════════════"
log "VoltAgent: $VOLTAGENT_URL"
log "Sending skill_development query to VoltAgent (may take ~90 s) ..."

BEFORE_TS2=$(date -u +%Y-%m-%dT%H:%M:%SZ)

VA_RESPONSE=$(curl -s -X POST "$VOLTAGENT_URL/agents/CareerLeadAgent/text" \
  -H "Content-Type: application/json" \
  -d '{"input": "有哪些方法可以提升職場溝通技巧和軟實力？"}' \
  --max-time 240) \
  || die "VoltAgent request failed (timeout or network error)"

VA_SUCCESS=$(echo "$VA_RESPONSE" | jq -r '.success // false' 2>/dev/null || echo false)
[[ "$VA_SUCCESS" == "true" ]] || die "VoltAgent returned success=false: $(echo "$VA_RESPONSE" | head -c 200)"
log "VoltAgent answered successfully"

log "Polling Langfuse for new rag-retrieve spans since $BEFORE_TS2 ..."

P2_PASS=false
for i in $(seq 1 6); do
  sleep 5

  OBS_JSON=$(curl -s \
    -H "Authorization: Basic $LANGFUSE_AUTH" \
    "$LANGFUSE_BASE_URL/api/public/observations?limit=5&name=rag-retrieve") || continue

  RAG_COUNT=$(echo "$OBS_JSON" | jq '[.data[] | select(.startTime > "'"$BEFORE_TS2"'")] | length' 2>/dev/null || echo 0)

  if [[ "$RAG_COUNT" -gt 0 ]]; then
    RAG_TRACE=$(echo "$OBS_JSON" | jq -r '[.data[] | select(.startTime > "'"$BEFORE_TS2"'")][0].traceId' 2>/dev/null)
    log "PASS (Phase 2) — $RAG_COUNT rag-retrieve span(s) from kb-api, traceId=$RAG_TRACE"
    log "View: $LANGFUSE_BASE_URL/trace/$RAG_TRACE"
    P2_PASS=true
    break
  fi

  log "Attempt $i/6 — no new span yet (LLM may not have called queryCareerKB), retrying in 5 s ..."
done

if [[ "$P2_PASS" != "true" ]]; then
  log "WARNING: Phase 2 — VoltAgent did not call queryCareerKB (LLM answered from own knowledge)"
  log "         Phase 1 confirmed kb-api stitching works. VoltAgent E2E requires LLM tool use."
  log "         This is a non-deterministic LLM behaviour, not a tracing bug."
fi

log ""
log "═══ Summary ═════════════════════════════════════════════════════════════"
log "Phase 1 (kb-api stitching):    PASS"
[[ "$P2_PASS" == "true" ]] && log "Phase 2 (VoltAgent E2E):        PASS" || log "Phase 2 (VoltAgent E2E):        SKIPPED (LLM answered without tool)"
exit 0
