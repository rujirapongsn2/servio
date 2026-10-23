#!/usr/bin/env bash
set -euo pipefail

: "${AUDIO_MODEL_PATH:?Set AUDIO_MODEL_PATH to the audio-capable EmbeddingGemma 2 BF16 GGUF}"
: "${AUDIO_MMPROJ_PATH:?Set AUDIO_MMPROJ_PATH to its matching BF16 mmproj GGUF}"

audio_binary="${LLAMA_SERVER_BIN:-llama-server}"
audio_port="${AUDIO_SERVER_PORT:-8093}"

if [[ ! -f "$AUDIO_MODEL_PATH" || ! -r "$AUDIO_MODEL_PATH" || ! -f "$AUDIO_MMPROJ_PATH" || ! -r "$AUDIO_MMPROJ_PATH" ]]; then
  echo "Model and projector must be readable local files." >&2
  exit 1
fi
if [[ ! "$audio_port" =~ ^[1-9][0-9]{3,4}$ ]] || (( audio_port < 1024 || audio_port > 65535 )); then
  echo "AUDIO_SERVER_PORT must be between 1024 and 65535, without leading zeros." >&2
  exit 1
fi
if [[ "$audio_port" == 8090 || "$audio_port" == 8091 || "$audio_port" == 8092 ]]; then
  echo "Choose a separate audio port; 8090, 8091, and 8092 are reserved for existing services." >&2
  exit 1
fi

exec "$audio_binary" \
  -m "$AUDIO_MODEL_PATH" --mmproj "$AUDIO_MMPROJ_PATH" \
  --embeddings --host 127.0.0.1 --port "$audio_port" \
  --alias servio-embeddinggemma2-audio \
  -ngl 0 --no-mmproj-offload -t 2 \
  -c 8192 -b 2048 -ub 2048 --parallel 1 \
  --cors-origins localhost --no-cors-credentials --no-webui
