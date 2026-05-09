#!/usr/bin/env bash

# Backward-compatible entrypoint. Prefer ./services.sh for day-to-day use.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "Servio now uses ./services.sh for service management."
echo ""
echo "Common commands:"
echo "  ./services.sh start"
echo "  ./services.sh restart frontend"
echo "  ./services.sh rebuild backend"
echo "  ./services.sh stop"
echo "  ./services.sh status"
echo "  ./services.sh update"
echo ""
echo "Starting all services. If you pass a services.sh command, it will be forwarded."
echo ""

case "${1:-}" in
  start|stop|restart|rebuild|build|status|ps|logs|log|update|help|-h|--help)
    exec "$ROOT_DIR/services.sh" "$@"
    ;;
  *)
    exec "$ROOT_DIR/services.sh" start "$@"
    ;;
esac
