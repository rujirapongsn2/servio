# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Voice Agents SDK Sample App that demonstrates building voice-enabled conversational agents using OpenAI's Agents SDK and Python. The application features a FastAPI backend with WebSocket support and a Next.js frontend, showcasing multi-turn conversations, push-to-talk audio, function calling, and streaming responses.

## Development Commands

### Initial Setup
```bash
# Set up environment: Create .env file at project root with required API keys
OPENAI_API_KEY=<your_api_key>
SOFTNIX_API_KEY=<your_softnix_key>    # Optional
GEMINI_API_KEY=<your_gemini_key>      # Optional

# Database credentials (auto-configured by docker-compose)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=voice_agents
```

### Running the Application (Docker - Primary Method)

The application runs in Docker containers managed by `./start.sh`:

```bash
# Start services in background
./start.sh
# Choose option 2 (Start services - background)

# Access the application:
# - Frontend: https://localhost
# - Backend API: https://localhost/api
# - WebSocket: wss://localhost/ws
# - Admin Panel: https://localhost/admin
```

**Common Operations:**
- **First time setup**: Option 5 (Build) → Option 2 (Start)
- **After code changes**: Option 5 (Rebuild) → Option 4 (Restart)
- **After .env changes**: Option 4 (Restart only)
- **View logs**: Option 6
- **Check status**: Option 7
- **Stop services**: Option 3

### Local Development (Without Docker - Legacy)

For local development without Docker:

```bash
# Backend only (hot reload)
cd server && uv run server.py

# Frontend only
cd frontend && npm run dev:next

# Lint
cd frontend && npm run lint
```

### Docker Services Architecture

The application runs in 4 Docker containers:
- **nginx**: Reverse proxy (ports 80→8080, 443→8443) with SSL termination
- **postgres**: PostgreSQL 15 database with persistent storage
- **backend**: FastAPI server (Python 3.11) on port 8000 inside container
- **frontend**: Next.js application (Node 20) on port 3000 inside container

### Rebuild Requirements

**Must rebuild images (Option 5):**
- Modified Python code in `server/`
- Modified React/Next.js code in `frontend/src/`
- Changed dependencies (`package.json`, `pyproject.toml`)
- Modified Dockerfile

**Only restart needed (Option 4):**
- Changed `.env` file
- Modified nginx configuration

## Architecture

### Backend (Python/FastAPI)

**Entry Point**: `server/server.py`
- FastAPI app with WebSocket endpoint at `/ws` (accessible via `wss://localhost/ws` through nginx)
- Runs in Docker container on port 8000 (internal), proxied by nginx to https://localhost/api
- Uses OpenAI Agents SDK (`openai-agents[voice]`) for voice pipeline
- Uses PostgreSQL 15 for persistent data storage
- Loads environment variables from `.env` at root level via docker-compose
- Built with multi-stage Dockerfile using `uv` package manager

**Key Components**:

1. **`Workflow` class** (in `server.py`): Implements `VoiceWorkflowBase` for voice interactions
   - Manages conversation flow using `Runner.run_streamed()`
   - Handles streaming events and text output
   - Works with `WebsocketHelper` to send updates to client

2. **`WebsocketHelper`** (in `app/utils.py`): Core state management for WebSocket connections
   - Manages conversation history and current agent state
   - Handles message transformations between SDK events and WebSocket messages
   - Key methods:
     - `show_user_input()`: Adds user message to history
     - `stream_response()`: Streams partial responses to frontend
     - `handle_new_item()`: Processes SDK events (tool calls, text output)
     - `send_audio_chunk()`: Streams audio back to client
     - `text_output_complete()`: Finalizes response and updates agent state

3. **Agent Configuration** (`app/agent_config.py`): Multi-agent architecture
- **Coordinator Agent**: Routes users to specialized agents (starting point)
   - **Stylist Agent**: Handles styling queries, uses WebSearchTool with Tokyo location
   - **Customer Support Agent**: Handles orders and refunds
   - All agents use conversational tone without emojis or formal formatting
   - Agents can handoff to each other based on user needs

4. **Message Flow**:
   - Text messages: `history.update` → `Workflow.run()` → streaming via `Runner.run_streamed()`
   - Audio messages: Client sends audio chunks → `input_audio_buffer.append` → `input_audio_buffer.commit` → `VoicePipeline.run()` → audio chunks streamed back
   - History synchronization uses `history.updated` messages with reasons: `user.input`, `response.text.delta`, `response.input_item`, `response.done`

### Frontend (Next.js/TypeScript/React)

**Entry Point**: `frontend/src/app/page.tsx`
- Main page component orchestrating `useWebsocket` and `useAudio` hooks
- Runs in Docker container on port 3000 (internal), proxied by nginx to https://localhost
- Built with multi-stage Dockerfile (builder + production runner)
- Production build served via `npm start` in container

**Key Hooks**:

1. **`useWebsocket`** (`hooks/useWebsocket.ts`): WebSocket state management
   - Connects to backend WebSocket (default: `wss://localhost/ws` in Docker, or `ws://localhost:8000/ws` for local dev)
   - Connection URL configurable via `NEXT_PUBLIC_WEBSOCKET_ENDPOINT` environment variable
   - Manages conversation history and agent name
   - Key functions:
     - `sendTextMessage()`: Sends text input
     - `sendAudioMessage()`: Sends audio as base64-encoded Int16Array
     - `resetHistory()`: Clears conversation and resets to coordinator agent
   - Message types handled:
     - `history.updated`: Updates conversation state
     - `response.audio.delta`: Receives audio chunks from backend
     - `audio.done`: Signals audio completion

2. **`useAudio`** (`hooks/useAudio.ts`): Audio recording and playback
   - Handles microphone input and audio playback
   - Returns frequency data for visualization
   - Works with `wavtools` library for audio processing

**Component Structure**:
- `AudioChat`: Handles audio recording UI with push-to-talk
- `ChatDialog`/`ChatHistory`: Displays conversation messages
- `Composer`: Text input component with submit handling
- `Header`: Shows current agent name and audio visualization
- Message components in `components/messages/`: Specialized renderers for different message types (text, function calls, handoffs, web search)

**Type System** (`lib/types.ts`):
- Uses OpenAI SDK types: `ResponseInputItem`, `ResponseOutputItem`, `ResponseFunctionToolCall`
- `Message` type: Union of input items, output items, and tool calls

### WebSocket Protocol

**Client → Server**:
- `history.update`: Sync history or send new text message (includes `inputs` array, optional `reset_agent`)
- `input_audio_buffer.append`: Send audio chunk (base64-encoded)
- `input_audio_buffer.commit`: Signal audio input complete

**Server → Client**:
- `history.updated`: Update conversation state (includes `type`, `reason`, `inputs`, `agent_name`)
  - Reasons: `user.input`, `response.text.delta`, `response.input_item`, `response.done`
- `response.audio.delta`: Audio chunk from agent (base64-encoded PCM Int16)
- `audio.done`: Audio playback complete

### Audio Processing

- Frontend sends/receives audio as base64-encoded Int16Array (PCM 16-bit)
- Backend converts between Int16 and float32 numpy arrays
- `VoicePipeline` uses `TTSModelSettings` with configurable `buffer_size` (default: 512)
- Audio transformation pipeline in `server/app/utils.py`: `transform_data_to_events()`

## Environment Configuration

The application loads environment variables from `.env` at the project root via docker-compose.

**Required Variables:**
- `OPENAI_API_KEY`: OpenAI API key for Agents SDK

**Optional Variables:**
- `SOFTNIX_API_KEY`: API key for Softnix GenAI integration
- `GEMINI_API_KEY`: API key for Google Gemini File Search features
- `ALLOWED_ORIGINS`: CORS allowed origins (comma-separated)
- `NEXT_PUBLIC_WEBSOCKET_ENDPOINT`: Override default WebSocket URL (frontend)

**Database Configuration (auto-configured by docker-compose):**
- `POSTGRES_USER`: Database username (default: postgres)
- `POSTGRES_PASSWORD`: Database password (default: postgres)
- `POSTGRES_DB`: Database name (default: voice_agents)
- `DATABASE_URL`: Auto-generated connection string: `postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}`

**Container-Specific:**
- `UV_CACHE_DIR`: Cache directory for uv package manager (default: /tmp/uv_cache)

## Python Dependencies

Managed via `uv` (see `server/pyproject.toml`):
- `fastapi[standard]` - Web framework
- `openai-agents[voice]` - OpenAI Agents SDK with voice support
- `numpy` - Audio array processing
- `python-dotenv` - Environment variable loading
- `uvicorn` - ASGI server
- `sqlalchemy` - ORM for PostgreSQL database
- `psycopg2-binary` - PostgreSQL adapter for Python

Dependencies are installed in Docker build stage using `uv sync --frozen`.

## Adding New Agents or Tools

1. Define tools using `@function_tool` decorator in `app/agent_config.py`
2. Create `Agent` instances with name, instructions, model, tools, and handoffs
3. Update agent handoff chains as needed
4. The `starting_agent` variable determines the initial conversation agent (currently `triage_agent`)

## Modifying Mock Data

Edit `server/app/mock_api.py` to change sample order data or add new mock endpoints. These are used by the customer support agent for demonstration purposes.

## Docker Networking & Security

### Network Configuration
- **proxy-network**: Bridge network connecting nginx, frontend, and backend
- **db-network**: Internal bridge network (no external access) for backend-to-postgres communication

### Port Mapping
- Host → Container:
  - `80:8080` - HTTP (nginx)
  - `443:8443` - HTTPS (nginx)
- Internal only (not exposed to host):
  - `3000` - Frontend Next.js server
  - `8000` - Backend FastAPI server
  - `5432` - PostgreSQL database

### Security Features
- All containers run as non-root users
- Read-only filesystems where applicable
- Security options: `no-new-privileges:true`, `cap_drop: ALL`
- SSL/TLS certificates auto-generated for local development in `nginx/certs/`
- Database accessible only via internal network

### Health Checks
- **Backend**: HTTP check on `/api/health` endpoint
- **Frontend**: HTTP check on root endpoint
- **PostgreSQL**: `pg_isready` command
- Start period, interval, timeout, and retries configured for all services

### Data Persistence
- PostgreSQL data stored in Docker volume: `postgres_data`
- Backend uploads/data stored in bind mount: `./server/data`
