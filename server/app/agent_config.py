import json
import requests
import asyncio
import os
from typing import Dict, Any, List, Optional
from contextvars import ContextVar
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

from openai import AsyncOpenAI
from agents import Agent, WebSearchTool, function_tool, OpenAIChatCompletionsModel
from agents.tool import UserLocation
from app.softnix_api import query_softnix_genai, SoftnixAPIError

# MCP SDK imports
try:
    import httpx
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

STYLE_INSTRUCTIONS = (
    "You are a Voice AI assistant. Your responses will be spoken out loud, so they must be:"
    "\n1. Extremely concise and short (1-2 sentences max unless explained)."
    "\n2. Respond in the same language as the user (e.g., if the user speaks English, respond in English; if Thai, respond in Thai; if Chinese, respond in Chinese)."
    "\n3. Do not use special characters, markdown, lists, or emojis."
    "\n4. If the user input is unclear, completely random foreign words, or noise, IGNORE it or politely ask them to repeat in their language."
    "\n5. Do not switch languages mid-sentence."
)

"""\nLightweight tool-call logging for test runs.\n- Uses ContextVar to isolate per-request logs.\n- Admin test endpoint should call start_tool_logging() before running.\n"""
_tool_log: ContextVar[list] = ContextVar("tool_log", default=[])

def start_tool_logging():
    _tool_log.set([])

def log_tool_call(name: str, arguments: dict | None = None):
    try:
        entries = list(_tool_log.get())
        entries.append({"name": name, "arguments": arguments or {}})
        _tool_log.set(entries)
    except Exception:
        pass

def get_tool_log() -> List[Dict[str, Any]]:
    try:
        return list(_tool_log.get())
    except Exception:
        return []

def get_tool_citations() -> List[str]:
    seen = set()
    citations: List[str] = []
    for entry in get_tool_log():
        name = entry.get("name")
        if name and name not in seen:
            citations.append(name)
            seen.add(name)
    return citations


triage_agent = Agent(
    name="Coordinator Agent",
    model="gpt-4o-mini",
    instructions=f"""You are the coordinator for all conversations.
- Greet the user and handle their request directly.
- If specialized agents exist in the database, transfer to the best match immediately without any preamble, confirmation, or speaking to the user.
- When no specialized agents are available, do your best to answer yourself.
- IMPORTANT: You are a Voice Bot. Keep your answers very short, punchy, and to the point.
- LANGUAGE: Always match the user's language. If they speak English, respond in English. If they speak Thai, respond in Thai. If they speak Chinese, respond in Chinese.
{STYLE_INSTRUCTIONS}""",
    handoffs=[],
)

starting_agent = triage_agent


# Dynamic agent loading from database
def get_tool_by_name(tool_name: str, tool_config: Dict[str, Any] = None):
    """Get a tool instance by name"""
    if tool_name == "WebSearchTool":
        location = tool_config.get("location", {"type": "approximate", "city": "Bangkok"}) if tool_config else {"type": "approximate", "city": "Bangkok"}
        return WebSearchTool(user_location=UserLocation(**location))
    elif tool_config and tool_config.get("type") == "custom_api":
        # Check if this is a Softnix API tool
        if tool_name == "get_softnix_info" or tool_config.get("api_type") == "softnix":
            return create_softnix_tool(tool_name, tool_config)
        # Otherwise, create a generic custom API tool
        return create_custom_api_tool(tool_name, tool_config)
    elif tool_config and tool_config.get("type") == "gemini_file_search":
        # Create a dynamic function tool for Gemini File Search
        return create_gemini_file_search_tool(tool_name, tool_config)
    elif tool_config and tool_config.get("type") == "mcp_streamable_http":
        # Respect safe-mode: allow disabling MCP for offline/dev environments
        if os.getenv("DISABLE_MCP", "").lower() in {"1", "true", "yes"} or os.getenv(
            "AGENTS_SAFE_MODE_DISABLE_EXTERNAL", ""
        ).lower() in {"1", "true", "yes"}:
            @function_tool
            def mcp_disabled_tool(query: str):
                """MCP disabled in this environment (safe mode)."""
                log_tool_call(tool_name, {"query": query, "disabled": True})
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
    # Per-tool timeout with env fallback
    timeout_s = int(config.get("timeout_seconds", int(os.getenv("TOOL_TIMEOUT_SECONDS", "60"))))

    def _extract_preferred_text(data: Any) -> Optional[str]:
        try:
            if isinstance(data, dict):
                for k in ["answer", "message", "response", "result", "text", "content"]:
                    v = data.get(k)
                    if isinstance(v, (str, int, float)) and str(v).strip():
                        return str(v)
                if isinstance(data.get("data"), dict):
                    dd = data["data"]
                    for k in ["result", "text", "message", "response"]:
                        v = dd.get(k)
                        if isinstance(v, (str, int, float)) and str(v).strip():
                            return str(v)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, (str, int, float)):
                        return str(item)
        except Exception:
            pass
        return None

    # Create the function dynamically
    def dynamic_tool_func(query: str):
        """Dynamic API tool"""
        try:
            log_tool_call(tool_name, {"query": query})
            headers = {
                "Content-Type": "application/json",
            }
            if auth_token:
                if auth_token.lower().startswith("bearer "):
                    headers["Authorization"] = auth_token
                else:
                    headers["Authorization"] = f"Bearer {auth_token}"

            # Clone the payload template and substitute query
            payload = json.loads(json.dumps(config.get("payload_template", {"query": query})))
            if isinstance(payload, dict):
                if "query" in payload:
                    payload["query"] = query
                # For compatibility, also try common variations
                elif "message" in payload:
                    payload["message"] = query
                elif "text" in payload:
                    payload["text"] = query
                elif "input" in payload:
                    payload["input"] = query
            else:
                # If not a dict, wrap it
                payload = {"query": query}

            if method.upper() == "POST":
                response = requests.post(api_endpoint, headers=headers, json=payload, timeout=timeout_s)
            elif method.upper() == "GET":
                response = requests.get(api_endpoint, headers=headers, params={"query": query}, timeout=timeout_s)
            else:
                return f"Unsupported HTTP method: {method}"

            response.raise_for_status()
            data = response.json()

            # Extract answer from response (handle Tavily-style responses)
            if "answer" in data and "results" in data:
                # Tavily-style response with answer and results
                result_parts = []
                if data.get("answer"):
                    result_parts.append(f"Answer: {data['answer']}\n")

                if data.get("results"):
                    result_parts.append("Sources:")
                    for idx, result in enumerate(data["results"][:3], 1):
                        title = result.get("title", "")
                        content = result.get("content", "")
                        url = result.get("url", "")
                        result_parts.append(f"\n{idx}. {title}")
                        result_parts.append(f"   {content}")
                        result_parts.append(f"   URL: {url}")

                return "\n".join(result_parts) if result_parts else "No results found."
            # Try to derive a concise text from common response shapes (helps n8n)
            preferred = _extract_preferred_text(data)
            if preferred is not None:
                return preferred

            return json.dumps(data, ensure_ascii=False)

        except Exception as e:
            return f"Error calling {tool_name}: {str(e)}"

    # Set the function name and docstring BEFORE applying decorator
    dynamic_tool_func.__name__ = tool_name
    dynamic_tool_func.__doc__ = description

    # Apply the decorator
    return function_tool(dynamic_tool_func)


def create_gemini_file_search_tool(tool_name: str, config: Dict[str, Any]):
    """Create a Gemini File Search tool from configuration"""
    from app.gemini_service import GeminiFileSearchService

    gemini_store_id = config.get("gemini_store_id", "")
    description = config.get("description", f"Search documents using {tool_name}")
    model = config.get("model", "gemini-2.5-flash")

    # Create the function dynamically
    def dynamic_gemini_tool(query: str):
        """Search documents in Gemini file store"""
        try:
            log_tool_call(tool_name, {"query": query})

            # Initialize Gemini service
            service = GeminiFileSearchService(model=model)

            # Query the file store
            result = service.query(store_id=gemini_store_id, query=query)

            # Format response with sources
            response_text = result.get("response", "No response generated")
            sources = result.get("grounding_sources", [])

            if sources:
                response_text += "\n\nSources:\n" + "\n".join(f"- {source}" for source in sources)

            return response_text

        except Exception as e:
            return f"Error searching documents: {str(e)}"

    # Set the function name and docstring BEFORE applying decorator
    dynamic_gemini_tool.__name__ = tool_name
    dynamic_gemini_tool.__doc__ = description

    # Apply the decorator
    return function_tool(dynamic_gemini_tool)


def create_softnix_tool(tool_name: str, config: Dict[str, Any]):
    """Create a Softnix GenAI tool with Thai language enrichment"""
    description = config.get("description", "Get information about Softnix products and services")

    def dynamic_softnix_tool(question: str):
        """Query Softnix GenAI knowledge base with Thai language support"""
        try:
            log_tool_call(tool_name, {"question": question})
            q = question.strip()

            # Thai language detection and enrichment
            contains_thai = any('\u0e00' <= ch <= '\u0e7f' for ch in q)

            enriched_q = q
            if contains_thai and "softnix" not in q.lower():
                # Add canonical English brand keyword to help KB retrieval
                enriched_q = f"{q} (Softnix)"

            if contains_thai:
                # Add polite language instruction for Thai responses
                enriched_q = f"กรุณาตอบเป็นภาษาไทย: {enriched_q}"

            return query_softnix_genai(enriched_q)
        except SoftnixAPIError as e:
            return f"I apologize, but I'm having trouble accessing the Softnix information system right now. Error: {str(e)}"

    # Set function name and docstring BEFORE applying decorator
    dynamic_softnix_tool.__name__ = tool_name
    dynamic_softnix_tool.__doc__ = description

    # Apply the decorator
    return function_tool(dynamic_softnix_tool)


def create_mcp_tool(tool_name: str, config: Dict[str, Any]):
    """Create an MCP Streamable HTTP tool from configuration"""
    if not MCP_AVAILABLE:
        raise RuntimeError("MCP SDK not installed. Run: uv add mcp httpx")

    mcp_endpoint = config.get("endpoint", "")
    auth_token = config.get("auth_token", "")
    transport = config.get("transport", "streamable_http")
    # Remote MCP auth support (bearer|query|header)
    auth_mode = config.get("auth_mode", "bearer")
    auth_param_name = config.get("auth_param_name", "apikey")
    auth_header_name = config.get("auth_header_name", "X-API-Key")
    description = config.get("description", f"Call {tool_name} MCP tool")
    mcp_tool_names = config.get("tools", [])  # Specific MCP tools to call
    timeout_s = int(config.get("timeout_seconds", int(os.getenv("TOOL_TIMEOUT_SECONDS", "60"))))

    @function_tool
    def mcp_tool_call(query: str):
        """Dynamic MCP tool - calls MCP server via Streamable HTTP"""
        try:
            log_tool_call(tool_name, {"query": query})
            # Run async MCP call in sync context
            return asyncio.run(_call_mcp_server(
                endpoint=mcp_endpoint,
                auth_token=auth_token,
                auth_mode=auth_mode,
                auth_param_name=auth_param_name,
                auth_header_name=auth_header_name,
                timeout_s=timeout_s,
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
    auth_mode: str,
    auth_param_name: str,
    auth_header_name: str,
    timeout_s: int,
    query: str,
    tool_names: List[str]
) -> str:
    """Internal async function to call MCP server via Streamable HTTP.

    Supports remote MCP with flexible auth:
    - bearer: Authorization: Bearer <token>
    - query: append ?<param>=<token>
    - header: <Header-Name>: <token>
    """
    headers: Dict[str, str] = {}
    request_endpoint = endpoint
    if auth_token:
        mode = (auth_mode or "bearer").lower()
        if mode == "bearer":
            headers["Authorization"] = f"Bearer {auth_token}"
        elif mode == "header":
            # Custom header (e.g., X-API-Key)
            headers[auth_header_name or "X-API-Key"] = auth_token
        elif mode == "query":
            # Append token as query parameter (e.g., ?apikey=...)
            try:
                parsed = urlparse(endpoint)
                q = parse_qs(parsed.query, keep_blank_values=True)
                # Only add if not already present in URL
                if auth_param_name and auth_param_name not in q:
                    q[auth_param_name] = [auth_token]
                    new_query = urlencode(q, doseq=True)
                    request_endpoint = urlunparse(
                        (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
                    )
            except Exception:
                # If URL parsing fails, fall back to header
                headers["Authorization"] = f"Bearer {auth_token}"

    async with httpx.AsyncClient(timeout=timeout_s) as client:
        # For Streamable HTTP transport, the endpoint is typically /mcp
        # Send a tools/list request to discover available tools
        try:
            # Initialize session by calling the MCP endpoint
            response = await client.post(
                request_endpoint,
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

            # If server requires initialization, try initialize then retry list
            if isinstance(tools_response, dict) and tools_response.get("error"):
                try:
                    await client.post(
                        request_endpoint,
                        headers=headers,
                        json={
                            "jsonrpc": "2.0",
                            "id": 0,
                            "method": "initialize",
                            "params": {
                                "protocolVersion": "2024-11-05",
                                "capabilities": {}
                            }
                        }
                    )
                    # retry tools/list
                    response = await client.post(
                        request_endpoint,
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
                except Exception:
                    # Keep original error handling below
                    pass

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

            # Build arguments according to tool's inputSchema when available
            arguments: Dict[str, Any] = _build_mcp_arguments(query, target_tool)

            # Call the tool
            tool_response = await client.post(
                request_endpoint,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": target_tool["name"],
                        "arguments": arguments
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


def _build_mcp_arguments(query: str, tool: Dict[str, Any]) -> Dict[str, Any]:
    """Build MCP tool call arguments from a single string `query`.

    Heuristics:
    - If `query` parses as JSON object, use it directly.
    - If tool.inputSchema has a single required or single property, map to that key.
    - Prefer well-known keys: query, text, input, prompt, symbol, q.
    - Support simple `key=value` pairs separated by commas/whitespace.
    Fallback to {"query": query}.
    """
    # 1) Try JSON object payload
    try:
        obj = json.loads(query)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    schema = tool.get("inputSchema") if isinstance(tool, dict) else None
    props = None
    required = None
    if isinstance(schema, dict) and schema.get("type") == "object":
        props = schema.get("properties") or {}
        required = schema.get("required") or []

    # 2) Try to parse key=value pairs (e.g., "symbol=AAPL, interval=1min")
    kv: Dict[str, Any] = {}
    if "=" in query:
        # split by comma or whitespace
        parts = [p.strip() for p in query.replace("\n", ",").split(",") if p.strip()]
        for part in parts:
            if "=" in part:
                k, v = part.split("=", 1)
                if k.strip():
                    kv[k.strip()] = v.strip()
        if kv:
            return kv

    # 3) Prefer well-known keys present in schema
    preferred_keys = ["query", "text", "input", "prompt", "symbol", "q"]
    if isinstance(props, dict):
        for key in preferred_keys:
            if key in props:
                return {key: query}

        # If exactly one required key, map to it
        if isinstance(required, list) and len(required) == 1 and required[0] in props:
            return {required[0]: query}

        # If exactly one property overall, map to it
        if len(props) == 1:
            only_key = next(iter(props.keys()))
            return {only_key: query}

    # 4) Fallback
    return {"query": query}


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

    # Configure Model
    model = agent_data.get("model", "gpt-4o-mini")
    
    # Configure custom LLM provider if set
    llm_provider = agent_data.get("llm_provider")
    if llm_provider and llm_provider.get("base_url") and llm_provider.get("api_key"):
        try:
            client = AsyncOpenAI(
                base_url=llm_provider["base_url"],
                api_key=llm_provider["api_key"]
            )
            # Create model instance with custom client
            model = OpenAIChatCompletionsModel(
                model=model,
                openai_client=client
            )
        except Exception as e:
            print(f"Error configuring LLM provider for agent {agent_data['name']}: {e}")
            # Fallback to default model string

    # Create agent
    agent = Agent(
        name=agent_data["name"],
        model=model,
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

    # Base triage (no built-in handoffs; wait for DB-defined agents)
    combined_handoffs = db_agents

    # Enrich instructions with dynamic agent list and routing hints
    extra = "\n\nAdditional agents available for transfer:"
    if db_agents_data:
        for a in db_agents_data:
            agent_name = a.get("name", "")
            agent_instructions = a.get("instructions", "")
            extra += f"\n- {agent_name}: {agent_instructions[:150]}"
    else:
        extra += " None yet. Handle requests yourself until admins add more agents."

    # Add explicit routing hint for specific agents
    for a in db_agents_data:
        name = a.get("name", "").lower()
        if "dtwin" in name or "ดีทวิน" in name.lower():
            extra += (
                "\n\nIf the user mentions DTWIN (e.g., 'DTWIN', 'ดีทวิน'), "
                "transfer to the Dtwin Agent."
            )
        elif "it" in name or "ไอที" in name.lower():
            extra += (
                "\n\nIf the user asks about IT problems, system issues, technical support, "
                "or needs help with IT systems (e.g., 'IT', 'ไอที', 'ปัญหาระบบ'), "
                "transfer to the IT Agent."
            )

    triage = Agent(
        name="Coordinator Agent",
        model=triage_agent.model,
        instructions=triage_agent.instructions + extra,
        handoffs=combined_handoffs,
    )
    return triage
