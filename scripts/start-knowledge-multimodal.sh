#!/usr/bin/env bash
set -euo pipefail

: "${MULTIMODAL_MODEL_PATH:?Set MULTIMODAL_MODEL_PATH to embeddinggemma-2 GGUF}"
: "${MULTIMODAL_MMPROJ_PATH:?Set MULTIMODAL_MMPROJ_PATH to its matching mmproj GGUF}"

multimodal_binary="${LLAMA_SERVER_BIN:-llama-server}"
multimodal_port="${MULTIMODAL_PORT:-8092}"
multimodal_threads="${MULTIMODAL_THREADS:-2}"

if [[ ! -f "$MULTIMODAL_MODEL_PATH" || ! -f "$MULTIMODAL_MMPROJ_PATH" ]]; then
  echo "Model and projector files must exist locally." >&2
  exit 1
fi
if [[ ! "$multimodal_port" =~ ^[0-9]+$ ]] || (( multimodal_port < 1024 || multimodal_port > 65535 )); then
  echo "MULTIMODAL_PORT must be between 1024 and 65535." >&2
  exit 1
fi
if [[ "$multimodal_port" == 8090 || "$multimodal_port" == 8091 ]]; then
  echo "Choose a separate port; 8090 and 8091 are reserved for existing services." >&2
  exit 1
fi
if [[ ! "$multimodal_threads" =~ ^[0-9]+$ ]] || (( multimodal_threads < 1 || multimodal_threads > 8 )); then
  echo "MULTIMODAL_THREADS must be between 1 and 8." >&2
  exit 1
fi

exec "$multimodal_binary" \
  -m "$MULTIMODAL_MODEL_PATH" --mmproj "$MULTIMODAL_MMPROJ_PATH" \
  --embeddings --host 127.0.0.1 --port "$multimodal_port" \
  --alias servio-embeddinggemma2-images \
  -ngl 0 --no-mmproj-offload -t "$multimodal_threads" \
  -c 8192 -b 2048 -ub 2048 --parallel 1 --image-max-tokens 256 \
  --cors-origins localhost --no-cors-credentials --no-webui
