#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
AI_DIRECTORY="${EIDOLON_SOURCE_AI_DIRECTORY:-$TASK_ROOT/tmp/local-ai}"
if [[ ! -x "$AI_DIRECTORY/runtime/bin/ollama" ]]; then
  echo 'Runtime Ollama absent : consulter docs/SOURCE-LIBRARY.md.' >&2
  exit 1
fi
mkdir -p -- "$AI_DIRECTORY/models"
export OLLAMA_HOST=127.0.0.1:11435
export OLLAMA_MODELS="$AI_DIRECTORY/models"
export OLLAMA_NUM_PARALLEL=1
export OLLAMA_MAX_LOADED_MODELS=1
export OLLAMA_MAX_QUEUE=1
export OLLAMA_NO_CLOUD=1
export OLLAMA_KEEP_ALIVE=0
exec nice -n 19 "$AI_DIRECTORY/runtime/bin/ollama" serve
