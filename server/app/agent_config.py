import json
import requests
import asyncio
import os
from typing import Dict, Any, List, Optional

from agents import Agent, WebSearchTool, function_tool
from agents.tool import UserLocation
import app.mock_api as mock_api
from app.softnix_api import query_softnix_genai, SoftnixAPIError

# MCP SDK imports
try:
    import httpx
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

STYLE_INSTRUCTIONS = "Use a conversational tone and write in a chat style without formal formatting or lists and do not use any emojis."


@function_tool
def get_past_orders():
    return json.dumps(mock_api.get_past_orders())


@function_tool
def submit_refund_request(order_number: str):
    """Confirm with the user first"""
    return mock_api.submit_refund_request(order_number)


@function_tool
def get_softnix_info(question: str):
    """
    Get information about Softnix products, services, or company from the Softnix GenAI knowledge base.

    Use this tool when the user asks about:
    - Softnix products or services
    - Company information
    - Pricing or packages
    - Technical specifications
    - How to use Softnix services

    Args:
        question: The user's question about Softnix

    Returns:
        Answer from Softnix GenAI knowledge base
    """
    try:
        return query_softnix_genai(question)
    except SoftnixAPIError as e:
        return f"I apologize, but I'm having trouble accessing the Softnix information system right now. Error: {str(e)}"


customer_support_agent = Agent(
    name="Customer Support Agent",
    instructions=f"You are a customer support assistant. {STYLE_INSTRUCTIONS}",
    model="gpt-4o-mini",
    tools=[get_past_orders, submit_refund_request],
)

softnix_sales_agent = Agent(
    name="Softnix Sales Agent",
    model="gpt-4o-mini",
    instructions=f"""You are a Softnix sales representative assistant.
    You help customers understand Softnix products and services by answering their questions.

    When a customer asks about Softnix products, services, pricing, or company information,
    use the get_softnix_info tool to retrieve accurate information from the knowledge base.

    Be helpful, professional, and informative. If a customer wants to place an order or
    needs customer support after purchase, you can transfer them to the Customer Support Agent.

    {STYLE_INSTRUCTIONS}""",
    tools=[get_softnix_info],
    handoffs=[customer_support_agent],
)

stylist_agent = Agent(
    name="Stylist Agent",
    model="gpt-4o-mini",
    instructions=f"You are a stylist assistant. {STYLE_INSTRUCTIONS}",
    tools=[WebSearchTool(user_location=UserLocation(type="approximate", city="Bangkok"))],
    handoffs=[customer_support_agent],
)

triage_agent = Agent(
    name="Coordinator Agent",
    model="gpt-4o-mini",
    instructions=f"""Route the user to the appropriate agent based on their request.

    Transfer to:
    - Softnix Sales Agent: Questions about Softnix products, services, or company information
    - Stylist Agent: Fashion advice, clothing recommendations, style questions
    - Customer Support Agent: Order history, refunds, purchase issues

    {STYLE_INSTRUCTIONS}""",
    handoffs=[softnix_sales_agent, stylist_agent, customer_support_agent],
)

starting_agent = triage_agent


# Dynamic agent loading from database
def get_tool_by_name(tool_name: str, tool_config: Dict[str, Any] = None):
    """Get a tool instance by name"""
    if tool_name == "get_past_orders":
        return get_past_orders
    elif tool_name == "submit_refund_request":
        return submit_refund_request
    elif tool_name == "get_softnix_info":
        return get_softnix_info
    elif tool_name == "WebSearchTool":
        location = tool_config.get("location", {"type": "approximate", "city": "Bangkok"}) if tool_config else {"type": "approximate", "city": "Bangkok"}
        return WebSearchTool(user_location=UserLocation(**location))
    elif tool_config and tool_config.get("type") == "custom_api":
        # Create a dynamic function tool for custom API
        return create_custom_api_tool(tool_name, tool_config)
    elif tool_config and tool_config.get("type") == "mcp_streamable_http":
        # Respect safe-mode: allow disabling MCP for offline/dev environments
        if os.getenv("DISABLE_MCP", "").lower() in {"1", "true", "yes"} or os.getenv(
            "AGENTS_SAFE_MODE_DISABLE_EXTERNAL", ""
        ).lower() in {"1", "true", "yes"}:
            @function_tool
            def mcp_disabled_tool(query: str):
                """MCP disabled in this environment (safe mode)."""
                return (
                    "MCP tools are disabled in this environment. "
                    "Please enable network access or unset DISABLE_MCP to use this tool."
                )

            mcp_disabled_tool.__name__ = tool_name
            mcp_disabled_tool.__doc__ = tool_config.get(
                "description", f"Call {tool_name} MCP tool"
            )
            return mcp_disabled_tool

        # Create a dynamic function tool for MCP Streamable HTTP
        return create_mcp_tool(tool_name, tool_config)
    else:
        return None


def create_custom_api_tool(tool_name: str, config: Dict[str, Any]):
    """Create a custom API tool from configuration"""
    api_endpoint = config.get("endpoint", "")
    auth_token = config.get("auth_token", "")
    method = config.get("method", "POST")
    description = config.get("description", f"Call {tool_name} API")

    @function_tool
    def custom_api_call(query: str):
        """Dynamic API tool"""
        try:
            headers = {
                "Content-Type": "application/json",
            }
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"

            payload = config.get("payload_template", {"query": query})
            if isinstance(payload, dict) and "query" in payload:
                payload["query"] = query

            if method.upper() == "POST":
                response = requests.post(api_endpoint, headers=headers, json=payload, timeout=60)
            elif method.upper() == "GET":
                response = requests.get(api_endpoint, headers=headers, params={"query": query}, timeout=60)
            else:
                return f"Unsupported HTTP method: {method}"

            response.raise_for_status()
            data = response.json()

            # Extract answer from response
            if "answer" in data:
                return data["answer"]
            elif "message" in data:
                return data["message"]
            elif "response" in data:
                return data["response"]
            else:
                return json.dumps(data, ensure_ascii=False)

        except Exception as e:
            return f"Error calling {tool_name}: {str(e)}"

    # Set the function name and docstring
    custom_api_call.__name__ = tool_name
    custom_api_call.__doc__ = description

    return custom_api_call


def create_mcp_tool(tool_name: str, config: Dict[str, Any]):
    """Create an MCP Streamable HTTP tool from configuration"""
    if not MCP_AVAILABLE:
        raise RuntimeError("MCP SDK not installed. Run: uv add mcp httpx")

    mcp_endpoint = config.get("endpoint", "")
    auth_token = config.get("auth_token", "")
    transport = config.get("transport", "streamable_http")
    description = config.get("description", f"Call {tool_name} MCP tool")
    mcp_tool_names = config.get("tools", [])  # Specific MCP tools to call

    @function_tool
    def mcp_tool_call(query: str):
        """Dynamic MCP tool - calls MCP server via Streamable HTTP"""
        try:
            # Run async MCP call in sync context
            return asyncio.run(_call_mcp_server(
                endpoint=mcp_endpoint,
                auth_token=auth_token,
                query=query,
                tool_names=mcp_tool_names
            ))
        except Exception as e:
            return f"Error calling MCP tool {tool_name}: {str(e)}"

    # Set the function name and docstring
    mcp_tool_call.__name__ = tool_name
    mcp_tool_call.__doc__ = description

    return mcp_tool_call


async def _call_mcp_server(
    endpoint: str,
    auth_token: Optional[str],
    query: str,
    tool_names: List[str]
) -> str:
    """Internal async function to call MCP server via Streamable HTTP"""
    headers = {}
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        # For Streamable HTTP transport, the endpoint is typically /mcp
        # Send a tools/list request to discover available tools
        try:
            # Initialize session by calling the MCP endpoint
            response = await client.post(
                endpoint,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {}
                }
            )
            response.raise_for_status()
            tools_response = response.json()

            # If specific tool names are provided, use them; otherwise use first available
            available_tools = tools_response.get("result", {}).get("tools", [])

            if not available_tools:
                return "No tools available from MCP server"

            # Find the first matching tool or use the first available tool
            target_tool = None
            if tool_names:
                for tool in available_tools:
                    if tool["name"] in tool_names:
                        target_tool = tool
                        break
            if not target_tool and available_tools:
                target_tool = available_tools[0]

            if not target_tool:
                return f"Requested tools not found. Available: {[t['name'] for t in available_tools]}"

            # Call the tool
            tool_response = await client.post(
                endpoint,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": target_tool["name"],
                        "arguments": {"query": query}
                    }
                }
            )
            tool_response.raise_for_status()
            result = tool_response.json()

            # Extract result from MCP response
            if "result" in result:
                content = result["result"].get("content", [])
                if content and isinstance(content, list):
                    # Combine text from all content items
                    return "\n".join([item.get("text", "") for item in content if item.get("type") == "text"])
                return json.dumps(result["result"], ensure_ascii=False)
            elif "error" in result:
                return f"MCP Error: {result['error'].get('message', 'Unknown error')}"
            else:
                return json.dumps(result, ensure_ascii=False)

        except httpx.HTTPError as e:
            return f"HTTP Error calling MCP server: {str(e)}"
        except Exception as e:
            return f"Error calling MCP server: {str(e)}"


def build_agent_from_db(agent_data: Dict[str, Any], all_agents: Dict[int, Agent] = None) -> Agent:
    """Build an Agent instance from database configuration"""
    # Get tools
    tools = []
    for tool_data in agent_data.get("tools", []):
        tool_config = json.loads(tool_data["config"]) if tool_data.get("config") else {}
        tool = get_tool_by_name(tool_data["name"], tool_config)
        if tool:
            tools.append(tool)

    # Get handoffs
    handoffs = []
    if all_agents:
        for handoff_data in agent_data.get("handoffs", []):
            handoff_agent = all_agents.get(handoff_data["id"])
            if handoff_agent:
                handoffs.append(handoff_agent)

    # Create agent
    agent = Agent(
        name=agent_data["name"],
        model=agent_data.get("model", "gpt-4o-mini"),
        instructions=agent_data["instructions"],
        tools=tools,
        handoffs=handoffs,
    )

    return agent


def load_agents_from_db():
    """Load all agents from database and return starting agent"""
    from app import database

    agents_data = database.get_all_agents()

    if not agents_data:
        # Return default agents if no database agents
        return starting_agent

    # First pass: create all agents without handoffs
    all_agents = {}
    for agent_data in agents_data:
        agent = build_agent_from_db(agent_data, all_agents=None)
        all_agents[agent_data["id"]] = agent

    # Second pass: add handoffs
    for agent_data in agents_data:
        agent = all_agents[agent_data["id"]]
        handoffs = []
        for handoff_data in agent_data.get("handoffs", []):
            handoff_agent = all_agents.get(handoff_data["id"])
            if handoff_agent:
                handoffs.append(handoff_agent)
        agent.handoffs = handoffs

    # Find starting agent
    for agent_data in agents_data:
        if agent_data.get("is_starting_agent"):
            return all_agents[agent_data["id"]]

    # If no starting agent marked, return first agent or default
    return all_agents[agents_data[0]["id"]] if all_agents else starting_agent


def get_runtime_starting_agent() -> Agent:
    """Compose a runtime starting agent (coordinator) that includes DB agents as handoffs.

    - Keeps the familiar Coordinator Agent UX
    - Dynamically appends DB-defined agents as additional handoffs
    - Augments instructions with a brief list of available agents so the
      model learns routing options (helps it pick Dtwin Agent when asked)
    """
    from app import database

    # Build DB agents (if any)
    db_agents_data = database.get_all_agents()
    db_agents: list[Agent] = []
    for a in db_agents_data:
        try:
            db_agents.append(build_agent_from_db(a))
        except Exception:
            # If a DB tool misconfig fails (e.g., MCP offline), skip but keep triage usable
            continue

    # Base triage
    base_handoffs = [softnix_sales_agent, stylist_agent, customer_support_agent]
    combined_handoffs = base_handoffs + db_agents

    # Enrich instructions with dynamic agent list (names only to avoid long prompts)
    extra = "\n\nAdditional agents available for transfer: "
    if db_agents_data:
        names = ", ".join([a["name"] for a in db_agents_data])
        extra += names + "."
    else:
        extra += "None."

    # Add explicit routing hint for Dtwin if present
    for a in db_agents_data:
        name = a.get("name", "").lower()
        if "dtwin" in name:
            extra += (
                "\nIf the user mentions DTWIN (e.g., 'DTWIN', 'ดีทวิน'), "
                "transfer to the Dtwin Agent."
            )
            break

    triage = Agent(
        name="Coordinator Agent",
        model=triage_agent.model,
        instructions=triage_agent.instructions + extra,
        handoffs=combined_handoffs,
    )
    return triage
