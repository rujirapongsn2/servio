from fastapi import APIRouter, Depends, HTTPException, status
import json
from typing import List

from app import database
from app.auth import get_current_user, verify_password, create_access_token
from app.models import (
    LoginRequest,
    LoginResponse,
    ChangePasswordRequest,
    AgentResponse,
    CreateAgentRequest,
    UpdateAgentRequest,
    TestAgentRequest,
    TestAgentResponse,
    ToolResponse,
    CreateCustomToolRequest,
    UpdateCustomToolRequest,
    OptimizePromptRequest,
    OptimizePromptResponse,
    MessageResponse,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# Authentication endpoints
@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Login endpoint that returns JWT token"""
    admin = database.get_admin_by_username(request.username)

    if not admin or not verify_password(request.password, admin["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(data={"sub": request.username})
    return LoginResponse(
        access_token=access_token,
        username=request.username
    )


@router.post("/auth/change-password", response_model=MessageResponse)
async def change_password(
    request: ChangePasswordRequest,
    current_user: str = Depends(get_current_user)
):
    """Change password for current user"""
    admin = database.get_admin_by_username(current_user)

    if not admin or not verify_password(request.current_password, admin["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect"
        )

    success = database.update_admin_password(current_user, request.new_password)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update password"
        )

    return MessageResponse(message="Password changed successfully")


# Agent endpoints
@router.get("/agents", response_model=List[AgentResponse])
async def get_agents(current_user: str = Depends(get_current_user)):
    """Get all agents"""
    agents = database.get_all_agents()
    return agents


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: int, current_user: str = Depends(get_current_user)):
    """Get a single agent by ID"""
    agent = database.get_agent_by_id(agent_id)

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )

    return agent


@router.post("/agents", response_model=MessageResponse)
async def create_agent(
    request: CreateAgentRequest,
    current_user: str = Depends(get_current_user)
):
    """Create a new agent"""
    try:
        agent_id = database.create_agent(
            name=request.name,
            instructions=request.instructions,
            model=request.model,
            tool_ids=request.tool_ids,
            handoff_agent_ids=request.handoff_agent_ids,
            is_starting_agent=request.is_starting_agent
        )
        return MessageResponse(message=f"Agent created successfully with ID {agent_id}")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create agent: {str(e)}"
        )


@router.put("/agents/{agent_id}", response_model=MessageResponse)
async def update_agent(
    agent_id: int,
    request: UpdateAgentRequest,
    current_user: str = Depends(get_current_user)
):
    """Update an existing agent"""
    success = database.update_agent(
        agent_id=agent_id,
        name=request.name,
        instructions=request.instructions,
        model=request.model,
        tool_ids=request.tool_ids,
        handoff_agent_ids=request.handoff_agent_ids,
        is_starting_agent=request.is_starting_agent
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )

    return MessageResponse(message="Agent updated successfully")


@router.delete("/agents/{agent_id}", response_model=MessageResponse)
async def delete_agent(
    agent_id: int,
    current_user: str = Depends(get_current_user)
):
    """Delete an agent"""
    success = database.delete_agent(agent_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )

    return MessageResponse(message="Agent deleted successfully")


@router.post("/agents/{agent_id}/test", response_model=TestAgentResponse)
async def test_agent(
    agent_id: int,
    request: TestAgentRequest,
    current_user: str = Depends(get_current_user)
):
    """Test an agent with a sample message (streaming aggregation)."""
    from agents import Runner
    from app.agent_config import (
        build_agent_from_db,
        start_tool_logging,
        get_tool_log,
        get_tool_citations,
        get_tool_by_name,
    )
    from app.utils import is_text_output

    agent_data = database.get_agent_by_id(agent_id)

    if not agent_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )

    try:
        # Build agent from database configuration
        agent = build_agent_from_db(agent_data)

        # If force_tool provided, limit tools and prime instructions/message
        user_message = request.message
        if request.force_tool and request.force_tool.name:
            forced_name = request.force_tool.name

            # Try to find existing tool instance on the agent
            forced_tool = None
            for t in getattr(agent, 'tools', []) or []:
                tname = getattr(t, 'name', getattr(t, '__name__', None))
                if tname == forced_name:
                    forced_tool = t
                    break

            # If not present, try to construct tool by name from DB config
            if forced_tool is None:
                for t in agent_data.get("tools", []):
                    if t.get("name") == forced_name:
                        tconfig = json.loads(t.get("config")) if t.get("config") else {}
                        forced_tool = get_tool_by_name(forced_name, tconfig)
                        break

            if forced_tool is not None:
                # Restrict to the forced tool only for this test
                agent.tools = [forced_tool]

            # Prime instructions hard requirement for this test
            args = request.force_tool.arguments or {}
            args_str = json.dumps(args, ensure_ascii=False)
            agent.instructions = (
                "[TEST ONLY] You MUST call the tool '" + forced_name +
                "' exactly once using arguments: " + args_str + ". "
                "If the tool is unavailable or fails, explain the error. "
            ) + "\n\n" + agent.instructions

            # Also hint in the user's message to bias the model
            user_message = (
                request.message
                + f"\n\n[TEST HINT] Use tool '{forced_name}' with arguments: {args_str}"
            )

        # Stream the agent response and aggregate text
        response_text = ""
        tool_calls = []
        citation_tools: list[str] = []
        tool_outputs: list[dict] = []

        # Start per-request tool logging so dynamic tools can log invocations
        start_tool_logging()

        output = Runner.run_streamed(
            agent,
            [{"role": "user", "content": user_message}],
        )

        def _stringify(val):
            try:
                if isinstance(val, (dict, list)):
                    import json as _json
                    return _json.dumps(val, ensure_ascii=False)
            except Exception:
                pass
            return str(val)

        async for event in output.stream_events():
            if is_text_output(event):
                response_text += event.data.delta  # type: ignore[attr-defined]
            # Track tool calls and outputs from RunItemStreamEvent
            elif hasattr(event, 'item'):
                it = event.item
                etype = getattr(it, 'type', '') or ''
                # function call events
                if etype in {'function_call', 'function_tool_call', 'tool_call', 'function'}:
                    name = getattr(it, 'name', 'unknown')
                    args = getattr(it, 'arguments', {})
                    try:
                        # arguments may be JSON string in some versions
                        if isinstance(args, str):
                            import json as _json
                            args = _json.loads(args)
                    except Exception:
                        pass
                    tool_calls.append({'name': name, 'arguments': args})
                    if name and name not in citation_tools:
                        citation_tools.append(name)

                # function/tool output events — capture for structured display
                if ('output' in etype) or (etype in {'function_output', 'function_call_output', 'tool_result'}):
                    name = getattr(it, 'name', None) or getattr(it, 'tool_name', None) or ''
                    out = getattr(it, 'output', None) or getattr(it, 'content', None) or getattr(it, 'result', None)
                    if isinstance(out, list):
                        try:
                            texts = []
                            for x in out:
                                if isinstance(x, dict) and x.get('type') == 'text' and 'text' in x:
                                    texts.append(str(x['text']))
                            if texts:
                                out = '\n'.join(texts)
                        except Exception:
                            pass
                    tool_outputs.append({'name': name, 'output': out})

        # Merge SDK-detected tool calls with explicit logs from tools
        logged_calls = get_tool_log()
        if logged_calls:
            for c in logged_calls:
                name = c.get('name')
                args = c.get('arguments', {})
                if name and not any(tc.get('name') == name and tc.get('arguments') == args for tc in tool_calls):
                    tool_calls.append({'name': name, 'arguments': args})

        citations = citation_tools or get_tool_citations()

        return TestAgentResponse(
            response=response_text or "No response",
            tool_calls=tool_calls,
            citations=citations,
            tool_outputs=tool_outputs,
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test agent: {str(e)}"
        )


@router.post("/agents/optimize-prompt", response_model=OptimizePromptResponse)
async def optimize_prompt(
    request: OptimizePromptRequest,
    current_user: str = Depends(get_current_user)
):
    """Optimize agent instructions using AI"""
    import os
    from openai import OpenAI

    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Construct the optimization prompt
        system_prompt = """You are an expert at writing agent instructions for conversational AI systems.
Your task is to improve and optimize agent instructions to make them clear, actionable, and effective.

Guidelines for optimization:
1. Be specific and clear about the agent's role and capabilities
2. Use action-oriented language
3. Structure instructions logically
4. Include guidelines for tone and style
5. Specify when to use tools if applicable
6. Add error handling guidance
7. Keep instructions concise but comprehensive
8. Use bullet points or numbered lists for clarity
9. Avoid unnecessary jargon
10. Ensure the agent knows how to handle edge cases

Return only the optimized instructions without any additional commentary or explanation."""

        user_prompt = f"""Optimize these agent instructions:

Current Instructions:
{request.instructions}

Provide optimized instructions that are clear, actionable, and follow best practices for conversational AI agents."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
        )

        optimized = response.choices[0].message.content.strip()

        return OptimizePromptResponse(optimized_instructions=optimized)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to optimize prompt: {str(e)}"
        )


# Tool endpoints
@router.get("/tools", response_model=List[ToolResponse])
async def get_tools(current_user: str = Depends(get_current_user)):
    """Get all available tools"""
    tools = database.get_all_tools()
    return tools


@router.get("/tools/{tool_id}", response_model=ToolResponse)
async def get_tool(tool_id: int, current_user: str = Depends(get_current_user)):
    """Get a single tool by ID"""
    tool = database.get_tool_by_id(tool_id)

    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool not found"
        )

    return tool


@router.post("/tools", response_model=MessageResponse)
async def create_tool(
    request: CreateCustomToolRequest,
    current_user: str = Depends(get_current_user)
):
    """Create a custom API tool"""
    try:
        tool_id = database.create_custom_tool(request.name, request.config, request.icon)
        return MessageResponse(message=f"Tool created successfully with ID {tool_id}")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create tool: {str(e)}"
        )


@router.put("/tools/{tool_id}", response_model=MessageResponse)
async def update_tool(
    tool_id: int,
    request: UpdateCustomToolRequest,
    current_user: str = Depends(get_current_user)
):
    """Update a custom API tool"""
    success = database.update_custom_tool(tool_id, request.name, request.config, request.icon)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool not found or is not a custom tool"
        )

    return MessageResponse(message="Tool updated successfully")


@router.delete("/tools/{tool_id}", response_model=MessageResponse)
async def delete_tool(
    tool_id: int,
    current_user: str = Depends(get_current_user)
):
    """Delete a custom API tool"""
    success = database.delete_custom_tool(tool_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool not found or is not a custom tool"
        )

    return MessageResponse(message="Tool deleted successfully")
