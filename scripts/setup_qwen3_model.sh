#!/usr/bin/env bash
# Download Qwen3-30B-A3B Q4_K_M GGUF and register with Ollama.
# Requirements: ollama installed, pip available, ~20GB free in ~/Downloads
# Usage: ./scripts/setup_qwen3_model.sh

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HF_REPO="bartowski/Qwen3-30B-A3B-GGUF"
GGUF_FILE="Qwen3-30B-A3B-Q4_K_M.gguf"
STAGING="${HOME}/Downloads/qwen3-gguf"
MODELFILE="${REPO_ROOT}/models/Modelfile.qwen3-30b"
OLLAMA_NAME="qwen3-30b-a3b"

echo "=== Qwen3-30B-A3B Setup ==="
echo "Repo  : ${HF_REPO}"
echo "File  : ${GGUF_FILE} (~20 GB)"
echo "Dest  : ${STAGING}"
echo ""

# 1. Prerequisites
command -v ollama >/dev/null 2>&1 || { echo "ERROR: ollama not found. Install from https://ollama.com"; exit 1; }

if ! command -v huggingface-cli >/dev/null 2>&1; then
  echo "Installing huggingface_hub..."
  pip install -q huggingface_hub
fi

# 2. Download GGUF
mkdir -p "$STAGING"
echo "[1/3] Downloading GGUF..."
huggingface-cli download "${HF_REPO}" "${GGUF_FILE}" \
  --local-dir "${STAGING}" \
  --local-dir-use-symlinks False

# 3. Patch GGUF path into Modelfile
echo "[2/3] Patching Modelfile with GGUF path..."
sed "s|/GGUF_PATH_PLACEHOLDER|${STAGING}/${GGUF_FILE}|" \
  "${MODELFILE}" > /tmp/Modelfile.qwen3-30b.resolved

# 4. Register with Ollama
echo "[3/3] Registering '${OLLAMA_NAME}' with Ollama..."
ollama create "${OLLAMA_NAME}" -f /tmp/Modelfile.qwen3-30b.resolved

echo ""
echo "=== Done ==="
echo "Smoke test : ollama run ${OLLAMA_NAME} 'Say hello in one sentence'"
echo "Memory check: ollama ps  (expect Metal backend, ~20 GB)"
