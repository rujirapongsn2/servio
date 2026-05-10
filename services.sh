#!/usr/bin/env bash

# Servio service manager
# Usage examples:
#   ./services.sh install
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
  install               Guided first-time setup for Linux, then build and start
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
  --no-start            For install: write config and build, but do not start
  --force-env           For install: replace existing .env after making a backup

Examples:
  ./services.sh install
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
    fail ".env file not found. Run ./services.sh install first, or create .env manually with at least OPENAI_API_KEY."
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
  NO_START=0
  FORCE_ENV=0

  while [ "$#" -gt 0 ]; do
    case "$1" in
      -f|--foreground) FOREGROUND=1 ;;
      --no-cache) NO_CACHE=1 ;;
      --kill-ports) KILL_PORTS=1 ;;
      --allow-dirty) ALLOW_DIRTY=1 ;;
      --no-start) NO_START=1 ;;
      --force-env) FORCE_ENV=1 ;;
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

is_interactive() {
  [ -t 0 ] && [ -t 1 ]
}

random_hex() {
  local bytes="${1:-24}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$bytes"
  else
    tr -dc 'A-Za-z0-9' </dev/urandom | head -c $((bytes * 2))
    echo
  fi
}

prompt_value() {
  local label="$1"
  local default_value="${2:-}"
  local required="${3:-0}"
  local value=""

  if ! is_interactive; then
    echo "$default_value"
    return 0
  fi

  while true; do
    if [ -n "$default_value" ]; then
      read -r -p "$label [$default_value]: " value
      value="${value:-$default_value}"
    else
      read -r -p "$label: " value
    fi

    if [ "$required" != "1" ] || [ -n "$value" ]; then
      echo "$value"
      return 0
    fi
    warn "This value is required."
  done
}

prompt_secret_value() {
  local label="$1"
  local required="${2:-0}"
  local value=""

  if ! is_interactive; then
    echo ""
    return 0
  fi

  while true; do
    read -r -s -p "$label: " value
    echo >&2
    if [ "$required" != "1" ] || [ -n "$value" ]; then
      echo "$value"
      return 0
    fi
    warn "This value is required."
  done
}

write_env_file() {
  local tmp_file=".env.install.tmp"
  local openai_api_key="$1"
  local softnix_api_key="$2"
  local gemini_api_key="$3"
  local postgres_user="$4"
  local postgres_password="$5"
  local postgres_db="$6"
  local postgres_port="$7"
  local backend_port="$8"
  local frontend_port="$9"
  local public_api_url="${10}"
  local public_ws_endpoint="${11}"
  local allowed_origins="${12}"
  local jwt_secret="${13}"

  {
    printf 'OPENAI_API_KEY=%s\n' "$openai_api_key"
    printf 'SOFTNIX_API_KEY=%s\n' "$softnix_api_key"
    printf 'GEMINI_API_KEY=%s\n' "$gemini_api_key"
    printf '\n'
    printf 'POSTGRES_USER=%s\n' "$postgres_user"
    printf 'POSTGRES_PASSWORD=%s\n' "$postgres_password"
    printf 'POSTGRES_DB=%s\n' "$postgres_db"
    printf 'POSTGRES_PORT=%s\n' "$postgres_port"
    printf 'DATABASE_URL=postgresql://%s:%s@postgres:5432/%s\n' "$postgres_user" "$postgres_password" "$postgres_db"
    printf '\n'
    printf 'BACKEND_PORT=%s\n' "$backend_port"
    printf 'FRONTEND_PORT=%s\n' "$frontend_port"
    printf '\n'
    printf 'NEXT_PUBLIC_API_URL=%s\n' "$public_api_url"
    printf 'NEXT_PUBLIC_WEBSOCKET_ENDPOINT=%s\n' "$public_ws_endpoint"
    printf 'ALLOWED_ORIGINS=%s\n' "$allowed_origins"
    printf '\n'
    printf 'JWT_SECRET_KEY=%s\n' "$jwt_secret"
  } > "$tmp_file"

  chmod 600 "$tmp_file" 2>/dev/null || true
  mv "$tmp_file" ".env"
}

cmd_install() {
  parse_common_args "$@"
  TARGET="all"

  if [ "$(uname -s)" != "Linux" ]; then
    warn "This installer is designed for Linux. Continuing because Docker-based setup may still work on this OS."
  fi

  check_docker

  if [ -f ".env" ] && [ "$FORCE_ENV" != "1" ]; then
    if is_interactive; then
      local answer
      read -r -p ".env already exists. Reconfigure it now? [y/N]: " answer
      case "$answer" in
        y|Y|yes|YES) ;;
        *)
          info "Keeping existing .env"
          generate_certs
          check_ports "$KILL_PORTS"
          info "Building images..."
          "${COMPOSE[@]}" build
          if [ "$NO_START" = "1" ]; then
            success "Install completed. Start later with: ./services.sh start"
            return 0
          fi
          info "Starting Servio..."
          "${COMPOSE[@]}" up -d
          refresh_proxy_if_needed "all"
          show_urls
          return 0
          ;;
      esac
    else
      info "Keeping existing .env in non-interactive mode."
      generate_certs
      check_ports "$KILL_PORTS"
      "${COMPOSE[@]}" build
      [ "$NO_START" = "1" ] || "${COMPOSE[@]}" up -d
      [ "$NO_START" = "1" ] || show_urls
      return 0
    fi
  fi

  if [ -f ".env" ]; then
    local backup=".env.backup.$(date +%Y%m%d%H%M%S)"
    cp .env "$backup"
    chmod 600 "$backup" 2>/dev/null || true
    warn "Existing .env backed up to $backup"
  fi

  info "Configuring Servio environment..."
  local default_public_url="https://localhost"
  local default_ws_endpoint="wss://localhost/ws"
  local default_allowed_origins="https://localhost,http://localhost"
  local postgres_user postgres_password postgres_db postgres_port backend_port frontend_port
  local public_api_url public_ws_endpoint allowed_origins jwt_secret
  local openai_api_key softnix_api_key gemini_api_key

  openai_api_key="$(prompt_secret_value "OpenAI API key (leave blank to configure later)" 0)"
  softnix_api_key="$(prompt_secret_value "Softnix API key (optional, leave blank to skip)" 0)"
  gemini_api_key="$(prompt_secret_value "Gemini API key (optional, leave blank to skip)" 0)"

  postgres_user="$(prompt_value "PostgreSQL user" "postgres" 1)"
  postgres_password="$(prompt_value "PostgreSQL password" "$(random_hex 18)" 1)"
  postgres_db="$(prompt_value "PostgreSQL database" "voice_agents" 1)"
  postgres_port="$(prompt_value "PostgreSQL port" "5432" 1)"
  backend_port="$(prompt_value "Backend internal port" "8000" 1)"
  frontend_port="$(prompt_value "Frontend internal port" "3000" 1)"
  public_api_url="$(prompt_value "Public API URL" "$default_public_url" 1)"
  public_ws_endpoint="$(prompt_value "Public WebSocket endpoint" "$default_ws_endpoint" 1)"
  allowed_origins="$(prompt_value "Allowed CORS origins" "$default_allowed_origins" 1)"
  jwt_secret="$(prompt_value "JWT secret" "$(random_hex 32)" 1)"

  write_env_file \
    "$openai_api_key" \
    "$softnix_api_key" \
    "$gemini_api_key" \
    "$postgres_user" \
    "$postgres_password" \
    "$postgres_db" \
    "$postgres_port" \
    "$backend_port" \
    "$frontend_port" \
    "$public_api_url" \
    "$public_ws_endpoint" \
    "$allowed_origins" \
    "$jwt_secret"

  mkdir -p server/data nginx/certs
  chmod 700 server/data 2>/dev/null || true
  generate_certs
  check_ports "$KILL_PORTS"

  info "Building Servio images..."
  "${COMPOSE[@]}" build

  if [ "$NO_START" = "1" ]; then
    success "Install completed. Start later with: ./services.sh start"
    return 0
  fi

  info "Starting Servio..."
  "${COMPOSE[@]}" up -d
  refresh_proxy_if_needed "all"
  show_urls
  success "Install completed."
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
    install) cmd_install "$@" ;;
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
