# Voice Agents SDK Sample App

[![MIT License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
![FastAPI](https://img.shields.io/badge/Built_with-FastAPI-yellow)
![NextJS](https://img.shields.io/badge/Built_with-NextJS-blue)
![OpenAI API](https://img.shields.io/badge/Powered_by-OpenAI_API-orange)

This repository contains a sample app to highlight how to build [voice agents](https://platform.openai.com/docs/guides/voice-agents) using the [Agents SDK](https://openai.github.io/openai-agents-python) and Python. The backend is written using FastAPI and exposes a websocket endpoint. The front-end is written using Next.js and connects to the websocket server.

Features:

- **Multi-turn conversation handling** - Continuous back-and-forth conversations
- **Push-to-Talk audio mode** - Press and hold to speak, release to send
- **Multi-agent system** - Specialized AI agents that work together and transfer conversations
- **Function calling** - Agents can use tools (web search, database queries, etc.)
- **Streaming responses** - Real-time text and audio streaming
- **File Store Agents** - Document search and retrieval using Gemini File Search API

This app is meant to be used as a starting point to build a conversational assistant that you can customize to your needs.

## Table of Contents

- [Multi-Agent Architecture](#multi-agent-architecture)
- [File Store Agents](#file-store-agents)
- [Requirements](#requirements)
- [How to use](#how-to-use)
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
  - Location: Tokyo (can find local stores and trends)
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

1. **Set the API keys:**

   Create a `.env` file at the root of the project (see `.env.example` for reference):

   ```bash
   # Required: OpenAI API key for voice agents
   OPENAI_API_KEY=<your_openai_api_key>

   # Optional: Gemini API key for File Store Agents
   GEMINI_API_KEY=<your_gemini_api_key>
   ```

   Alternatively, you can set the `OPENAI_API_KEY` environment variable [globally in your system](https://platform.openai.com/docs/libraries#create-and-export-an-api-key).

2. **Clone the Repository:**

   ```bash
   git clone https://github.com/openai/openai-voice-agent-sdk-sample.git
   cd openai-voice-agent-sdk-sample/ 
   ```

3. **Install dependencies:**

   You will have to install both the dependencies for the front-end and the server. To do this run in the project root:

   ```bash
   make sync
   ```

4. **Run the app:**

   You have multiple options to start the application:

   **Option 1: Quick Start (Recommended)**
   ```bash
   ./start.sh
   ```
   This will start both frontend and backend in development mode with hot reload.

   **Option 2: Using Make (Production Mode)**
   ```bash
   make serve
   ```
   Starts the app in production mode at [`http://localhost:3000`](http://localhost:3000).

   **Option 3: Development Mode with Hot Reload**
   ```bash
   cd frontend && npm run dev
   ```
   - Frontend: [`http://localhost:3001`](http://localhost:3001) (or next available port)
   - Backend: [`http://localhost:8000`](http://localhost:8000)
   - WebSocket: `ws://localhost:8000/ws`

   **Option 4: Run Separately**
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

You: [Press & hold] "Show me some trendy styles in Tokyo"
Stylist Agent: [Uses WebSearch] "Current trends in Tokyo include..."
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
