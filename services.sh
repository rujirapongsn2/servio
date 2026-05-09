#!/usr/bin/env bash

# Servio service manager
# Usage examples:
#   ./services.sh start
#   ./services.sh start frontend
#   ./services.sh restart backend
#   ./services.sh rebuild frontend
#   ./services.sh update

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

COMPOSE=(docker compose)

usage() {
  cat <<'EOF'
Servio service manager

Usage:
  ./services.sh <command> [service] [options]

Commands:
  start [service]       Start services in the background
  restart [service]     Restart running services
  rebuild [service]     Rebuild image(s), then recreate services
  stop [service]        Stop services
  status [service]      Show service status
  logs [service]        Follow service logs
  update [service]      Pull latest code, rebuild, and restart
  help                  Show this help

Services:
  all                   Full stack: postgres, backend, frontend, nginx
  frontend              Frontend plus required backend/proxy dependencies
  backend               Backend plus database/proxy dependencies
  postgres | db         PostgreSQL only
  nginx | proxy         Reverse proxy only

Options:
  -f, --foreground      For start: run in foreground
  --no-cache            For rebuild/update: rebuild images without cache
  --kill-ports          Kill non-Docker processes using ports 80/443 before start
  --allow-dirty         For update: allow git pull with local changes

Examples:
  ./services.sh start
  ./services.sh start frontend
  ./services.sh restart backend
  ./services.sh rebuild frontend --no-cache
  ./services.sh logs backend
  ./services.sh update
EOF
}

info() {
  echo -e "${BLUE}$*${NC}"
}

success() {
  echo -e "${GREEN}$*${NC}"
}

warn() {
  echo -e "${YELLOW}$*${NC}"
}

fail() {
  echo -e "${RED}ERROR: $*${NC}" >&2
  exit 1
}

check_docker() {
  command -v docker >/dev/null 2>&1 || fail "Docker is not installed."
  docker ps >/dev/null 2>&1 || fail "Docker daemon is not running or Docker socket is not accessible. Start Docker Desktop, then try again."
  docker compose version >/dev/null 2>&1 || fail "Docker Compose is not available."
}

ensure_env() {
  if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
      fail ".env file not found. Create it first: cp .env.example .env, then add OPENAI_API_KEY."
    fi
    fail ".env file not found. Create .env with at least OPENAI_API_KEY."
  fi

  if ! grep -E '^OPENAI_API_KEY=.+$' .env >/dev/null 2>&1; then
    warn "OPENAI_API_KEY is not set in .env. Services may start but agent calls will fail."
  fi
}

generate_certs() {
  local cert_dir="nginx/certs"
  local cert_file="$cert_dir/server.crt"
  local key_file="$cert_dir/server.key"

  if [ -f "$cert_file" ] && [ -f "$key_file" ]; then
    return 0
  fi

  command -v openssl >/dev/null 2>&1 || fail "openssl is required to generate local HTTPS certificates."

  info "Generating local HTTPS certificates..."
  mkdir -p "$cert_dir"
  openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout "$key_file" \
    -out "$cert_file" \
    -subj "/C=TH/ST=Bangkok/L=Bangkok/O=Servio/CN=localhost" >/dev/null 2>&1
  success "Generated certificates in $cert_dir"
}

show_urls() {
  cat <<'EOF'

Servio is available at:
  Frontend:    https://localhost
  Backend API: https://localhost/api
  WebSocket:   wss://localhost/ws
  Admin:       https://localhost/admin

EOF
}

refresh_proxy_if_needed() {
  case "$1" in
    all|frontend|backend)
      info "Refreshing nginx upstream resolution..."
      "${COMPOSE[@]}" restart nginx >/dev/null
      ;;
  esac
}

normalize_target() {
  local target="${1:-all}"
  case "$target" in
    all|"") echo "all" ;;
    frontend|front|web|app) echo "frontend" ;;
    backend|api|server) echo "backend" ;;
    postgres|postgresql|db|database) echo "postgres" ;;
    nginx|proxy) echo "nginx" ;;
    *) fail "Unknown service '$target'. Run ./services.sh help for valid services." ;;
  esac
}

compose_services_for_start() {
  case "$1" in
    all) echo "" ;;
    frontend) echo "postgres backend frontend nginx" ;;
    backend) echo "postgres backend nginx" ;;
    postgres) echo "postgres" ;;
    nginx) echo "nginx" ;;
  esac
}

compose_services_exact() {
  case "$1" in
    all) echo "" ;;
    frontend) echo "frontend" ;;
    backend) echo "backend" ;;
    postgres) echo "postgres" ;;
    nginx) echo "nginx" ;;
  esac
}

build_services_for_target() {
  case "$1" in
    all) echo "" ;;
    frontend) echo "frontend" ;;
    backend) echo "backend" ;;
    postgres|nginx) echo "" ;;
  esac
}

check_ports() {
  local kill_ports="$1"
  local ports=(80 443)
  local found=0

  for port in "${ports[@]}"; do
    local pids
    pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    [ -n "$pids" ] || continue

    for pid in $pids; do
      local cmd
      cmd="$(ps -p "$pid" -o comm= 2>/dev/null || true)"
      if echo "$cmd" | grep -qiE '(Docker\.app|docker|com\.docker|docker-proxy|vpnkit|containerd)'; then
        continue
      fi

      found=1
      if [ "$kill_ports" = "1" ]; then
        warn "Killing process on port $port: $cmd (PID $pid)"
        kill -9 "$pid" 2>/dev/null || fail "Failed to kill PID $pid"
      else
        warn "Port $port is already used by $cmd (PID $pid). Use --kill-ports to stop it automatically."
      fi
    done
  done

  if [ "$found" = "1" ] && [ "$kill_ports" != "1" ]; then
    fail "Port conflicts detected."
  fi
}

parse_common_args() {
  TARGET="all"
  TARGET_SEEN=0
  FOREGROUND=0
  NO_CACHE=0
  KILL_PORTS=0
  ALLOW_DIRTY=0

  while [ "$#" -gt 0 ]; do
    case "$1" in
      -f|--foreground) FOREGROUND=1 ;;
      --no-cache) NO_CACHE=1 ;;
      --kill-ports) KILL_PORTS=1 ;;
      --allow-dirty) ALLOW_DIRTY=1 ;;
      -h|--help) usage; exit 0 ;;
      -*)
        fail "Unknown option '$1'"
        ;;
      *)
        if [ "$TARGET_SEEN" = "1" ]; then
          fail "Only one service target is supported."
        fi
        TARGET="$(normalize_target "$1")"
        TARGET_SEEN=1
        ;;
    esac
    shift
  done
}

run_compose_with_optional_services() {
  local service_string="$1"
  shift

  if [ -n "$service_string" ]; then
    # shellcheck disable=SC2086
    "${COMPOSE[@]}" "$@" $service_string
  else
    "${COMPOSE[@]}" "$@"
  fi
}

cmd_start() {
  parse_common_args "$@"
  check_docker
  ensure_env
  generate_certs
  check_ports "$KILL_PORTS"

  local services
  services="$(compose_services_for_start "$TARGET")"

  if [ "$FOREGROUND" = "1" ]; then
    info "Starting Servio ($TARGET) in foreground..."
    run_compose_with_optional_services "$services" up
  else
    info "Starting Servio ($TARGET)..."
    run_compose_with_optional_services "$services" up -d
    show_urls
  fi
}

cmd_stop() {
  parse_common_args "$@"
  check_docker

  local services
  services="$(compose_services_exact "$TARGET")"

  if [ "$TARGET" = "all" ]; then
    info "Stopping Servio..."
    "${COMPOSE[@]}" down
  else
    info "Stopping $TARGET..."
    run_compose_with_optional_services "$services" stop
  fi

  success "Stopped."
}

cmd_restart() {
  parse_common_args "$@"
  check_docker
  ensure_env
  generate_certs

  local services
  services="$(compose_services_exact "$TARGET")"

  info "Restarting Servio ($TARGET)..."
  if [ "$TARGET" = "all" ]; then
    "${COMPOSE[@]}" restart
  else
    run_compose_with_optional_services "$services" restart
  fi
  show_urls
}

cmd_rebuild() {
  parse_common_args "$@"
  check_docker
  ensure_env
  generate_certs

  local build_services
  build_services="$(build_services_for_target "$TARGET")"

  if [ "$TARGET" = "postgres" ] || [ "$TARGET" = "nginx" ]; then
    warn "$TARGET uses a base image/config and does not need a Docker build. Recreating service instead."
  else
    local build_args=(build)
    [ "$NO_CACHE" = "1" ] && build_args+=(--no-cache)

    info "Rebuilding Servio ($TARGET)..."
    run_compose_with_optional_services "$build_services" "${build_args[@]}"
  fi

  local start_services
  start_services="$(compose_services_for_start "$TARGET")"
  info "Recreating services..."
  run_compose_with_optional_services "$start_services" up -d
  refresh_proxy_if_needed "$TARGET"
  show_urls
}

cmd_status() {
  parse_common_args "$@"
  check_docker

  local services
  services="$(compose_services_exact "$TARGET")"
  run_compose_with_optional_services "$services" ps
}

cmd_logs() {
  parse_common_args "$@"
  check_docker

  local services
  services="$(compose_services_exact "$TARGET")"
  run_compose_with_optional_services "$services" logs -f --tail=200
}

cmd_update() {
  parse_common_args "$@"
  check_docker
  ensure_env

  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    if [ "$ALLOW_DIRTY" != "1" ] && [ -n "$(git status --porcelain)" ]; then
      fail "Local changes detected. Commit or stash them before update, or rerun with --allow-dirty."
    fi

    info "Fetching latest code from GitHub..."
    git fetch --all --prune
    info "Applying latest code with fast-forward only..."
    git pull --ff-only
  else
    warn "This directory is not a git repository. Skipping code update."
  fi

  local rebuild_args=("$TARGET")
  [ "$NO_CACHE" = "1" ] && rebuild_args+=(--no-cache)
  cmd_rebuild "${rebuild_args[@]}"
}

main() {
  local command="${1:-help}"
  shift || true

  case "$command" in
    start) cmd_start "$@" ;;
    stop) cmd_stop "$@" ;;
    restart) cmd_restart "$@" ;;
    rebuild|build) cmd_rebuild "$@" ;;
    status|ps) cmd_status "$@" ;;
    logs|log) cmd_logs "$@" ;;
    update) cmd_update "$@" ;;
    help|-h|--help) usage ;;
    *) fail "Unknown command '$command'. Run ./services.sh help." ;;
  esac
}

main "$@"
