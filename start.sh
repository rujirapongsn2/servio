#!/bin/bash

# Voice Agents SDK Sample App - Quick Start Script
# This script starts both frontend and backend servers in development mode

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Print banner
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   Voice Agents SDK Sample App - Quick Start           ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${RED}ERROR: .env file not found!${NC}"
    echo -e "${YELLOW}Please create a .env file with your OPENAI_API_KEY${NC}"
    echo ""
    echo "Example:"
    echo "  OPENAI_API_KEY=your_api_key_here"
    echo ""
    exit 1
fi

# Check if dependencies are installed
if [ ! -d "frontend/node_modules" ]; then
    echo -e "${YELLOW}Frontend dependencies not found. Installing...${NC}"
    cd frontend && npm install && cd ..
fi

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo -e "${RED}ERROR: 'uv' is not installed!${NC}"
    echo -e "${YELLOW}Please install uv: https://github.com/astral-sh/uv${NC}"
    exit 1
fi

# Start the development servers
echo -e "${GREEN}✓${NC} Environment check passed"
echo ""
echo -e "${BLUE}Starting development servers...${NC}"
echo ""
echo -e "${GREEN}Frontend:${NC} Will be available at http://localhost:3001 (or next available port)"
echo -e "${GREEN}Backend:${NC}  http://localhost:8000"
echo -e "${GREEN}WebSocket:${NC} ws://localhost:8000/ws"
echo -e "${GREEN}Admin:${NC}    http://localhost:3001/admin"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all servers${NC}"
echo ""

# Change to frontend directory and start both servers
cd frontend && npm run dev
