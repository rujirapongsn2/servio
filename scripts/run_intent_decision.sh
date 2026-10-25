#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$repo_root/server"
export MPLCONFIGDIR="${MPLCONFIGDIR:-$repo_root/server/decision_service/.cache/matplotlib}"
exec "${INTENT_DECISION_PYTHON:-$repo_root/server/decision_service/.venv/bin/python}" -m decision_service.service
