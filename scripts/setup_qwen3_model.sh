#!/usr/bin/env bash
# Download Qwen3-30B-A3B and register with Ollama at 16K context.
# Usage: ./scripts/setup_qwen3_model.sh

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
MODELFILE="${REPO_ROOT}/models/Modelfile.qwen3-30b"
OLLAMA_NAME="qwen3-30b-a3b"
BASE_MODEL="qwen3:30b-a3b-q4_K_M"

echo "=== Qwen3-30B-A3B Setup ==="

# 1. Pull base model from Ollama (resumes if interrupted)
echo "[1/2] Pulling ${BASE_MODEL} (~18 GB)..."
ollama pull "${BASE_MODEL}"

# 2. Create custom model with 16K context
echo "[2/2] Registering '${OLLAMA_NAME}' with num_ctx=16384..."
ollama create "${OLLAMA_NAME}" -f "${MODELFILE}"

echo ""
echo "=== Done ==="
echo "Smoke test  : ollama run ${OLLAMA_NAME} 'Say hello in one sentence'"
echo "Memory check: ollama ps"
