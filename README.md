# Servio - Customer Support Agent

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![FastAPI](https://img.shields.io/badge/Built_with-FastAPI-yellow)
![NextJS](https://img.shields.io/badge/Built_with-NextJS-blue)
![OpenAI API](https://img.shields.io/badge/Powered_by-OpenAI_API-orange)

Servio is a powerful voice-enabled customer support agent system built with OpenAI's [Agents SDK](https://openai.github.io/openai-agents-python) and Python. The backend uses FastAPI with WebSocket support, while the frontend is built with Next.js, providing a seamless voice and chat interface for customer interactions.

## Key Features

- **Voice & Chat Interface** - Dual-mode support for voice (push-to-talk) and text chat interactions
- **Multi-Agent System** - Specialized AI agents that collaborate and transfer conversations seamlessly
- **Admin Dashboard** - Comprehensive web-based admin console for managing agents, tools, and settings
- **Widget Embedding** - Easy-to-embed chat/voice widgets for websites
- **Custom Tools Integration** - Support for custom APIs, MCP tools, and Gemini File Search
- **Dynamic Agent Configuration** - Create and configure agents through the admin interface without code changes
- **Real-time Monitoring** - Track active sessions and agent performance
- **Multi-turn Conversations** - Continuous back-and-forth conversations with context retention
- **Streaming Responses** - Real-time text and audio streaming for instant feedback
- **Softnix Integration** - Built-in integration with Softnix GenAI knowledge base

Servio is designed to be a production-ready customer support solution that you can customize and extend to meet your specific business needs.

## Table of Contents

- [Key Features](#key-features)
- [Multi-Agent Architecture](#multi-agent-architecture)
- [File Store Agents](#file-store-agents)
- [Widget Embedding](#widget-embedding)
- [Requirements](#requirements)
- [How to use](#how-to-use)
  - [Quick Start with Docker (Recommended)](#quick-start-with-docker-recommended-)
  - [Manual Installation (Development)](#manual-installation-development)
- [Docker Deployment](#docker-deployment)
- [Using the App](#using-the-app)
- [Admin & Agents](#admin--agents)
- [Screenshots & GIFs](#screenshots--gifs)
- [Contributing](#contributing)
- [License](#license)

## Multi-Agent Architecture

This sample app demonstrates a **multi-agent system** where multiple AI agents work together, each specialized in different domains. Think of it like calling a customer service center with different departments!

### The Four Agents

#### 1. **Coordinator Agent** (Main Router) 🎯
- **Role**: First point of contact that routes conversations to the appropriate specialist
- **Instructions**: "Route the user to the appropriate agent based on their request"
- **Starting Point**: Every conversation begins here
- **Can transfer to**: Softnix Sales Agent, Stylist Agent, Customer Support Agent, and any agents you create in Admin (e.g., Dtwin Agent)

**Example**:
```
You: "Hello, I need help"
Coordinator Agent: Greets you and waits for more context

You: "What products does Softnix offer?"
Coordinator Agent: → Transferred to Softnix Sales Agent
```

#### 2. **Softnix Sales Agent** (Product Information) 💼
- **Role**: Provides information about Softnix products and services
- **Special Tools**:
  - `get_softnix_info(question)` - Queries Softnix GenAI knowledge base API
  - Connects to: https://genai.softnix.ai/external/api/chat-messages
- **Can transfer to**: Customer Support Agent (if purchase-related questions come up)

**Example**:
```
You: "What is Softnix GenAI?"
Softnix Sales Agent: Uses get_softnix_info() → Returns detailed product information

You: "How much does it cost?"
Softnix Sales Agent: Uses get_softnix_info() → Provides pricing details

You: "I want to place an order"
Softnix Sales Agent: → Transferred to Customer Support Agent
```

#### 3. **Stylist Agent** (Fashion Consultant) 👔
- **Role**: Provides fashion advice and styling recommendations
- **Special Tools**:
  - `WebSearchTool` - Searches the internet for fashion information
  - Location: Bangkok (can find local stores and trends)
- **Can transfer to**: Customer Support Agent (if order-related questions come up)

**Example**:
```
You: "Recommend summer outfits"
Stylist Agent: Uses WebSearch → Suggests breathable clothing

You: "I want to check my order"
Stylist Agent: → Transferred to Customer Support Agent
```

#### 3. **Customer Support Agent** (Customer Service) 🛍️
- **Role**: Handles orders, refunds, and purchase information
- **Special Tools**:
  - `get_past_orders()` - Retrieves order history
  - `submit_refund_request(order_number)` - Processes refund requests
- **Cannot transfer**: This is the final agent (no handoffs)

**Example**:
```
You: "Check my orders"
Customer Support: Uses get_past_orders() → Shows all orders

You: "Refund order AB472"
Customer Support: Uses submit_refund_request("AB472") → Processes refund
```

### How Agent Handoffs Work

When you see "**Transferred to [Agent Name]**" in the conversation, it means:

> The AI has determined that a different specialist would better serve your needs and has seamlessly transferred the conversation.

**Technical Flow**:
1. Current agent decides to transfer → `output.last_agent` changes
2. Backend updates `self.latest_agent = output.last_agent`
3. WebSocket sends message with new `agent_name`
4. Frontend displays "Transferred to [Agent Name]"
5. The runtime coordinator agent automatically includes DB-defined agents as handoffs; if you’ve created “Dtwin Agent”, the coordinator can route to it when users mention DTWIN

### Conversation Flow Diagram

```
                    ┌─────────────────────┐
                    │  Start Conversation │
                    │ (Coordinator Agent) │
                    └──────────┬──────────┘
                               │
                        What did you say?
                               │
        ┌───────────────┬─────────────┬───────────────┬───────────────┐
        ▼               ▼             ▼               ▼
┌───────────────┐  ┌─────────┐  ┌──────────────┐  ┌───────────────┐
│ Softnix Sales │  │ Stylist │  │ Customer     │  │  Dtwin Agent  │
│    Agent      │  │ Agent   │  │ Support Agent│  │     (DB)      │
└───────┬───────┘  └────┬────┘  └──────────────┘  └───────────────┘
        │               │
        │               │ (If order mentioned)
        │               │
        │               ▼
        │       ┌──────────────┐
        └──────>│ Customer     │
                │ Support Agent│
                └──────────────┘

Routes:
• Softnix questions → Softnix Sales Agent
• Fashion advice → Stylist Agent
• Order/refund issues → Customer Support Agent
• DTWIN questions → Dtwin Agent (from database)
• Additional DB agents appear as extra branches as configured in Admin
```

### Why Multi-Agent?

✅ **Specialized Expertise** - Each agent excels in their domain
✅ **More Accurate Responses** - Uses domain-specific tools
✅ **Flexible Routing** - Transfers based on context
✅ **Easy to Extend** - Add new agents anytime

### Customizing Agents

Edit `server/app/agent_config.py` to:
- Add new agents with specialized tools
- Modify agent instructions and behavior
- Configure handoff relationships
- Add custom function tools

## Widget Embedding

Servio provides an easy-to-embed widget that you can add to any website, enabling instant access to your AI agents for your customers.

### Quick Start

1. **Generate Widget Code**: Navigate to Admin Console → Tools → Widget
2. **Configure Widget**:
   - Choose widget type: `voice` (with push-to-talk) or `chat` (text-only)
   - Select position: `bottom-right` or `bottom-left`
   - Set server URL (default: `http://localhost:3000`)
3. **Copy & Embed**: Copy the generated code and paste it into your website's HTML

### Widget Code Example

```html
<!-- Servio Chat Widget -->
<script
  src="http://localhost:3000/embed.js"
  data-type="chat"
  data-position="bottom-right"
  data-server-url="http://localhost:3000">
</script>
```

### Widget Types

**Chat Widget** (`data-type="chat"`):
- Text-based chat interface
- No microphone permissions required
- Perfect for desktop users or situations where voice isn't ideal

**Voice Widget** (`data-type="voice"`):
- Push-to-talk voice interaction
- Requests microphone permission
- Ideal for hands-free operation

### Customization

The widget automatically:
- Adapts to your agent branding (displays agent name and logo)
- Matches your theme (supports light/dark mode)
- Responds to user interactions with visual feedback
- Shows conversation history with proper formatting
- Handles agent transfers seamlessly

## File Store Agents

The app includes a **File Store Agent** system that allows you to create document search agents powered by Google's Gemini File Search API. This enables your AI agents to answer questions based on your uploaded documents.

### What are File Store Agents?

File Store Agents are specialized agents that can search and retrieve information from a collection of documents you upload. They use Gemini's advanced RAG (Retrieval-Augmented Generation) capabilities to provide accurate answers with source citations.

### Key Features

✅ **Multi-File Upload** - Upload multiple documents at once (PDF, TXT, MD, DOC, DOCX)
✅ **Drag-and-Drop Interface** - Easy file upload with visual feedback
✅ **Auto-Tool Creation** - Automatically creates a search tool when you create a file store
✅ **File Management** - Add or remove files from stores at any time
✅ **Detailed Testing** - Test queries with grounding sources and metadata
✅ **Thai Filename Support** - Handles non-ASCII characters automatically
✅ **Progress Tracking** - Visual progress bars during file uploads

### How to Create a File Store Agent

1. **Navigate to Admin Console**
   - Go to `http://localhost:3001/admin` (or your configured port)
   - Click "Agents" in the sidebar
   - Switch to the "File Store Agents" tab

2. **Create a New File Store**
   - Click "New File Store" button
   - Enter a descriptive display name (e.g., "Product Documentation")
   - Upload your documents (supports multiple files)
   - Check "Create Tool Automatically" (default: enabled)
   - Click "Create File Store"

3. **The Tool is Auto-Created**
   - When "Create Tool Automatically" is enabled, a search tool is automatically created
   - Tool name: `{store_name}_search`
   - This tool becomes available to all agents in your system
   - Agents can use it to search the documents in that store

4. **Test Your File Store**
   - Click the green "Play" button next to your file store
   - Enter a question about your documents
   - See the AI response with:
     - Answer based on document content
     - Grounding sources (which documents were referenced)
     - Response time and metadata

5. **Manage Files**
   - Click the blue "Upload" button to manage files
   - View all files in the store
   - Upload additional files
   - Delete individual files

### Example Use Cases

**Product Documentation**
```
Store: "Product Manuals"
Files: product_guide.pdf, faq.pdf, specifications.pdf
Use case: Customer support agents can answer technical questions
```

**HR Knowledge Base**
```
Store: "HR Policies"
Files: employee_handbook.pdf, leave_policy.pdf, benefits.pdf
Use case: HR chatbot can answer employee policy questions
```

**Legal Documents**
```
Store: "Legal Contracts"
Files: contract_template.pdf, terms.pdf, privacy_policy.pdf
Use case: Legal assistant can help with contract questions
```

### Using File Store Tools in Agents

Once a file store is created with auto-tool enabled, you can assign the tool to any agent:

1. Go to "Agents" tab in Admin
2. Create or edit an agent
3. In the "Tools" section, select the auto-created tool (e.g., "product_docs_search")
4. Save the agent

Now when users talk to that agent, it can search your documents to answer questions!

### API Configuration

To use File Store Agents, you need a Gemini API key:

1. Get your API key from: https://ai.google.dev/
2. Add to your `.env` file:
   ```bash
   GEMINI_API_KEY=your_api_key_here
   ```

### Technical Details

- **Backend**: `server/app/gemini_service.py` handles all Gemini API interactions
- **Database**: Stores file store metadata and file references in SQLite
- **File Upload**: Supports up to 10MB per file (configurable)
- **Supported Formats**: PDF, TXT, MD, DOC, DOCX
- **Unicode Support**: Automatically handles non-ASCII filenames by creating temporary ASCII copies

### Troubleshooting

**Issue**: Files with Thai/Unicode names fail to upload
- **Solution**: The system automatically handles this by creating temporary ASCII-named copies

**Issue**: Query returns no results
- **Solution**: Make sure your documents contain relevant information and try rephrasing your query

**Issue**: File upload is slow
- **Solution**: Large files take time to process. The progress bar shows upload status.

## Requirements

- OpenAI API key
  - If you're new to the OpenAI API, [sign up for an account](https://platform.openai.com/signup).
  - Follow the [Quickstart](https://platform.openai.com/docs/quickstart) to retrieve your API key.
- Gemini API key (optional, for File Store Agents)
  - Get your API key from: https://ai.google.dev/
  - Required only if you want to use File Store Agents feature
- Node.js and npm
- `uv` installed on your system

## How to use

### Quick Start with Docker (Recommended) 🐳

The easiest way to get started is using Docker. No need to install Node.js, Python, or uv!

1. **Prerequisites:**
   - Install [Docker Desktop](https://docs.docker.com/get-docker/)
   - Make sure Docker is running

2. **Set the API keys:**

   Create a `.env` file at the root of the project:

   ```bash
   cp .env.example .env
   # Edit .env and add your API keys:
   # OPENAI_API_KEY=your_openai_api_key
   # SOFTNIX_API_KEY=your_softnix_api_key (optional)
   # GEMINI_API_KEY=your_gemini_api_key (optional)
   ```

3. **Clone the Repository:**

   ```bash
   git clone https://github.com/rujirapongsn2/servio.git
   cd servio/
   ```

4. **Run with Docker:**

   ```bash
   # Start the Docker management script
   ./start.sh

   # Then select option 2 (Start services in background)
   # Or select option 1 to see logs in real-time
   ```

   The interactive script provides:
   - ✅ Start/Stop services
   - ✅ View logs (all, backend only, or frontend only)
   - ✅ Check container status
   - ✅ Build/Rebuild images
   - ✅ Clean up containers and volumes

   **Access your application:**
   - Frontend: [`http://localhost:3000`](http://localhost:3000)
   - Backend API: [`http://localhost:8000`](http://localhost:8000)
   - Admin Console: [`http://localhost:3000/admin`](http://localhost:3000/admin)
   - WebSocket: `ws://localhost:8000/ws`

   **Direct Docker Commands** (if you prefer):
   ```bash
   # Build and start services
   docker-compose up -d

   # View logs
   docker-compose logs -f

   # Stop services
   docker-compose down
   ```

### Manual Installation (Development)

If you prefer to run without Docker:

1. **Set the API keys:**

   Create a `.env` file at the root of the project (see `.env.example` for reference):

   ```bash
   # Required: OpenAI API key for voice agents
   OPENAI_API_KEY=<your_openai_api_key>

   # Optional: Softnix API key
   SOFTNIX_API_KEY=<your_softnix_api_key>

   # Optional: Gemini API key for File Store Agents
   GEMINI_API_KEY=<your_gemini_api_key>
   ```

   Alternatively, you can set the `OPENAI_API_KEY` environment variable [globally in your system](https://platform.openai.com/docs/libraries#create-and-export-an-api-key).

2. **Clone the Repository:**

   ```bash
   git clone https://github.com/rujirapongsn2/servio.git
   cd servio/
   ```

3. **Install dependencies:**

   You will have to install both the dependencies for the front-end and the server. To do this run in the project root:

   ```bash
   make sync
   ```

4. **Run the app:**

   You have multiple options to start the application:

   **Option 1: Using Make (Production Mode)**
   ```bash
   make serve
   ```
   Starts the app in production mode at [`http://localhost:3000`](http://localhost:3000).

   **Option 2: Development Mode with Hot Reload**
   ```bash
   cd frontend && npm run dev
   ```
   - Frontend: [`http://localhost:3001`](http://localhost:3001) (or next available port)
   - Backend: [`http://localhost:8000`](http://localhost:8000)
   - WebSocket: `ws://localhost:8000/ws`

   **Option 3: Run Separately**
   ```bash
   # Terminal 1 - Frontend only
   cd frontend && npm run dev:next

   # Terminal 2 - Backend only
   cd server && uv run server.py
   ```

   **Available Ports:**
   - Frontend: `3000` (production) or `3001+` (development, auto-increments if busy)
   - Backend: `8000`
   - Admin Console: [`http://localhost:3001/admin`](http://localhost:3001/admin)

## Docker Deployment

Servio includes production-ready Docker deployment with multi-container architecture.

### Architecture

The Docker setup uses **docker-compose** to orchestrate two services:

- **Backend Container** (Python 3.11 + FastAPI + uvicorn)
  - Port: 8000
  - Auto-installs dependencies using `uv`
  - SQLite database persisted via volume mount
  - Health checks on `/api/admin/sessions` endpoint

- **Frontend Container** (Node.js 20 + Next.js)
  - Port: 3000
  - Multi-stage build for optimized image size
  - Runs as non-root user for security
  - Health checks on HTTP root endpoint

- **Shared Network** (`voice-agent-network`)
  - Allows backend and frontend to communicate
  - Internal DNS resolution (backend can reach frontend and vice versa)

### Docker Files Structure

```
CSAgent/
├── docker-compose.yml          # Service orchestration
├── .env                        # Environment variables (create from .env.example)
├── .env.example               # Template for environment variables
├── start.sh                   # Interactive Docker management script
├── server/
│   ├── Dockerfile            # Backend container definition
│   ├── .dockerignore        # Exclude unnecessary files
│   └── data/                # SQLite database volume (auto-created)
└── frontend/
    ├── Dockerfile           # Frontend container definition (multi-stage)
    └── .dockerignore       # Exclude node_modules, .next, etc.
```

### Environment Variables

Required variables in `.env`:

```bash
# Required
OPENAI_API_KEY=your_openai_api_key

# Optional
SOFTNIX_API_KEY=your_softnix_api_key
GEMINI_API_KEY=your_gemini_api_key

# Docker Configuration (optional, defaults provided)
BACKEND_PORT=8000
FRONTEND_PORT=3000
DATABASE_PATH=/app/data/agents.db
NEXT_PUBLIC_WEBSOCKET_ENDPOINT=ws://localhost:8000/ws

# Production CORS (comma-separated domains)
ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
```

### Database Persistence

The SQLite database is persisted using Docker volumes:

- **Volume Mount**: `./server/data:/app/data`
- **Database File**: `./server/data/agents.db`
- **Persistence**: Data survives container restarts and rebuilds
- **Backup**: Simply copy `./server/data/agents.db` to back up

### Using the Docker Management Script

The `start.sh` script provides an interactive menu for managing Docker services:

```bash
./start.sh
```

**Menu Options:**

1. **Start services (foreground)** - See logs in real-time, Ctrl+C to stop
2. **Start services (background)** - Run in background, use logs option to view output
3. **Stop services** - Stop all containers (data is preserved)
4. **Restart services** - Restart both frontend and backend
5. **Build/Rebuild images** - Rebuild Docker images (use after code changes)
6. **View logs** - View logs for all services, backend only, or frontend only
7. **Check status** - See container status and access URLs
8. **Clean up** - Remove containers and volumes (⚠️ deletes database!)
0. **Exit** - Quit the script

### Production Deployment

For production deployment:

1. **Set production environment variables:**
   ```bash
   # In .env file
   ALLOWED_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
   NEXT_PUBLIC_WEBSOCKET_ENDPOINT=wss://yourdomain.com/ws
   ```

2. **Build optimized images:**
   ```bash
   docker-compose build --no-cache
   ```

3. **Start services:**
   ```bash
   docker-compose up -d
   ```

4. **Optional: Add Nginx reverse proxy for SSL/TLS:**
   ```nginx
   server {
       listen 80;
       server_name yourdomain.com;

       location / {
           proxy_pass http://localhost:3000;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection 'upgrade';
           proxy_set_header Host $host;
       }

       location /api/ {
           proxy_pass http://localhost:8000;
       }

       location /ws {
           proxy_pass http://localhost:8000/ws;
           proxy_http_version 1.1;
           proxy_set_header Upgrade $http_upgrade;
           proxy_set_header Connection "upgrade";
       }
   }
   ```

### Troubleshooting

**Port already in use:**
```bash
# Find process using port 3000
lsof -ti :3000 | xargs kill -9

# Or change port in .env
FRONTEND_PORT=3001
```

**Database not persisting:**
```bash
# Check volume mount
docker-compose exec backend ls -la /app/data/

# Verify DATABASE_PATH environment variable
docker-compose exec backend env | grep DATABASE_PATH
```

**Frontend can't reach backend:**
```bash
# Check network
docker network inspect csagent_voice-agent-network

# Test connection from frontend container
docker-compose exec frontend ping backend
```

**View container logs:**
```bash
# All services
docker-compose logs -f

# Backend only
docker-compose logs -f backend

# Frontend only
docker-compose logs -f frontend

# Last 100 lines
docker-compose logs --tail=100
```

### Docker Commands Quick Reference

```bash
# Build images
docker-compose build
docker-compose build --no-cache  # Rebuild from scratch

# Start services
docker-compose up                # Foreground (see logs)
docker-compose up -d            # Background (detached)

# Stop services
docker-compose down             # Stop and remove containers
docker-compose down -v          # Also remove volumes (⚠️ deletes data!)

# View status
docker-compose ps               # Container status
docker-compose top              # Running processes

# Restart
docker-compose restart          # Restart all services
docker-compose restart backend  # Restart specific service

# Execute commands in containers
docker-compose exec backend bash    # Open bash in backend
docker-compose exec frontend sh     # Open sh in frontend (Alpine)

# View resource usage
docker stats                    # Real-time stats
```

## Admin & Agents

### Admin Console
- URL: `http://localhost:3001/admin` (or next available port in development mode)
- Default login: `admin` / set via database; token stored in `localStorage` for subsequent requests.

### Agents Management
The Admin Console provides two tabs for managing your AI agents:

#### 1. **Agents Tab**
- Create, edit, and delete traditional agents
- Configure agent instructions, models, and tools
- Set up agent handoffs and relationships
- Test agents directly in the browser

#### 2. **File Store Agents Tab**
- Create document search agents powered by Gemini File Search
- Upload and manage document collections
- Auto-create search tools for your file stores
- Test queries with grounding sources
- Manage files: add, remove, or update documents

### Dynamic Coordinator + DB Agents
- The backend composes a coordinator agent at runtime that includes agents from the database as handoffs. If you create a "Dtwin Agent" in Admin, the coordinator can transfer to it when a user asks about DTWIN.
- Reset in-call agent state triggers rebuilding the coordinator with latest DB changes.
- File Store Agent tools are automatically available to all agents once created.

### Dtwin Agent Tips
- For offline/dev environments, disable MCP tools to avoid network errors:
  - Add to `.env`: `DISABLE_MCP=1`
- To make Dtwin testable without network, run:
  ```bash
  uv run python server/scripts/configure_dtwin_fallback.py
  ```
  This removes MCP tools from Dtwin and attaches a built-in mock tool (`get_past_orders`).

### Testing Agents (API)
- Test endpoint streams output and aggregates text:
  ```bash
  curl -X POST \
    -H "Authorization: Bearer <ADMIN_TOKEN>" \
    -H "Content-Type: application/json" \
    -d '{"message":"hello"}' \
    http://localhost:8000/api/admin/agents/<id>/test
  ```
  If MCP is disabled or unreachable, the response still returns 200 with an explanatory message rather than a 500.

## Screenshots & GIFs

### Admin Dashboard
The Servio admin dashboard provides a comprehensive overview of your voice agent system with real-time statistics and quick actions.

![Admin Dashboard](dashboard-preview.png)

**Key Features:**
- **System Overview**: View total agents, tools, built-in tools, and custom tools at a glance
- **Quick Actions**: Create new agents, manage existing agents, and add custom tools directly from the dashboard
- **Clean Interface**: Modern, responsive design with easy navigation
- **Agent Management**: Navigate between Dashboard, Agents, Online Agent monitoring, Tools, Widget configuration, and Settings

### Dtwin Transfer (expected)
- Add your screenshot or GIF demonstrating: user asks about "DTWIN" → triage transfers to "Dtwin Agent" → agent responds.
- Place files at:
  - `docs/images/dtwin-transfer.png`
  - `docs/images/dtwin-transfer.gif` (optional)

Example embed (auto-picks whichever exists):

![Dtwin transfer](docs/images/dtwin-transfer.png)

### Admin Tool Form (MCP)
![MCP tool form](.playwright-mcp/mcp-tool-form.png)

### Admin Settings Saved
![Admin settings success](.playwright-mcp/admin-settings-success.png)

### Tips to Capture a GIF
- macOS: QuickTime Player → New Screen Recording → export → convert to GIF via `ffmpeg` or an online tool.
- CLI (ffmpeg): `ffmpeg -i input.mov -vf "fps=12,scale=1200:-1:flags=lanczos" -loop 0 docs/images/dtwin-transfer.gif`

## Using the App

### Push-to-Talk Interface

The app uses a **Push-to-Talk** system for voice interaction:

1. **Start a Call**: Click the green **Call** button 🟢
2. **Push-to-Talk Button Appears**: A large blue microphone button will appear
3. **Hold to Speak**:
   - Press and hold the button (mouse/touch)
   - Button turns red 🔴 and shows "Recording..."
   - Speak your message
4. **Release to Send**:
   - Release the button
   - Audio is sent immediately to the agent
   - Button returns to blue, ready for next message
5. **End Call**: Click the red "End Call" button to finish

### Console Debugging

Open your browser's Developer Console (F12) to see real-time logs:

```
📞 Call started - Ready for Push-to-Talk
🎤 Push-to-Talk: Recording started
🛑 Push-to-Talk: Recording stopped
📤 Sending audio, length: 48000
Transferred to Stylist Agent
📞 Call ended
```

### Example Conversations

**Fashion Advice**:
```
You: [Press & hold] "What should I wear for summer?"
Stylist Agent: "I recommend breathable cotton t-shirts and linen shorts..."

You: [Press & hold] "Show me some trendy styles in Bangkok"
Stylist Agent: [Uses WebSearch] "Current trends in Bangkok include..."
```

**Order Management**:
```
You: [Press & hold] "Check my orders"
→ Transferred to Customer Support Agent
Customer Support: "You have 9 orders. The most recent is AB472..."

You: [Press & hold] "Refund order AB472"
Customer Support: [Uses submit_refund_request] "Refund processed successfully"
```

## Contributing

You are welcome to open issues or submit PRs to improve this app, however, please note that we may not review all suggestions.

## License

This project is licensed under the MIT License. See the LICENSE file for details.
