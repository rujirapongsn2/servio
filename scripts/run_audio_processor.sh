#!/usr/bin/env bash
set -euo pipefail
for binary in ffmpeg ffprobe; do command -v "$binary" >/dev/null; done
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root/server"
exec "${KNOWLEDGE_AUDIO_PYTHON:-$repo_root/server/.venv/bin/python}" -m uvicorn audio_processor.service:app --host "${KNOWLEDGE_AUDIO_BIND:-127.0.0.1}" --port "${KNOWLEDGE_AUDIO_PORT:-8094}" --workers 1 --limit-concurrency 4 --timeout-keep-alive 5
