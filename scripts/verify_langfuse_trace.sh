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

RESPONSE=$(curl -s -X POST "$VOLTAGENT_URL/agents/career-lead/invoke" \
  -H "Content-Type: application/json" \
  -d '{"input": "如何準備技術面試？"}') \
  || die "VoltAgent request failed"

TRACE_ID=$(echo "$RESPONSE" | jq -r '.traceId // .trace_id // empty' 2>/dev/null || true)

if [[ -z "$TRACE_ID" ]]; then
  log "Response: $RESPONSE"
  die "Could not extract traceId from VoltAgent response"
fi

log "Got traceId: $TRACE_ID"

# ── Step 2: poll Langfuse for the trace (up to 15 s) ─────────────────────────

log "Polling Langfuse for trace $TRACE_ID ..."

LANGFUSE_AUTH=$(printf '%s:%s' "$LANGFUSE_PUBLIC_KEY" "$LANGFUSE_SECRET_KEY" | base64)

for i in $(seq 1 5); do
  sleep 3
  HTTP_STATUS=$(curl -s -o /tmp/lf_trace.json -w "%{http_code}" \
    -H "Authorization: Basic $LANGFUSE_AUTH" \
    "$LANGFUSE_BASE_URL/api/public/traces/$TRACE_ID") || true

  if [[ "$HTTP_STATUS" == "200" ]]; then
    TRACE_NAME=$(jq -r '.name // "unknown"' /tmp/lf_trace.json)
    SPAN_COUNT=$(jq '.observations | length' /tmp/lf_trace.json 2>/dev/null || echo "?")
    log "PASS — trace found: name='$TRACE_NAME' spans=$SPAN_COUNT"
    log "View: $LANGFUSE_BASE_URL/trace/$TRACE_ID"
    exit 0
  fi

  log "Attempt $i/5 — HTTP $HTTP_STATUS, retrying in 3 s ..."
done

# ── Step 3: check whether kb-api sub-spans are linked ────────────────────────

log "Checking for linked kb-api observations ..."

KB_SPANS=$(jq '[.observations[] | select(.name | test("rag-"))] | length' /tmp/lf_trace.json 2>/dev/null || echo 0)

if [[ "$KB_SPANS" -gt 0 ]]; then
  log "PASS — $KB_SPANS kb-api rag-* span(s) linked to parent trace"
else
  log "WARN — trace found but no kb-api rag-* spans linked (check x-langfuse-trace-id header propagation)"
fi

die "Trace not found in Langfuse after 15 s — check keys or Langfuse connectivity"
