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
- [Contributing](#contributing)
- [License](#license)

## Multi-Agent Architecture

This sample app demonstrates a **multi-agent system** where multiple AI agents work together, each specialized in different domains. Think of it like calling a customer service center with different departments!

### The Three Agents

#### 1. **Triage Agent** (Main Router) 🎯
- **Role**: First point of contact that routes conversations to the appropriate specialist
- **Instructions**: "Route the user to the appropriate agent based on their request"
- **Starting Point**: Every conversation begins here
- **Can transfer to**: Stylist Agent or Customer Support Agent

**Example**:
```
You: "Hello, I need help"
Triage Agent: Greets you and waits for more context

You: "I want to see some clothes"
Triage Agent: → Transferred to Stylist Agent
```

#### 2. **Stylist Agent** (Fashion Consultant) 👔
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

### Conversation Flow Diagram

```
┌─────────────────────┐
│  Start Conversation │
│   (Triage Agent)    │
└──────────┬──────────┘
           │
    What did you say?
           │
     ┌─────┴─────┐
     │           │
     ▼           ▼
┌─────────┐  ┌──────────────┐
│ Stylist │  │ Customer     │
│ Agent   │  │ Support Agent│
└────┬────┘  └──────────────┘
     │
     └──────────┐
                │
    (If order mentioned)
                │
                ▼
        ┌──────────────┐
        │ Customer     │
        │ Support Agent│
        └──────────────┘
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
