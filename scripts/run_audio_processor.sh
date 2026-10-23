#!/usr/bin/env bash
set -euo pipefail
: "${KNOWLEDGE_AUDIO_WHISPER_CLI:?Set the local whisper.cpp CLI path}"
: "${KNOWLEDGE_AUDIO_WHISPER_MODEL:?Set the local whisper model path}"
: "${KNOWLEDGE_AUDIO_VAD_MODEL:?Set the local Silero VAD model path}"
: "${KNOWLEDGE_AUDIO_ASR_REVISION:?Set the exact ASR and VAD weight revisions}"
for binary in ffmpeg ffprobe; do command -v "$binary" >/dev/null; done
for asset in "$KNOWLEDGE_AUDIO_WHISPER_CLI" "$KNOWLEDGE_AUDIO_WHISPER_MODEL" "$KNOWLEDGE_AUDIO_VAD_MODEL"; do
  test -f "$asset" || { echo "Missing local processor asset: $asset" >&2; exit 1; }
done
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root/server"
exec "${KNOWLEDGE_AUDIO_PYTHON:-$repo_root/server/.venv/bin/python}" -m uvicorn audio_processor.service:app --host "${KNOWLEDGE_AUDIO_BIND:-127.0.0.1}" --port "${KNOWLEDGE_AUDIO_PORT:-8094}" --workers 1 --limit-concurrency 4 --timeout-keep-alive 5
