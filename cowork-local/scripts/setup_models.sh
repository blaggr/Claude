#!/usr/bin/env bash
# First-time model setup: pull the newest Qwen and GLM models and record the
# app default. Re-runnable any time to refresh to the latest.
#
# Usage:
#   ./scripts/setup_models.sh            # default primary = qwen
#   ./scripts/setup_models.sh --primary glm
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama is not installed. Install it from https://ollama.com first." >&2
  exit 1
fi

# Make sure the daemon is up (pulls need it).
if ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Starting Ollama…"
  ollama serve >/dev/null 2>&1 &
  for _ in $(seq 1 20); do
    curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break
    sleep 0.5
  done
fi

python3 "$SCRIPT_DIR/update_models.py" "$@"
echo
echo "Done. Launch the app with 'npm run tauri dev' and your newest Qwen/GLM"
echo "model will be selected automatically."
