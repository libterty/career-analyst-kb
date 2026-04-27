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

# 2. Download GGUF
mkdir -p "$STAGING"
DEST="${STAGING}/${GGUF_FILE}"

# Resume-capable: skip if already fully downloaded
if [[ -f "$DEST" ]]; then
  echo "[1/3] Already downloaded: ${DEST}"
else
  echo "[1/3] Downloading GGUF (resume-capable, shows % progress)..."
  curl -L --progress-bar --continue-at - \
    "https://huggingface.co/${HF_REPO}/resolve/main/${GGUF_FILE}" \
    -o "$DEST"
fi

# 3. Patch GGUF path into Modelfile
echo "[2/3] Patching Modelfile with GGUF path..."
sed "s|/GGUF_PATH_PLACEHOLDER|${DEST}|" \
  "${MODELFILE}" > /tmp/Modelfile.qwen3-30b.resolved

# 4. Register with Ollama
echo "[3/3] Registering '${OLLAMA_NAME}' with Ollama..."
ollama create "${OLLAMA_NAME}" -f /tmp/Modelfile.qwen3-30b.resolved

echo ""
echo "=== Done ==="
echo "Smoke test : ollama run ${OLLAMA_NAME} 'Say hello in one sentence'"
echo "Memory check: ollama ps  (expect Metal backend, ~20 GB)"
