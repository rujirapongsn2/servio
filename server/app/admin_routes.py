from fastapi import APIRouter, Depends, HTTPException, status
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
    from app.agent_config import build_agent_from_db
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

        # Stream the agent response and aggregate text
        response_text = ""
        tool_calls = []

        output = Runner.run_streamed(
            agent,
            [{"role": "user", "content": request.message}],
        )

        async for event in output.stream_events():
            if is_text_output(event):
                response_text += event.data.delta  # type: ignore[attr-defined]
            # Track tool calls from RunItemStreamEvent
            elif hasattr(event, 'item') and hasattr(event.item, 'type'):
                if event.item.type == 'function_call':
                    tool_calls.append({
                        'name': event.item.name if hasattr(event.item, 'name') else 'unknown',
                        'arguments': event.item.arguments if hasattr(event.item, 'arguments') else {}
                    })

        return TestAgentResponse(response=response_text or "No response", tool_calls=tool_calls)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test agent: {str(e)}"
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
        tool_id = database.create_custom_tool(request.name, request.config)
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
    success = database.update_custom_tool(tool_id, request.name, request.config)

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
