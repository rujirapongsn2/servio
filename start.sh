#!/bin/bash

# Voice Agents SDK - Docker Management Script
# Manage Docker containers for Voice Agents application

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Print banner
clear
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Voice Agents SDK - Docker Manager                   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}📚 Quick Start Guide:${NC}"
echo -e "${YELLOW}   First time?${NC}        → Choose 5 (Build) then 2 (Start)"
echo -e "${YELLOW}   Changed code?${NC}      → Choose 5 (Build) then 4 (Restart)"
echo -e "${YELLOW}   Changed .env?${NC}      → Choose 4 (Restart)"
echo -e "${YELLOW}   Need to debug?${NC}     → Choose 6 (View logs)"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}ERROR: Docker is not installed!${NC}"
    echo -e "${YELLOW}Please install Docker: https://docs.docker.com/get-docker/${NC}"
    exit 1
fi

# Check if Docker daemon is running
if ! docker info &> /dev/null; then
    echo -e "${RED}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ERROR: Docker daemon is not running!                           ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}Docker Desktop is not running. Please start it first.${NC}"
    echo ""
    echo -e "${CYAN}How to start Docker Desktop:${NC}"
    echo -e "  ${BLUE}1.${NC} Open Docker Desktop from Applications"
    echo -e "  ${BLUE}2.${NC} Wait for Docker icon in menu bar to turn white"
    echo -e "  ${BLUE}3.${NC} Run this script again: ${YELLOW}./start.sh${NC}"
    echo ""

    # Try to start Docker Desktop automatically on macOS
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo -e "${CYAN}Would you like to try starting Docker Desktop automatically?${NC}"
        echo -n "Start Docker Desktop? (y/n): "
        read -r start_docker
        if [ "$start_docker" = "y" ] || [ "$start_docker" = "Y" ]; then
            echo ""
            echo -e "${BLUE}Opening Docker Desktop...${NC}"
            open -a Docker
            echo ""
            echo -e "${YELLOW}Waiting for Docker to start (this may take 30-60 seconds)...${NC}"

            # Wait for Docker daemon to be ready (max 2 minutes)
            local max_wait=120
            local elapsed=0
            while [ $elapsed -lt $max_wait ]; do
                if docker info &> /dev/null; then
                    echo ""
                    echo -e "${GREEN}✓ Docker is now running!${NC}"
                    echo ""
                    sleep 2
                    break
                fi
                sleep 2
                elapsed=$((elapsed + 2))
                echo -n "."
            done

            if [ $elapsed -ge $max_wait ]; then
                echo ""
                echo -e "${RED}✗ Docker failed to start within 2 minutes${NC}"
                echo -e "${YELLOW}Please start Docker Desktop manually and try again${NC}"
                exit 1
            fi
        else
            echo ""
            echo -e "${YELLOW}Please start Docker Desktop manually and run this script again${NC}"
            exit 1
        fi
    else
        exit 1
    fi
fi

# Check if docker-compose is available
if ! docker compose version &> /dev/null; then
    echo -e "${RED}ERROR: docker-compose is not available!${NC}"
    echo -e "${YELLOW}Please install Docker Compose${NC}"
    exit 1
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${RED}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ERROR: .env file not found!                                     ║${NC}"
    echo -e "${RED}╚══════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}The application requires environment variables for API keys.${NC}"
    echo ""

    # Check if .env.example exists
    if [ -f ".env.example" ]; then
        echo -e "${CYAN}Would you like to create .env file from template?${NC}"
        echo ""
        echo -e "  ${GREEN}1)${NC} Yes - Create .env from .env.example (Recommended)"
        echo -e "  ${GREEN}2)${NC} No - I'll create it manually"
        echo ""
        echo -n "Enter choice [1-2]: "
        read -r env_choice
        echo ""

        if [ "$env_choice" = "1" ]; then
            cp .env.example .env
            echo -e "${GREEN}✓ Created .env file from template${NC}"
            echo ""
            echo -e "${YELLOW}⚠️  IMPORTANT: You must edit .env and add your API keys!${NC}"
            echo ""
            echo -e "${CYAN}Required API keys:${NC}"
            echo -e "  ${BLUE}→${NC} OPENAI_API_KEY     (Required - Get from: https://platform.openai.com/api-keys)"
            echo -e "  ${BLUE}→${NC} SOFTNIX_API_KEY    (Optional - For Softnix integration)"
            echo -e "  ${BLUE}→${NC} GEMINI_API_KEY     (Optional - For File Store Agents)"
            echo ""
            echo -e "${CYAN}Quick setup:${NC}"
            echo -e "  ${BLUE}1.${NC} Open .env file:        ${YELLOW}nano .env${NC}  or  ${YELLOW}vim .env${NC}"
            echo -e "  ${BLUE}2.${NC} Replace 'your_xxx' with your actual API keys"
            echo -e "  ${BLUE}3.${NC} Save and close the file"
            echo -e "  ${BLUE}4.${NC} Run this script again:  ${YELLOW}./start.sh${NC}"
            echo ""
            echo -e "${YELLOW}Press Enter to open .env file in default editor...${NC}"
            read -r
            ${EDITOR:-nano} .env
            echo ""
            echo -e "${GREEN}Please run ./start.sh again after saving your API keys${NC}"
            exit 0
        fi
    fi

    # Manual instructions
    echo -e "${CYAN}To set up manually:${NC}"
    echo ""
    echo -e "${BLUE}Step 1:${NC} Copy the template file"
    echo -e "  ${YELLOW}cp .env.example .env${NC}"
    echo ""
    echo -e "${BLUE}Step 2:${NC} Edit .env file and add your API keys"
    echo -e "  ${YELLOW}nano .env${NC}  or  ${YELLOW}vim .env${NC}"
    echo ""
    echo -e "${BLUE}Step 3:${NC} Add at minimum:"
    echo ""
    echo -e "  ${GREEN}OPENAI_API_KEY${NC}=your_openai_api_key_here"
    echo ""
    echo -e "  Get your key from: ${CYAN}https://platform.openai.com/api-keys${NC}"
    echo ""
    echo -e "${BLUE}Step 4:${NC} Save the file and run this script again"
    echo -e "  ${YELLOW}./start.sh${NC}"
    echo ""
    echo -e "${CYAN}Optional API keys (can be added later):${NC}"
    echo -e "  • SOFTNIX_API_KEY  - For Softnix GenAI integration"
    echo -e "  • GEMINI_API_KEY   - For Google Gemini File Search"
    echo ""
    exit 1
fi

# Validate that required API keys are set
if ! grep -q "OPENAI_API_KEY=sk-" .env 2>/dev/null && ! grep -q "OPENAI_API_KEY=your_" .env 2>/dev/null; then
    if ! grep -E "^OPENAI_API_KEY=.+$" .env | grep -qv "your_openai_api_key" 2>/dev/null; then
        echo -e "${YELLOW}⚠️  WARNING: OPENAI_API_KEY might not be set correctly in .env${NC}"
        echo -e "${YELLOW}   Please make sure to replace 'your_openai_api_key_here' with your actual key${NC}"
        echo ""
        echo -n "Continue anyway? (y/n): "
        read -r continue_choice
        if [ "$continue_choice" != "y" ] && [ "$continue_choice" != "Y" ]; then
            echo -e "${YELLOW}Exiting. Please update your .env file first.${NC}"
            exit 1
        fi
        echo ""
    fi
fi

# Function to show menu
show_menu() {
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║                    Docker Service Manager                        ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${YELLOW}Choose an action:${NC}"
    echo ""
    echo -e "  ${GREEN}1)${NC} Start services (foreground)"
    echo -e "     ${BLUE}→${NC} See logs in real-time, Ctrl+C to stop"
    echo -e "     ${BLUE}→${NC} Use when: First time running or debugging"
    echo ""
    echo -e "  ${GREEN}2)${NC} Start services (background)"
    echo -e "     ${BLUE}→${NC} Run in background, use option 6 to view logs"
    echo -e "     ${BLUE}→${NC} Use when: Normal daily usage"
    echo ""
    echo -e "  ${GREEN}3)${NC} Stop services"
    echo -e "     ${BLUE}→${NC} Stop all containers (data is preserved)"
    echo -e "     ${BLUE}→${NC} Use when: Done working, shutting down"
    echo ""
    echo -e "  ${GREEN}4)${NC} Restart services"
    echo -e "     ${BLUE}→${NC} Restart both frontend and backend"
    echo -e "     ${BLUE}→${NC} Use when: Changed .env file or config (no code changes)"
    echo ""
    echo -e "  ${GREEN}5)${NC} Build/Rebuild images ⚠️  REQUIRED after code changes"
    echo -e "     ${BLUE}→${NC} Rebuild Docker images with latest code"
    echo -e "     ${BLUE}→${NC} Use when: Fixed bugs, added features, modified source code"
    echo -e "     ${BLUE}→${NC} After build, choose option 4 (Restart) to apply changes"
    echo ""
    echo -e "  ${GREEN}6)${NC} View logs"
    echo -e "     ${BLUE}→${NC} View logs from running containers"
    echo -e "     ${BLUE}→${NC} Use when: Debugging issues or monitoring activity"
    echo ""
    echo -e "  ${GREEN}7)${NC} Check status"
    echo -e "     ${BLUE}→${NC} See which containers are running"
    echo -e "     ${BLUE}→${NC} Use when: Verify services are up and get URLs"
    echo ""
    echo -e "  ${GREEN}8)${NC} Clean up (remove containers and volumes) ⚠️  DANGER"
    echo -e "     ${BLUE}→${NC} Remove all containers AND delete database"
    echo -e "     ${BLUE}→${NC} Use when: Complete reset or troubleshooting"
    echo ""
    echo -e "  ${GREEN}0)${NC} Exit"
    echo ""
    echo -e "${CYAN}────────────────────────────────────────────────────────────────────${NC}"
    echo -n "Enter choice [0-8]: "
}

# Function to check and kill conflicting ports
check_and_kill_ports() {
    local ports=(3000 8000 5432)
    local port_names=("Frontend" "Backend" "PostgreSQL")
    local conflicts=()
    local pids=()

    # Check for conflicts
    for i in "${!ports[@]}"; do
        local port="${ports[$i]}"
        local pid=$(lsof -ti:$port 2>/dev/null)
        if [ ! -z "$pid" ]; then
            conflicts+=("${port_names[$i]} (port $port)")
            pids+=("$port:$pid")
        fi
    done

    # If conflicts found, ask to kill
    if [ ${#conflicts[@]} -gt 0 ]; then
        echo -e "${YELLOW}⚠️  Port conflicts detected:${NC}"
        for conflict in "${conflicts[@]}"; do
            echo -e "  ${RED}✗${NC} $conflict is already in use"
        done
        echo ""
        echo -e "${CYAN}These ports must be free to start Docker services.${NC}"
        echo -e "${CYAN}Would you like to automatically kill these processes?${NC}"
        echo ""
        echo -n "Kill conflicting processes? (y/n): "
        read -r kill_choice
        echo ""

        if [ "$kill_choice" = "y" ] || [ "$kill_choice" = "Y" ]; then
            for port_pid in "${pids[@]}"; do
                local port="${port_pid%%:*}"
                local pid="${port_pid##*:}"
                echo -e "${BLUE}Killing process on port $port (PID: $pid)...${NC}"
                kill -9 $pid 2>/dev/null && echo -e "${GREEN}✓ Process killed${NC}" || echo -e "${RED}✗ Failed to kill process${NC}"
            done
            echo ""
            echo -e "${GREEN}✓ Port conflicts resolved${NC}"
            echo ""
            sleep 1
        else
            echo -e "${RED}Cannot start services with ports in use${NC}"
            echo -e "${YELLOW}Please manually stop the conflicting services and try again${NC}"
            echo ""
            return 1
        fi
    fi
    return 0
}

# Function to check and generate SSL certificates
check_and_generate_certs() {
    local cert_dir="nginx/certs"
    local cert_file="$cert_dir/server.crt"
    local key_file="$cert_dir/server.key"

    if [ ! -f "$cert_file" ] || [ ! -f "$key_file" ]; then
        echo -e "${YELLOW}🔒 SSL certificates not found in $cert_dir${NC}"
        echo -e "${BLUE}Generating self-signed certificates for local development...${NC}"
        
        # Check if openssl is installed
        if ! command -v openssl &> /dev/null; then
            echo -e "${RED}ERROR: openssl is not installed!${NC}"
            echo -e "${YELLOW}Please install openssl or provide certificates manually in $cert_dir${NC}"
            return 1
        fi

        mkdir -p "$cert_dir"
        openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
            -keyout "$key_file" \
            -out "$cert_file" \
            -subj "/C=TH/ST=Bangkok/L=Bangkok/O=Softnix/CN=localhost" &>/dev/null
        
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✓ Self-signed certificates generated successfully${NC}"
            echo ""
        else
            echo -e "${RED}✗ Failed to generate certificates${NC}"
            return 1
        fi
    fi
    return 0
}

# Function to show service URLs
show_urls() {
    echo ""
    echo -e "${GREEN}✓ Services are running!${NC}"
    echo ""
    echo -e "${CYAN}Access your application at:${NC}"
    echo -e "  ${GREEN}Frontend:${NC}   https://localhost"
    echo -e "  ${GREEN}Backend API:${NC} https://localhost/api"
    echo -e "  ${GREEN}WebSocket:${NC}  wss://localhost/ws"
    echo -e "  ${GREEN}Admin:${NC}      https://localhost/admin"
    echo ""
}

# Function to check if services are running
check_status() {
    echo -e "${BLUE}Checking container status...${NC}"
    echo ""
    docker compose ps
    echo ""

    # Check if containers are running
    if docker compose ps | grep -q "Up"; then
        show_urls
    else
        echo -e "${YELLOW}No services are currently running${NC}"
    fi
}

# Function to view logs
view_logs() {
    echo -e "${CYAN}Select logs to view:${NC}"
    echo "  1) All services"
    echo "  2) Backend only"
    echo "  3) Frontend only"
    echo -n "Enter choice [1-3]: "
    read -r log_choice

    case $log_choice in
        1)
            echo -e "${BLUE}Showing all logs (Ctrl+C to exit)...${NC}"
            docker compose logs -f
            ;;
        2)
            echo -e "${BLUE}Showing backend logs (Ctrl+C to exit)...${NC}"
            docker compose logs -f backend
            ;;
        3)
            echo -e "${BLUE}Showing frontend logs (Ctrl+C to exit)...${NC}"
            docker compose logs -f frontend
            ;;
        *)
            echo -e "${RED}Invalid choice${NC}"
            ;;
    esac
}

# Main loop
while true; do
    show_menu
    read -r choice
    echo ""

    case $choice in
        1)
            echo -e "${BLUE}Starting services in foreground...${NC}"
            echo ""
            # Check and kill conflicting ports
            if ! check_and_kill_ports; then
                continue
            fi
            # Check for SSL certificates
            if ! check_and_generate_certs; then
                continue
            fi
            echo -e "${YELLOW}Press Ctrl+C to stop${NC}"
            echo ""
            docker compose up
            ;;
        2)
            echo -e "${BLUE}Starting services in background...${NC}"
            echo ""
            # Check and kill conflicting ports
            if ! check_and_kill_ports; then
                continue
            fi
            # Check for SSL certificates
            if ! check_and_generate_certs; then
                continue
            fi
            docker compose up -d
            echo ""
            show_urls
            echo -e "${CYAN}TIP: Use option 6 to view logs, option 7 to check status${NC}"
            echo ""
            ;;
        3)
            echo -e "${BLUE}Stopping services...${NC}"
            echo ""
            docker compose down
            echo ""
            echo -e "${GREEN}✓ Services stopped (database preserved)${NC}"
            echo -e "${CYAN}TIP: Use option 2 to start again${NC}"
            echo ""
            ;;
        4)
            echo -e "${BLUE}Restarting services...${NC}"
            echo ""
            # Check and kill conflicting ports
            if ! check_and_kill_ports; then
                continue
            fi
            # Check for SSL certificates
            if ! check_and_generate_certs; then
                continue
            fi
            docker compose restart
            echo ""
            show_urls
            echo -e "${CYAN}TIP: Use option 6 to view logs if something went wrong${NC}"
            echo ""
            ;;
        5)
            echo -e "${CYAN}Select services to rebuild:${NC}"
            echo "  1) Backend only"
            echo "  2) Frontend only"
            echo "  3) All (backend + frontend)"
            echo -n "Enter choice [1-3, default 3]: "
            read -r build_choice
            echo ""

            case "$build_choice" in
                1)
                    echo -e "${BLUE}Rebuilding backend image...${NC}"
                    docker compose build --no-cache backend
                    ;;
                2)
                    echo -e "${BLUE}Rebuilding frontend image...${NC}"
                    docker compose build --no-cache frontend
                    ;;
                ""|3)
                    echo -e "${BLUE}Rebuilding all images...${NC}"
                    docker compose build --no-cache
                    ;;
                *)
                    echo -e "${RED}Invalid choice. Skipping build.${NC}"
                    echo ""
                    continue
                    ;;
            esac
            echo ""
            echo -e "${GREEN}✓ Build complete${NC}"
            echo ""
            echo -e "${YELLOW}NEXT STEP: Choose option 4 (Restart services) to apply changes${NC}"
            echo -e "${YELLOW}          or option 2 (Start services) if currently stopped${NC}"
            echo ""
            ;;
        6)
            view_logs
            echo ""
            ;;
        7)
            check_status
            ;;
        8)
            echo -e "${RED}⚠️  WARNING: This will remove all containers and volumes!${NC}"
            echo -e "${RED}⚠️  Database data will be PERMANENTLY DELETED!${NC}"
            echo ""
            echo -n "Type 'yes' to confirm deletion: "
            read -r confirm
            if [ "$confirm" = "yes" ]; then
                echo ""
                echo -e "${BLUE}Cleaning up...${NC}"
                docker compose down -v
                echo ""
                echo -e "${GREEN}✓ Cleanup complete${NC}"
                echo -e "${CYAN}TIP: Use option 5 to rebuild, then option 2 to start fresh${NC}"
            else
                echo -e "${YELLOW}Cleanup cancelled - your data is safe${NC}"
            fi
            echo ""
            ;;
        0)
            echo -e "${GREEN}Goodbye!${NC}"
            exit 0
            ;;
        *)
            echo -e "${RED}Invalid choice. Please try again.${NC}"
            echo ""
            ;;
    esac
done
