# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Voice Agents SDK Sample App that demonstrates building voice-enabled conversational agents using OpenAI's Agents SDK and Python. The application features a FastAPI backend with WebSocket support and a Next.js frontend, showcasing multi-turn conversations, push-to-talk audio, function calling, and streaming responses.

## Development Commands

### Initial Setup
```bash
# Install all dependencies (frontend + backend)
make sync

# Set up environment: Create .env file at project root with:
OPENAI_API_KEY=<your_api_key>
```

### Running the Application
```bash
# Run both frontend and backend (production mode)
make serve

# Run frontend and backend together (development mode with hot reload)
cd frontend && npm run dev

# Run only frontend (Next.js dev server with Turbo)
cd frontend && npm run dev:next

# Run only backend server
cd frontend && npm run dev:server
# OR
cd server && uv run server.py
```

### Frontend Commands
```bash
cd frontend

npm run build        # Build Next.js production bundle
npm run start        # Start production server
npm run lint         # Run ESLint
```

### Backend Server
The backend runs on `http://localhost:8000` with a WebSocket endpoint at `/ws`. It uses `uvicorn` with hot reload enabled in development.

## Architecture

### Backend (Python/FastAPI)

**Entry Point**: `server/server.py`
- FastAPI app with WebSocket endpoint at `/ws`
- Uses OpenAI Agents SDK (`openai-agents[voice]`) for voice pipeline
- Loads environment variables from `../.env` at root level

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

**Key Hooks**:

1. **`useWebsocket`** (`hooks/useWebsocket.ts`): WebSocket state management
   - Connects to backend WebSocket (default: `ws://localhost:8000/ws`)
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

The backend loads environment variables from `.env` at the project root (not `server/.env`). Required variable:
- `OPENAI_API_KEY`: OpenAI API key for Agents SDK

Optional frontend environment variable:
- `NEXT_PUBLIC_WEBSOCKET_ENDPOINT`: Override default WebSocket URL

## Python Dependencies

Managed via `uv` (see `server/pyproject.toml`):
- `fastapi[standard]` - Web framework
- `openai-agents[voice]` - OpenAI Agents SDK with voice support
- `numpy` - Audio array processing
- `python-dotenv` - Environment variable loading
- `uvicorn` - ASGI server

## Adding New Agents or Tools

1. Define tools using `@function_tool` decorator in `app/agent_config.py`
2. Create `Agent` instances with name, instructions, model, tools, and handoffs
3. Update agent handoff chains as needed
4. The `starting_agent` variable determines the initial conversation agent (currently `triage_agent`)

## Modifying Mock Data

Edit `server/app/mock_api.py` to change sample order data or add new mock endpoints. These are used by the customer support agent for demonstration purposes.
