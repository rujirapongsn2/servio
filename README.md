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

This app is meant to be used as a starting point to build a conversational assistant that you can customize to your needs.

## Table of Contents

- [Multi-Agent Architecture](#multi-agent-architecture)
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

#### 1. **Triage Agent** (Main Router) 🎯
- **Role**: First point of contact that routes conversations to the appropriate specialist
- **Instructions**: "Route the user to the appropriate agent based on their request"
- **Starting Point**: Every conversation begins here
- **Can transfer to**: Softnix Sales Agent, Stylist Agent, Customer Support Agent, and any agents you create in Admin (e.g., Dtwin Agent)

**Example**:
```
You: "Hello, I need help"
Triage Agent: Greets you and waits for more context

You: "What products does Softnix offer?"
Triage Agent: → Transferred to Softnix Sales Agent
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
5. The runtime triage agent automatically includes DB-defined agents as handoffs; if you’ve created “Dtwin Agent”, the triage can route to it when users mention DTWIN

### Conversation Flow Diagram

```
                    ┌─────────────────────┐
                    │  Start Conversation │
                    │   (Triage Agent)    │
                    └──────────┬──────────┘
                               │
                        What did you say?
                               │
              ┌────────────────┼────────────────┐
              │                │                │
              ▼                ▼                ▼
      ┌───────────────┐  ┌─────────┐  ┌──────────────┐
      │ Softnix Sales │  │ Stylist │  │ Customer     │
      │    Agent      │  │ Agent   │  │ Support Agent│
      └───────┬───────┘  └────┬────┘  └──────────────┘
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
• Both specialized agents can transfer to Customer Support if needed
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

## Requirements

- OpenAI API key
  - If you're new to the OpenAI API, [sign up for an account](https://platform.openai.com/signup).
  - Follow the [Quickstart](https://platform.openai.com/docs/quickstart) to retrieve your API key.
- Node.js and npm
- `uv` installed on your system

## How to use

1. **Set the OpenAI API key:**

   2 options:

   - Set the `OPENAI_API_KEY` environment variable [globally in your system](https://platform.openai.com/docs/libraries#create-and-export-an-api-key)
   - Set the `OPENAI_API_KEY` environment variable in the project: Create a `.env` file at the root of the project and add the following line (see `.env.example` for reference):

   ```bash
   OPENAI_API_KEY=<your_api_key>
   ```

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

   ```bash
   make serve
   ```

   The app will be available at [`http://localhost:3000`](http://localhost:3000).

## Admin & Agents

### Admin Console
- URL: `http://localhost:3002/admin`
- Default login: `admin` / set via database; token stored in `localStorage` for subsequent requests.

### Dynamic Triage + DB Agents
- The backend composes a triage agent at runtime that includes agents from the database as handoffs. If you create a "Dtwin Agent" in Admin, triage can transfer to it when a user asks about DTWIN.
- Reset in-call agent state triggers rebuilding the triage with latest DB changes.

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

### Dtwin Transfer (expected)
- Add your screenshot or GIF demonstrating: user asks about “DTWIN” → triage transfers to “Dtwin Agent” → agent responds.
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
