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

DOCKER=(docker)
COMPOSE=(docker compose)

run_compose() {
  if [ -f ".env" ]; then
    "${COMPOSE[@]}" --env-file .env "$@"
  else
    "${COMPOSE[@]}" "$@"
  fi
}

usage() {
  cat <<'EOF'
Servio service manager

Usage:
  ./services.sh <command> [service] [options]

Commands:
  install               Install dependencies, configure, build, and start
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
  --kill-ports          Kill non-Docker processes using configured nginx ports before start
  --allow-dirty         For update: allow git pull with local changes
  --no-start            For install: write config and build, but do not start
  --force-env           For install: replace existing .env after making a backup
  --skip-api-check      For install: skip provider API key connectivity checks

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

run_as_root() {
  if [ "$(id -u)" = "0" ]; then
    "$@"
  elif command -v sudo >/dev/null 2>&1; then
    sudo "$@"
  else
    fail "This installer needs root privileges to install dependencies. Install sudo or run this command as root."
  fi
}

apt_has_package() {
  apt-cache show "$1" >/dev/null 2>&1
}

install_apt_packages() {
  local packages=("$@")
  [ "${#packages[@]}" -gt 0 ] || return 0

  info "Installing missing packages: ${packages[*]}"
  run_as_root apt-get update
  run_as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y "${packages[@]}"
}

ensure_basic_dependencies() {
  local packages=()

  command -v curl >/dev/null 2>&1 || packages+=(curl)
  command -v openssl >/dev/null 2>&1 || packages+=(openssl)
  command -v lsof >/dev/null 2>&1 || packages+=(lsof)
  command -v git >/dev/null 2>&1 || packages+=(git)

  if command -v apt-get >/dev/null 2>&1; then
    command -v update-ca-certificates >/dev/null 2>&1 || packages+=(ca-certificates)
    install_apt_packages "${packages[@]}"
  elif [ "${#packages[@]}" -gt 0 ]; then
    fail "Missing required commands: ${packages[*]}. Automatic dependency installation currently supports apt-based Linux only."
  fi
}

ensure_docker_service_running() {
  if command -v systemctl >/dev/null 2>&1; then
    run_as_root systemctl enable --now docker >/dev/null 2>&1 || true
  elif command -v service >/dev/null 2>&1; then
    run_as_root service docker start >/dev/null 2>&1 || true
  fi
}

ensure_docker_dependency() {
  local packages=()

  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    ensure_docker_service_running
    return 0
  fi

  if ! command -v apt-get >/dev/null 2>&1; then
    fail "Docker or Docker Compose is missing. Automatic Docker installation currently supports apt-based Linux only."
  fi

  command -v docker >/dev/null 2>&1 || packages+=(docker.io)

  if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
    if apt_has_package docker-compose-v2; then
      packages+=(docker-compose-v2)
    elif apt_has_package docker-compose-plugin; then
      packages+=(docker-compose-plugin)
    else
      packages+=(docker-compose)
    fi
  fi

  install_apt_packages "${packages[@]}"
  ensure_docker_service_running

  command -v docker >/dev/null 2>&1 || fail "Docker installation did not provide the docker command."
}

configure_docker_command() {
  DOCKER=(docker)
  COMPOSE=(docker compose)

  if "${DOCKER[@]}" ps >/dev/null 2>&1; then
    if "${COMPOSE[@]}" version >/dev/null 2>&1; then
      return 0
    fi
    if command -v docker-compose >/dev/null 2>&1 && docker-compose version >/dev/null 2>&1; then
      COMPOSE=(docker-compose)
      return 0
    fi
  fi

  if command -v sudo >/dev/null 2>&1; then
    if sudo docker ps >/dev/null 2>&1; then
      DOCKER=(sudo docker)
      if sudo docker compose version >/dev/null 2>&1; then
        COMPOSE=(sudo docker compose)
        warn "Using sudo for Docker commands. To avoid sudo later, add your user to the docker group and log in again."
        return 0
      fi
      if command -v docker-compose >/dev/null 2>&1 && sudo docker-compose version >/dev/null 2>&1; then
        COMPOSE=(sudo docker-compose)
        warn "Using sudo for Docker commands. To avoid sudo later, add your user to the docker group and log in again."
        return 0
      fi
    fi
  fi

  return 1
}

ensure_install_dependencies() {
  if [ "$(uname -s)" != "Linux" ]; then
    warn "Automatic dependency installation is only supported on Linux."
    return 0
  fi

  ensure_basic_dependencies
  ensure_docker_dependency
}

check_docker() {
  command -v docker >/dev/null 2>&1 || fail "Docker is not installed. Run ./services.sh install to install dependencies, or install Docker manually."
  configure_docker_command || fail "Docker daemon is not running, Docker socket is not accessible, or Docker Compose is not available."
}

ensure_env() {
  if [ ! -f ".env" ]; then
    fail ".env file not found. Run ./services.sh install first, or create .env manually with at least OPENAI_API_KEY."
  fi

  if ! grep -E '^OPENAI_API_KEY=.+$' .env >/dev/null 2>&1; then
    fail "OPENAI_API_KEY is not set in .env. Run ./services.sh install --force-env to configure and validate it."
  fi
}

generate_certs() {
  local cert_dir="nginx/certs"
  local cert_file="$cert_dir/server.crt"
  local key_file="$cert_dir/server.key"
  local nginx_conf="nginx/nginx.conf"

  mkdir -p "$cert_dir"

  if [ ! -f "$cert_file" ] || [ ! -f "$key_file" ]; then
    command -v openssl >/dev/null 2>&1 || fail "openssl is required to generate local HTTPS certificates."

    info "Generating local HTTPS certificates..."
    openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
      -keyout "$key_file" \
      -out "$cert_file" \
      -subj "/C=TH/ST=Bangkok/L=Bangkok/O=Servio/CN=localhost" >/dev/null 2>&1
    success "Generated certificates in $cert_dir"
  fi

  chmod 755 "$cert_dir" 2>/dev/null || true
  chmod 644 "$cert_file" "$key_file" 2>/dev/null || true
  chmod 644 "$nginx_conf" 2>/dev/null || true
}

ensure_data_permissions() {
  local data_dir="server/data"
  local backend_uid="1001"
  local host_gid

  host_gid="$(stat -c '%g' "$ROOT_DIR" 2>/dev/null || id -g)"
  mkdir -p "$data_dir" "$data_dir/okf_bundles"

  if command -v chown >/dev/null 2>&1; then
    run_as_root chown -R "$backend_uid:$host_gid" "$data_dir" 2>/dev/null ||       warn "Could not chown $data_dir. OKF/local knowledge uploads may fail if the backend cannot write there."
  fi

  run_as_root chmod -R u+rwX,g+rwX,o-rwx "$data_dir" 2>/dev/null ||     chmod -R u+rwX,g+rwX,o-rwx "$data_dir" 2>/dev/null || true

  if command -v find >/dev/null 2>&1; then
    run_as_root find "$data_dir" -type d -exec chmod g+s {} + 2>/dev/null || true
  fi
}

read_env_value() {
  local key="$1"
  local default_value="${2:-}"

  if [ ! -f ".env" ]; then
    echo "$default_value"
    return 0
  fi

  local value
  value="$(grep -E "^${key}=" .env | head -n 1 | cut -d= -f2- || true)"
  echo "${value:-$default_value}"
}

show_urls() {
  local public_api_url websocket_endpoint admin_url nginx_http_port nginx_https_port http_origin https_local
  public_api_url="$(read_env_value "NEXT_PUBLIC_API_URL" "https://localhost")"
  websocket_endpoint="$(read_env_value "NEXT_PUBLIC_WEBSOCKET_ENDPOINT" "wss://localhost/ws")"
  nginx_http_port="$(read_env_value "NGINX_HTTP_PORT" "80")"
  nginx_https_port="$(read_env_value "NGINX_HTTPS_PORT" "443")"
  admin_url="${public_api_url%/}/admin"

  if [ "$nginx_http_port" = "80" ]; then
    http_origin="http://localhost"
  else
    http_origin="http://localhost:${nginx_http_port}"
  fi

  if [ "$nginx_https_port" = "443" ]; then
    https_local="https://localhost"
  else
    https_local="https://localhost:${nginx_https_port}"
  fi

  cat <<EOF

Servio is available at:
  Frontend:    ${public_api_url}
  Backend API: ${public_api_url%/}/api
  WebSocket:   ${websocket_endpoint}
  Admin:       ${admin_url}

Cloudflare Tunnel origin:
  HTTP origin: ${http_origin}

Local direct access:
  HTTP:        ${http_origin}
  HTTPS:       ${https_local}

EOF
}

refresh_proxy_if_needed() {
  case "$1" in
    all|frontend|backend)
      info "Refreshing nginx upstream resolution..."
      run_compose restart nginx >/dev/null
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
  local nginx_http_port nginx_https_port
  local ports=()
  local found=0

  nginx_http_port="${NGINX_HTTP_PORT:-$(read_env_value "NGINX_HTTP_PORT" "80")}"
  nginx_https_port="${NGINX_HTTPS_PORT:-$(read_env_value "NGINX_HTTPS_PORT" "443")}"
  [ -n "$nginx_http_port" ] && ports+=("$nginx_http_port")
  [ -n "$nginx_https_port" ] && [ "$nginx_https_port" != "$nginx_http_port" ] && ports+=("$nginx_https_port")

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
  SKIP_API_CHECK=0

  while [ "$#" -gt 0 ]; do
    case "$1" in
      -f|--foreground) FOREGROUND=1 ;;
      --no-cache) NO_CACHE=1 ;;
      --kill-ports) KILL_PORTS=1 ;;
      --allow-dirty) ALLOW_DIRTY=1 ;;
      --no-start) NO_START=1 ;;
      --force-env) FORCE_ENV=1 ;;
      --skip-api-check) SKIP_API_CHECK=1 ;;
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
    run_compose "$@" $service_string
  else
    run_compose "$@"
  fi
}

can_prompt() {
  { [ -t 0 ] && [ -t 1 ]; } || { [ -r /dev/tty ] && [ -w /dev/tty ]; }
}

is_interactive() {
  can_prompt
}

prompt_read() {
  local prompt="$1"
  local silent="${2:-0}"
  local value=""

  if [ -r /dev/tty ] && [ -w /dev/tty ]; then
    printf '%s' "$prompt" >/dev/tty
    if [ "$silent" = "1" ]; then
      stty -echo </dev/tty 2>/dev/null || true
      IFS= read -r value </dev/tty || true
      stty echo </dev/tty 2>/dev/null || true
      printf '\n' >/dev/tty
    else
      IFS= read -r value </dev/tty || true
    fi
  else
    if [ "$silent" = "1" ]; then
      read -r -s -p "$prompt" value
      echo >&2
    else
      read -r -p "$prompt" value
    fi
  fi

  echo "$value"
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
      value="$(prompt_read "$label [$default_value]: " 0)"
      value="${value:-$default_value}"
    else
      value="$(prompt_read "$label: " 0)"
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
    value="$(prompt_read "$label: " 1)"
    if [ "$required" != "1" ] || [ -n "$value" ]; then
      echo "$value"
      return 0
    fi
    warn "This value is required."
  done
}

validate_api_key() {
  local provider="$1"
  local api_key="$2"
  local body_file status curl_exit

  if [ "${SKIP_API_CHECK:-0}" = "1" ]; then
    warn "Skipping ${provider} API key check because --skip-api-check was set." >&2
    return 0
  fi

  command -v curl >/dev/null 2>&1 || fail "curl is required to validate API keys. Install curl or rerun install with --skip-api-check."

  body_file="$(mktemp)"
  status="000"
  curl_exit=0

  case "$provider" in
    openai)
      info "Validating OpenAI API key..." >&2
      status="$(curl -sS -o "$body_file" -w "%{http_code}" \
        --connect-timeout 10 --max-time 30 \
        -H "Authorization: Bearer ${api_key}" \
        https://api.openai.com/v1/models)" || curl_exit=$?
      ;;
    gemini)
      info "Validating Gemini API key..." >&2
      status="$(curl -sS -o "$body_file" -w "%{http_code}" \
        --connect-timeout 10 --max-time 30 \
        "https://generativelanguage.googleapis.com/v1beta/models?key=${api_key}")" || curl_exit=$?
      ;;
    softnix)
      info "Validating Softnix API key..." >&2
      status="$(curl -sS -o "$body_file" -w "%{http_code}" \
        --connect-timeout 10 --max-time 75 \
        -X POST \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${api_key}" \
        -d '{"query":"ping","files":[],"inputs":{},"citation":false,"response_mode":"blocking"}' \
        https://genai.softnix.ai/external/api/chat-messages)" || curl_exit=$?
      ;;
    *)
      rm -f "$body_file"
      fail "Unknown API provider '$provider'."
      ;;
  esac

  if [ "$curl_exit" != "0" ]; then
    rm -f "$body_file"
    warn "Could not connect to ${provider} API (curl exit ${curl_exit})." >&2
    return 1
  fi

  if [ "$status" = "200" ]; then
    rm -f "$body_file"
    success "${provider} API key validated." >&2
    return 0
  fi

  rm -f "$body_file"
  warn "${provider} API key check failed (HTTP ${status})." >&2
  return 1
}

prompt_api_key() {
  local provider="$1"
  local label="$2"
  local required="${3:-0}"
  local existing_value="${4:-}"
  local value=""

  if ! is_interactive; then
    value="$existing_value"
    if [ "$required" = "1" ] && [ -z "$value" ]; then
      fail "$label is required in non-interactive install. Set it in .env first or run install interactively."
    fi
    if [ -n "$value" ]; then
      validate_api_key "$provider" "$value" || fail "$label validation failed."
    fi
    echo "$value"
    return 0
  fi

  while true; do
    if [ -n "$existing_value" ]; then
      value="$(prompt_read "$label (press Enter to keep existing): " 1)"
      value="${value:-$existing_value}"
    else
      value="$(prompt_read "$label: " 1)"
    fi

    if [ -z "$value" ]; then
      if [ "$required" = "1" ]; then
        warn "This API key is required." >&2
        continue
      fi
      echo ""
      return 0
    fi

    if validate_api_key "$provider" "$value"; then
      echo "$value"
      return 0
    fi

    warn "Please enter a working $label, or press Ctrl+C to stop." >&2
  done
}

validate_configured_api_keys() {
  local openai_api_key softnix_api_key gemini_api_key

  openai_api_key="$(read_env_value "OPENAI_API_KEY" "")"
  softnix_api_key="$(read_env_value "SOFTNIX_API_KEY" "")"
  gemini_api_key="$(read_env_value "GEMINI_API_KEY" "")"

  [ -n "$openai_api_key" ] || fail "OPENAI_API_KEY is required. Run ./services.sh install --force-env to configure it."
  validate_api_key "openai" "$openai_api_key" || fail "OPENAI_API_KEY validation failed."

  if [ -n "$softnix_api_key" ]; then
    validate_api_key "softnix" "$softnix_api_key" || fail "SOFTNIX_API_KEY validation failed."
  fi

  if [ -n "$gemini_api_key" ]; then
    validate_api_key "gemini" "$gemini_api_key" || fail "GEMINI_API_KEY validation failed."
  fi
}

derive_public_endpoints() {
  local raw_input="$1"
  local normalized origin scheme host_port

  normalized="$(printf '%s' "$raw_input" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
  [ -n "$normalized" ] || normalized="localhost"

  if [[ "$normalized" != http://* && "$normalized" != https://* ]]; then
    normalized="https://$normalized"
  fi

  origin="$(printf '%s' "$normalized" | sed -E 's#^(https?://[^/]+).*$#\1#')"
  scheme="${origin%%:*}"
  host_port="${origin#*://}"

  DERIVED_PUBLIC_API_URL="$origin"
  if [ "$scheme" = "https" ]; then
    DERIVED_PUBLIC_WS_ENDPOINT="wss://${host_port}/ws"
  else
    DERIVED_PUBLIC_WS_ENDPOINT="ws://${host_port}/ws"
  fi

  case "$host_port" in
    localhost)
      DERIVED_ALLOWED_ORIGINS="https://localhost,http://localhost"
      ;;
    127.0.0.1)
      DERIVED_ALLOWED_ORIGINS="https://127.0.0.1,http://127.0.0.1"
      ;;
    *)
      DERIVED_ALLOWED_ORIGINS="$origin"
      ;;
  esac
}

wait_for_backend_exec() {
  local attempts="${1:-60}"
  local attempt

  for attempt in $(seq 1 "$attempts"); do
    if run_compose exec -T backend python -c "from app.db_config import get_db; print('ready')" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
  done

  return 1
}

ensure_default_admin_login() {
  info "Ensuring built-in admin account is ready..."

  if ! wait_for_backend_exec 60; then
    warn "Backend did not become ready in time. Skipping admin credential reset."
    return 1
  fi

  local python_cmd
  python_cmd="$(cat <<'PY'
import bcrypt
from app.db_config import get_db
from app.orm_models import Admin

password_hash = bcrypt.hashpw("admin123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

with get_db() as db:
    admin = db.query(Admin).filter_by(username="admin").first()
    if admin is None:
        db.add(Admin(username="admin", password_hash=password_hash, is_super_admin=True))
    else:
        admin.password_hash = password_hash
        admin.is_super_admin = True

print("admin-ready")
PY
)"

  run_compose exec -T backend python -c "$python_cmd" >/dev/null
  success "Built-in admin credentials are set to username: admin / password: admin123"
}

wait_for_compose_health() {
  local service="$1"
  local attempts="${2:-90}"
  local attempt id status

  info "Waiting for ${service} to become healthy..."
  for attempt in $(seq 1 "$attempts"); do
    id="$(run_compose ps -q "$service" 2>/dev/null || true)"
    if [ -n "$id" ]; then
      status="$(${DOCKER[@]} inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$id" 2>/dev/null || true)"
      case "$status" in
        healthy|running)
          success "${service} is ${status}."
          return 0
          ;;
        unhealthy|exited|dead)
          run_compose logs --tail=80 "$service" >&2 || true
          fail "${service} became ${status}. Check logs above."
          ;;
      esac
    fi
    sleep 2
  done

  run_compose logs --tail=80 "$service" >&2 || true
  fail "Timed out waiting for ${service} to become healthy."
}

wait_for_http_health() {
  local url="$1"
  local attempts="${2:-60}"
  local attempt

  command -v curl >/dev/null 2>&1 || fail "curl is required to verify local HTTP health."

  info "Checking local HTTP health at ${url}..."
  for attempt in $(seq 1 "$attempts"); do
    if curl -fsS --connect-timeout 3 --max-time 10 "$url" >/dev/null 2>&1; then
      success "Local HTTP health check passed."
      return 0
    fi
    sleep 2
  done

  fail "Local HTTP health check failed at ${url}."
}

verify_stack() {
  local nginx_http_port
  nginx_http_port="$(read_env_value "NGINX_HTTP_PORT" "80")"

  wait_for_compose_health postgres 60
  wait_for_compose_health backend 90
  wait_for_compose_health frontend 90
  wait_for_http_health "http://localhost:${nginx_http_port}/api/health" 60
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
  local nginx_http_port="${10}"
  local nginx_https_port="${11}"
  local public_api_url="${12}"
  local public_ws_endpoint="${13}"
  local allowed_origins="${14}"
  local jwt_secret="${15}"

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
    printf 'NGINX_HTTP_PORT=%s\n' "$nginx_http_port"
    printf 'NGINX_HTTPS_PORT=%s\n' "$nginx_https_port"
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

  ensure_install_dependencies
  check_docker

  if [ -f ".env" ] && [ "$FORCE_ENV" != "1" ]; then
    if is_interactive; then
      local answer
      answer="$(prompt_read ".env already exists. Reconfigure it now? [y/N]: " 0)"
      case "$answer" in
        y|Y|yes|YES) ;;
        *)
          info "Keeping existing .env"
          validate_configured_api_keys
          generate_certs
          check_ports "$KILL_PORTS"
          info "Building images..."
          run_compose build
          if [ "$NO_START" = "1" ]; then
            success "Install completed. Start later with: ./services.sh start"
            return 0
          fi
          info "Starting Servio..."
          run_compose up -d
          refresh_proxy_if_needed "all"
          verify_stack
          ensure_default_admin_login
          show_urls
          return 0
          ;;
      esac
    else
      info "Keeping existing .env in non-interactive mode."
      validate_configured_api_keys
      generate_certs
      check_ports "$KILL_PORTS"
      run_compose build
      [ "$NO_START" = "1" ] || run_compose up -d
      [ "$NO_START" = "1" ] || refresh_proxy_if_needed "all"
      [ "$NO_START" = "1" ] || verify_stack
      [ "$NO_START" = "1" ] || ensure_default_admin_login
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
  local public_access_entry derived_public_api_url derived_public_ws_endpoint derived_allowed_origins
  local postgres_user postgres_password postgres_db postgres_port backend_port frontend_port nginx_http_port nginx_https_port
  local public_api_url public_ws_endpoint allowed_origins jwt_secret
  local openai_api_key softnix_api_key gemini_api_key
  local existing_openai_api_key existing_softnix_api_key existing_gemini_api_key

  existing_openai_api_key="${OPENAI_API_KEY:-$(read_env_value "OPENAI_API_KEY" "")}"
  existing_softnix_api_key="${SOFTNIX_API_KEY:-$(read_env_value "SOFTNIX_API_KEY" "")}"
  existing_gemini_api_key="${GEMINI_API_KEY:-$(read_env_value "GEMINI_API_KEY" "")}"

  openai_api_key="$(prompt_api_key "openai" "OpenAI API key" 1 "$existing_openai_api_key")"
  softnix_api_key="$(prompt_api_key "softnix" "Softnix API key (optional)" 0 "$existing_softnix_api_key")"
  gemini_api_key="$(prompt_api_key "gemini" "Gemini API key (optional)" 0 "$existing_gemini_api_key")"

  postgres_user="$(prompt_value "PostgreSQL user" "postgres" 1)"
  postgres_password="$(prompt_value "PostgreSQL password" "$(random_hex 18)" 1)"
  postgres_db="$(prompt_value "PostgreSQL database" "voice_agents" 1)"
  postgres_port="$(prompt_value "PostgreSQL port" "5432" 1)"
  backend_port="$(prompt_value "Backend internal port" "$(read_env_value "BACKEND_PORT" "8000")" 1)"
  frontend_port="$(prompt_value "Frontend internal port" "$(read_env_value "FRONTEND_PORT" "3000")" 1)"
  nginx_http_port="$(prompt_value "Local HTTP port for Cloudflare Tunnel origin" "$(read_env_value "NGINX_HTTP_PORT" "8080")" 1)"
  nginx_https_port="$(prompt_value "Local HTTPS port for direct local access" "$(read_env_value "NGINX_HTTPS_PORT" "8443")" 1)"
  public_access_entry="$(prompt_value "Public hostname, IP, or base URL for browser access" "$(read_env_value "NEXT_PUBLIC_API_URL" "https://servio.softnix.ai")" 1)"
  derive_public_endpoints "$public_access_entry"
  derived_public_api_url="$DERIVED_PUBLIC_API_URL"
  derived_public_ws_endpoint="$DERIVED_PUBLIC_WS_ENDPOINT"
  derived_allowed_origins="$DERIVED_ALLOWED_ORIGINS"
  public_api_url="$(prompt_value "Public API URL" "$derived_public_api_url" 1)"
  public_ws_endpoint="$(prompt_value "Public WebSocket endpoint" "$derived_public_ws_endpoint" 1)"
  allowed_origins="$(prompt_value "Allowed CORS origins" "$derived_allowed_origins" 1)"
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
    "$nginx_http_port" \
    "$nginx_https_port" \
    "$public_api_url" \
    "$public_ws_endpoint" \
    "$allowed_origins" \
    "$jwt_secret"

  ensure_data_permissions
  mkdir -p nginx/certs
  generate_certs
  check_ports "$KILL_PORTS"

  info "Building Servio images..."
  run_compose build

  if [ "$NO_START" = "1" ]; then
    success "Install completed. Start later with: ./services.sh start"
    return 0
  fi

  info "Starting Servio..."
  run_compose up -d
  refresh_proxy_if_needed "all"
  verify_stack
  ensure_default_admin_login
  show_urls
  success "Install completed."
}

cmd_start() {
  parse_common_args "$@"
  check_docker
  ensure_env
  generate_certs
  ensure_data_permissions
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
    run_compose down
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
  ensure_data_permissions

  local services
  services="$(compose_services_exact "$TARGET")"

  info "Restarting Servio ($TARGET)..."
  if [ "$TARGET" = "all" ]; then
    run_compose restart
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
  ensure_data_permissions

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
