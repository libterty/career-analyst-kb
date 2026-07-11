#!/usr/bin/env bash
# Langfuse end-to-end trace verification.
#
# Sends one request through VoltAgent → kb-api and checks that a linked
# trace appears in Langfuse within 10 seconds.
#
# Prerequisites:
#   - LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY, LANGFUSE_BASE_URL in .env
#   - VoltAgent running  (default: http://localhost:3141)
#   - kb-api running     (default: http://localhost:8000)
#
# Usage:
#   ./scripts/verify_langfuse_trace.sh
#   VOLTAGENT_URL=http://localhost:3141 ./scripts/verify_langfuse_trace.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$REPO_ROOT/.env" ]] && set -a && source "$REPO_ROOT/.env" && set +a || true

VOLTAGENT_URL="${VOLTAGENT_URL:-http://localhost:3141}"
LANGFUSE_BASE_URL="${LANGFUSE_BASE_URL:-https://cloud.langfuse.com}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }
die() { log "FAIL: $*" >&2; exit 1; }

# ── Preflight ─────────────────────────────────────────────────────────────────

[[ -n "${LANGFUSE_PUBLIC_KEY:-}" ]]  || die "LANGFUSE_PUBLIC_KEY not set"
[[ -n "${LANGFUSE_SECRET_KEY:-}" ]]  || die "LANGFUSE_SECRET_KEY not set"
command -v curl &>/dev/null          || die "curl not found"
command -v jq   &>/dev/null          || die "jq not found"

log "VoltAgent: $VOLTAGENT_URL"
log "Langfuse:  $LANGFUSE_BASE_URL"

# ── Step 1: send a test query through VoltAgent ───────────────────────────────

log "Sending test query to VoltAgent ..."

BEFORE_TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

log "Sending test query (this may take ~90 s for LLM inference) ..."
RESPONSE=$(curl -s -X POST "$VOLTAGENT_URL/agents/CareerLeadAgent/text" \
  -H "Content-Type: application/json" \
  -d '{"input": "面試中如何展現領導力？"}' \
  --max-time 180) \
  || die "VoltAgent request failed (timeout or network error)"

SUCCESS=$(echo "$RESPONSE" | jq -r '.success // false' 2>/dev/null || echo false)
[[ "$SUCCESS" == "true" ]] || die "VoltAgent returned success=false: $(echo "$RESPONSE" | head -c 200)"
log "VoltAgent answered successfully"

# ── Step 2: poll Langfuse for a new trace and rag-retrieve span ───────────────

LANGFUSE_AUTH=$(printf '%s:%s' "$LANGFUSE_PUBLIC_KEY" "$LANGFUSE_SECRET_KEY" | base64)
log "Polling Langfuse for new traces since $BEFORE_TS ..."

for i in $(seq 1 5); do
  sleep 5

  # Get latest trace
  TRACE_JSON=$(curl -s \
    -H "Authorization: Basic $LANGFUSE_AUTH" \
    "$LANGFUSE_BASE_URL/api/public/traces?limit=1&orderBy=timestamp.desc") || continue

  TRACE_ID=$(echo "$TRACE_JSON" | jq -r '.data[0].id // empty' 2>/dev/null || true)
  [[ -z "$TRACE_ID" ]] && continue

  # Check for rag-retrieve observations
  OBS_JSON=$(curl -s \
    -H "Authorization: Basic $LANGFUSE_AUTH" \
    "$LANGFUSE_BASE_URL/api/public/observations?limit=5&name=rag-retrieve") || continue

  RAG_COUNT=$(echo "$OBS_JSON" | jq '[.data[] | select(.startTime > "'"$BEFORE_TS"'")] | length' 2>/dev/null || echo 0)

  if [[ "$RAG_COUNT" -gt 0 ]]; then
    RAG_TRACE=$(echo "$OBS_JSON" | jq -r '[.data[] | select(.startTime > "'"$BEFORE_TS"'")][0].traceId' 2>/dev/null)
    log "PASS — VoltAgent trace=$TRACE_ID"
    log "PASS — $RAG_COUNT rag-retrieve span(s) from kb-api linked to traceId=$RAG_TRACE"
    log "View: $LANGFUSE_BASE_URL/trace/$TRACE_ID"
    exit 0
  fi

  log "Attempt $i/5 — no new rag-retrieve spans yet, retrying in 5 s ..."
done

die "No rag-retrieve spans appeared in Langfuse after 25 s — check kb-api LANGFUSE_* env and docker-compose"
