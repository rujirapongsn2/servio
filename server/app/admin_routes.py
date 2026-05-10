from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Response
import json
import os
import re
import time
from typing import List, Optional
from pathlib import Path

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
    SystemInfoResponse,
    FileStoreResponse,
    FileStoreFileResponse,
    CreateFileStoreRequest,
    TestFileStoreRequest,
    TestFileStoreResponse,
    VoIPProviderResponse,
    CreateVoIPProviderRequest,
    UpdateVoIPProviderRequest,
    ChannelConfigResponse,
    UpdateChannelConfigRequest,
    ApiKeyResponse,
    CreateApiKeyRequest,
    UpdateApiKeyRequest,
    LLMProviderResponse,
    CreateLLMProviderRequest,
    UpdateLLMProviderRequest,
    IntentRuleResponse,
    CreateIntentRuleRequest,
    UpdateIntentRuleRequest,
    IntentGroupResponse,
    TeamAgentResponse,
    TeamAgentListResponse,
    CreateTeamAgentRequest,
    UpdateTeamAgentRequest,
    UpdateTeamMembersRequest,
    AdminUserResponse,
    CreateAdminUserRequest,
    UpdateAdminUserRequest,
    UpdateTeamUsersRequest,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def require_team_access(current_user: str, team_agent_id: Optional[int], min_role: str = "viewer") -> None:
    if team_agent_id is not None and not database.has_team_access(current_user, team_agent_id, min_role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this Team Agent",
        )


def require_super_admin(current_user: str) -> None:
    admin = database.get_admin_by_username(current_user)
    if not admin or not admin.get("is_super_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can perform this action",
        )


def require_user_management_access(current_user: str) -> None:
    if not database.can_manage_users(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage users",
        )


def require_team_admin_scope_access(current_user: str) -> None:
    """
    Allow super admin or users with team role >= admin on at least one team.
    Use this for admin-scope features that are not user-management.
    """
    if not database.has_any_team_role(current_user, "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this admin feature",
        )


def sanitize_tool_name(name: str) -> str:
    """
    Sanitize a tool name to meet OpenAI API requirements.

    OpenAI requires tool names to match pattern: ^[a-zA-Z0-9_-]+$
    This function:
    1. Removes all non-ASCII characters
    2. Replaces spaces with underscores
    3. Keeps only letters, numbers, underscores, and hyphens
    4. Ensures the name is not empty (uses 'tool' as fallback)
    """
    # Remove non-ASCII characters
    ascii_name = name.encode('ascii', 'ignore').decode('ascii')

    # Replace spaces with underscores
    ascii_name = ascii_name.replace(' ', '_')

    # Keep only valid characters: a-z, A-Z, 0-9, _, -
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', ascii_name)

    # If name is empty after sanitization, use a default
    if not sanitized:
        sanitized = 'file_store_tool'

    return sanitized


# Authentication endpoints
@router.options("/auth/login")
async def login_options():
    """Handle CORS preflight for login endpoint"""
    return Response(status_code=200)

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

    access_token = create_access_token(data={
        "sub": request.username,
        "is_super_admin": admin.get("is_super_admin", False),
    })
    return LoginResponse(
        access_token=access_token,
        username=request.username,
        is_super_admin=admin.get("is_super_admin", False),
        is_operator_only=database.is_operator_only_user(request.username),
        can_manage_users=database.can_manage_users(request.username),
    )


@router.get("/auth/me")
async def get_current_user_info(current_user: str = Depends(get_current_user)):
    """Return current user info from JWT"""
    admin = database.get_admin_by_username(current_user)
    return {
        "username": current_user,
        "is_super_admin": admin.get("is_super_admin", False) if admin else False,
        "is_operator_only": database.is_operator_only_user(current_user),
        "can_manage_users": database.can_manage_users(current_user),
    }


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


# Intent Rule endpoints
@router.get("/intent-rules", response_model=List[IntentRuleResponse])
async def get_intent_rules(current_user: str = Depends(get_current_user)):
    """Get all intent detection rules"""
    require_user_management_access(current_user)
    return database.get_all_intent_rules()

@router.post("/intent-rules", response_model=IntentRuleResponse)
async def create_intent_rule(
    request: CreateIntentRuleRequest,
    current_user: str = Depends(get_current_user)
):
    """Create a new intent rule"""
    require_user_management_access(current_user)
    try:
        rule = database.create_intent_rule(request.dict())
        return rule
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.put("/intent-rules/{rule_id}", response_model=IntentRuleResponse)
async def update_intent_rule(
    rule_id: int,
    request: UpdateIntentRuleRequest,
    current_user: str = Depends(get_current_user)
):
    """Update an intent rule"""
    require_user_management_access(current_user)
    rule = database.update_intent_rule(rule_id, request.dict(exclude_unset=True))
    if not rule:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found"
        )
    return rule

@router.delete("/intent-rules/{rule_id}", response_model=MessageResponse)
async def delete_intent_rule(
    rule_id: int,
    current_user: str = Depends(get_current_user)
):
    """Delete an intent rule"""
    require_user_management_access(current_user)
    success = database.delete_intent_rule(rule_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rule not found"
        )
    return MessageResponse(message="Rule deleted successfully")

@router.get("/intent-groups", response_model=List[IntentGroupResponse])
async def get_intent_groups(current_user: str = Depends(get_current_user)):
    """Get standard intent groups for dropdown"""
    require_user_management_access(current_user)
    from app.intent_service import STANDARD_INTENT_GROUPS
    return STANDARD_INTENT_GROUPS

@router.get("/intent-statistics")
async def get_intent_statistics(
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user),
):
    """
    Get real-time intent distribution statistics from active sessions

    Returns:
    {
        "total_active_sessions": int,
        "by_intent": {
            "Smooth Resolution": int,
            "Repetitive / Looping": int,
            ...
        },
        "unclassified": int,
        "timestamp": float,
        "intent_groups": [
            {
                "group": str,
                "color": str,
                "count": int
            }
        ]
    }
    """
    from app.session_manager import session_manager
    from app.intent_service import STANDARD_INTENT_GROUPS

    require_team_access(current_user, team_agent_id, "viewer")
    stats = session_manager.get_intent_statistics(team_agent_id=team_agent_id)

    # Enrich with intent group metadata (color)
    intent_groups = []
    for group_config in STANDARD_INTENT_GROUPS:
        group_name = group_config["group"]
        count = stats["by_intent"].get(group_name, 0)
        intent_groups.append({
            "group": group_name,
            "color": group_config["color"],
            "count": count
        })

    return {
        **stats,
        "intent_groups": intent_groups
    }

@router.post("/intent-rules/init-defaults", response_model=MessageResponse)
async def init_default_rules(current_user: str = Depends(get_current_user)):
    """Initialize default intent rules if none exist"""
    require_user_management_access(current_user)
    from app.intent_service import STANDARD_INTENT_GROUPS
    
    existing_rules = database.get_all_intent_rules()
    if len(existing_rules) > 0:
        return MessageResponse(message="Default rules already exist")
    
    created_count = 0
    for group_info in STANDARD_INTENT_GROUPS:
        try:
            database.create_intent_rule({
                "group": group_info["group"],
                "color": group_info["color"],
                "keywords": group_info["default_keywords"],
                "description": group_info["description"]
            })
            created_count += 1
        except Exception as e:
            print(f"Error creating default rule for {group_info['group']}: {e}")
    
    return MessageResponse(message=f"Created {created_count} default intent rules")

# Team Agent endpoints
@router.get("/team-agents")
async def get_team_agents(current_user: str = Depends(get_current_user)):
    """Get all team agents"""
    teams = database.get_all_team_agents(username=current_user)
    return teams


@router.post("/team-agents", response_model=MessageResponse)
async def create_team_agent(
    request: "CreateTeamAgentRequest",
    current_user: str = Depends(get_current_user)
):
    """Create a new team agent"""
    from app.models import CreateTeamAgentRequest
    team_id = database.create_team_agent(
        name=request.name,
        slug=request.slug,
        description=request.description,
        created_by=current_user,
    )
    return MessageResponse(message=f"Team agent created with ID {team_id}")


@router.get("/team-agents/{team_id}")
async def get_team_agent(team_id: int, current_user: str = Depends(get_current_user)):
    """Get a team agent by ID with members"""
    require_team_access(current_user, team_id, "viewer")
    team = database.get_team_agent_by_id(team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team agent not found"
        )
    return team


@router.put("/team-agents/{team_id}", response_model=MessageResponse)
async def update_team_agent(
    team_id: int,
    request: "UpdateTeamAgentRequest",
    current_user: str = Depends(get_current_user)
):
    """Update a team agent"""
    require_team_access(current_user, team_id, "admin")
    from app.models import UpdateTeamAgentRequest
    success = database.update_team_agent(
        team_id=team_id,
        name=request.name,
        slug=request.slug,
        description=request.description,
        status=request.status
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team agent not found"
        )
    return MessageResponse(message="Team agent updated")


@router.delete("/team-agents/{team_id}", response_model=MessageResponse)
async def delete_team_agent(team_id: int, current_user: str = Depends(get_current_user)):
    """Delete a team agent"""
    if not database.has_exact_team_role(current_user, team_id, "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only team admins can delete Team Agent",
        )
    success = database.delete_team_agent(team_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team agent not found"
        )
    return MessageResponse(message="Team agent deleted")


@router.get("/team-agents/{team_id}/members")
async def get_team_agent_members(team_id: int, current_user: str = Depends(get_current_user)):
    """Get members of a team agent"""
    require_team_access(current_user, team_id, "viewer")
    team = database.get_team_agent_by_id(team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team agent not found"
        )
    return database.get_team_agent_members(team_id)


@router.put("/team-agents/{team_id}/members", response_model=MessageResponse)
async def update_team_agent_members(
    team_id: int,
    request: "UpdateTeamMembersRequest",
    current_user: str = Depends(get_current_user)
):
    """Update the members of a team agent"""
    require_team_access(current_user, team_id, "admin")
    from app.models import UpdateTeamMembersRequest
    for agent_id in request.member_agent_ids:
        if not database.user_can_access_agent(current_user, agent_id, "viewer"):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} is not available to this user"
            )
    success = database.set_team_agent_members(
        team_id=team_id,
        member_agent_ids=request.member_agent_ids,
        starting_agent_id=request.starting_agent_id
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team agent not found"
        )
    return MessageResponse(message="Team members updated")


# User Management endpoints
@router.get("/users")
async def get_users(current_user: str = Depends(get_current_user)):
    """Get all admin users"""
    require_user_management_access(current_user)
    return database.get_all_admins()


@router.post("/users", response_model=MessageResponse)
async def create_user(
    body: CreateAdminUserRequest,
    current_user: str = Depends(get_current_user),
):
    """Create a new admin user"""
    require_super_admin(current_user)
    user_id = database.create_admin(
        username=body.username,
        password=body.password,
    )
    return MessageResponse(message=f"User created with ID {user_id}")


@router.put("/users/{user_id}", response_model=MessageResponse)
async def update_user(
    user_id: int,
    body: UpdateAdminUserRequest,
    current_user: str = Depends(get_current_user),
):
    """Update an admin user"""
    require_user_management_access(current_user)
    current_admin = database.get_admin_by_username(current_user) or {}
    is_super_admin = bool(current_admin.get("is_super_admin"))
    if not is_super_admin and body.username is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can change usernames",
        )
    if body.password is None and body.username is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )
    success = database.update_admin(
        user_id=user_id,
        username=body.username if is_super_admin else None,
        password=body.password,
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return MessageResponse(message="User updated")


@router.delete("/users/{user_id}", response_model=MessageResponse)
async def delete_user(
    user_id: int,
    current_user: str = Depends(get_current_user),
):
    """Delete an admin user"""
    require_user_management_access(current_user)
    try:
        success = database.delete_admin(user_id)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return MessageResponse(message="User deleted")


@router.get("/team-agents/{team_id}/users")
async def get_team_users(
    team_id: int,
    current_user: str = Depends(get_current_user),
):
    """Get users assigned to a team"""
    require_team_access(current_user, team_id, "admin")
    team = database.get_team_agent_by_id(team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team agent not found"
        )
    return database.get_team_users(team_id)


@router.put("/team-agents/{team_id}/users", response_model=MessageResponse)
async def update_team_users(
    team_id: int,
    body: UpdateTeamUsersRequest,
    current_user: str = Depends(get_current_user),
):
    """Update user roles for a team"""
    require_team_access(current_user, team_id, "owner")
    team = database.get_team_agent_by_id(team_id)
    if not team:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team agent not found"
        )
    for user_entry in body.users:
        admin_id = user_entry.get("admin_id")
        role = user_entry.get("role")
        if admin_id is not None:
            database.set_user_team_role(admin_id, team_id, role)
    return MessageResponse(message="Team users updated")


# Agent endpoints
@router.get("/agents", response_model=List[AgentResponse])
async def get_agents(
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user),
):
    """Get all agents"""
    require_team_access(current_user, team_agent_id, "viewer")
    accessible_team_ids = None
    if team_agent_id is None:
        accessible_team_ids = database.get_accessible_team_ids(current_user, "viewer")
    agents = database.get_all_agents(
        team_agent_id=team_agent_id,
        accessible_team_ids=accessible_team_ids,
    )
    return agents


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: int,
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user),
):
    """Get a single agent by ID"""
    require_team_access(current_user, team_agent_id, "viewer")
    agent = database.get_agent_by_id(agent_id)

    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )
    if team_agent_id is not None and not any(
        item["id"] == agent_id for item in database.get_all_agents(team_agent_id=team_agent_id)
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found in this Team Agent"
        )
    if team_agent_id is None and not database.user_can_access_agent(current_user, agent_id, "viewer"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )

    return agent


@router.post("/agents", response_model=MessageResponse)
async def create_agent(
    request: CreateAgentRequest,
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user)
):
    """Create a new agent"""
    require_team_access(current_user, team_agent_id, "admin")
    try:
        agent_id = database.create_agent(
            name=request.name,
            instructions=request.instructions,
            model=request.model,
            tool_ids=request.tool_ids,
            handoff_agent_ids=request.handoff_agent_ids,
            is_starting_agent=request.is_starting_agent,
            llm_provider_id=request.llm_provider_id,
            team_agent_id=team_agent_id,
        )
        return MessageResponse(message=f"Agent created successfully with ID {agent_id}")
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create agent: {str(e)}"
        )


@router.put("/agents/{agent_id}", response_model=MessageResponse)
async def update_agent(
    agent_id: int,
    request: UpdateAgentRequest,
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user)
):
    """Update an existing agent"""
    require_team_access(current_user, team_agent_id, "admin")
    if not database.user_can_access_agent(current_user, agent_id, "admin", team_agent_id=team_agent_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )
    try:
        success = database.update_agent(
            agent_id=agent_id,
            name=request.name,
            instructions=request.instructions,
            model=request.model,
            tool_ids=request.tool_ids,
            handoff_agent_ids=request.handoff_agent_ids,
            is_starting_agent=request.is_starting_agent,
            llm_provider_id=request.llm_provider_id,
            team_agent_id=team_agent_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
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
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user)
):
    """Delete an agent"""
    require_team_access(current_user, team_agent_id, "admin")
    if not database.user_can_access_agent(current_user, agent_id, "admin", team_agent_id=team_agent_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )
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
    team_agent_id: Optional[int] = None,
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

    require_team_access(current_user, team_agent_id, "viewer")
    if not database.user_can_access_agent(current_user, agent_id, "viewer", team_agent_id=team_agent_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent not found"
        )

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
    from app import provider_service, database

    try:
        # Determine which provider and model to use
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = None
        model = request.model or "gpt-4o-mini"

        if request.llm_provider_id:
            with database.get_db() as db:
                provider = provider_service.get_provider_by_id(db, request.llm_provider_id)
                if provider:
                    api_key = provider.api_key
                    base_url = provider.base_url
                    # Use the provider's default model if request.model is empty? 
                    # Usually request.model is set by the UI.
        
        if not api_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No API key found for the selected provider and no default OpenAI key set."
            )

        client = OpenAI(api_key=api_key, base_url=base_url)

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
            model=model,
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
@router.get("/tools")
async def get_tools(
    response: Response,
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user),
):
    """Get tools, optionally filtered by team"""
    require_team_access(current_user, team_agent_id, "viewer")
    if team_agent_id is None:
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "Sat, 01 Aug 2026 00:00:00 GMT"
    tools = database.get_all_tools(team_agent_id=team_agent_id)
    return tools


@router.get("/tools/{tool_id}")
async def get_tool(
    tool_id: int,
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user),
):
    """Get a single tool by ID"""
    require_team_access(current_user, team_agent_id, "viewer")
    tool = database.get_tool_by_id(tool_id, team_agent_id=team_agent_id)

    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool not found"
        )

    return tool


@router.get("/system-info", response_model=SystemInfoResponse)
async def system_info(
    request: Request,
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user),
):
    """Return dynamic system information for the Admin UI."""
    require_team_access(current_user, team_agent_id, "viewer")
    import os, sys, datetime
    from app import database as db

    # Backend URL from request
    backend_url = str(request.base_url).rstrip('/')
    # Frontend origin hint from Referer (best-effort)
    frontend_origin = request.headers.get('origin') or request.headers.get('referer')
    if frontend_origin:
        # Trim paths if referer
        try:
            from urllib.parse import urlparse
            parsed = urlparse(frontend_origin)
            frontend_origin = f"{parsed.scheme}://{parsed.netloc}"
        except Exception:
            pass

    # Flags
    disable_mcp = os.getenv("DISABLE_MCP", "").lower() in {"1", "true", "yes"} or os.getenv(
        "AGENTS_SAFE_MODE_DISABLE_EXTERNAL", ""
    ).lower() in {"1", "true", "yes"}
    mcp_enabled = not disable_mcp
    openai_api_key_set = bool(os.getenv("OPENAI_API_KEY"))

    # Counts
    agents = db.get_all_agents()
    tools = db.get_all_tools(team_agent_id=team_agent_id)

    return SystemInfoResponse(
        backend_url=backend_url,
        frontend_origin=frontend_origin,
        server_time=datetime.datetime.utcnow().isoformat() + "Z",
        python_version=sys.version.split()[0],
        mcp_enabled=mcp_enabled,
        openai_api_key_set=openai_api_key_set,
        agents_count=len(agents),
        tools_count=len(tools),
    )


@router.post("/tools", response_model=MessageResponse)
async def create_tool(
    request: CreateCustomToolRequest,
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user),
):
    """Create a custom API tool, optionally owned by a team"""
    require_team_access(current_user, team_agent_id, "admin")
    try:
        tool_id = database.create_custom_tool(
            request.name, request.config, request.icon,
            team_agent_id=team_agent_id,
            visibility=request.visibility or "team",
            created_by_username=current_user,
        )
        if request.assign_agent_id is not None:
            if not database.user_can_access_agent(current_user, request.assign_agent_id, "admin", team_agent_id=team_agent_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="You do not have permission to assign tools to this agent",
                )
            assigned = database.assign_tool_to_agent(
                agent_id=request.assign_agent_id,
                tool_id=tool_id,
                team_agent_id=team_agent_id,
            )
            if not assigned:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Failed to auto-assign tool to target agent",
                )
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
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user),
):
    """Update a custom API tool"""
    require_team_access(current_user, team_agent_id, "admin")
    success = database.update_custom_tool(
        tool_id, request.name, request.config, request.icon,
        team_agent_id=team_agent_id,
        visibility=request.visibility,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool not found or is not a custom tool"
        )

    return MessageResponse(message="Tool updated successfully")


@router.delete("/tools/{tool_id}", response_model=MessageResponse)
async def delete_tool(
    tool_id: int,
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user),
):
    """Delete a custom API tool"""
    require_team_access(current_user, team_agent_id, "admin")
    success = database.delete_custom_tool(tool_id, team_agent_id=team_agent_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool not found or is not a custom tool"
        )

    return MessageResponse(message="Tool deleted successfully")


@router.put("/tools/{tool_id}/visibility", response_model=MessageResponse)
async def update_tool_visibility(
    tool_id: int,
    request: Request,
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user),
):
    """Update a tool's visibility (team or global)"""
    body = await request.json()
    visibility = body.get("visibility")
    request_team_agent_id = body.get("team_agent_id", team_agent_id)
    require_team_access(current_user, request_team_agent_id, "admin")
    if visibility not in ("team", "global"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Visibility must be 'team' or 'global'"
        )
    success = database.set_tool_visibility(tool_id, visibility, team_agent_id=request_team_agent_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tool not found"
        )
    return MessageResponse(message=f"Tool visibility updated to {visibility}")


# File Store endpoints
@router.get("/file-stores", response_model=List[FileStoreResponse])
async def get_file_stores(current_user: str = Depends(get_current_user)):
    """Get all file stores"""
    require_team_admin_scope_access(current_user)
    stores = database.get_all_file_stores()
    return stores


@router.post("/file-stores", response_model=MessageResponse)
async def create_file_store(
    request: CreateFileStoreRequest,
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user)
):
    """Create a new file search store"""
    require_team_admin_scope_access(current_user)
    require_team_access(current_user, team_agent_id, "admin")
    try:
        from app.gemini_service import GeminiFileSearchService

        # Initialize Gemini service
        service = GeminiFileSearchService()

        # Create Gemini store
        result = service.create_store(display_name=request.display_name)
        gemini_store_id = result["store_id"]

        # Generate unique name from display name (sanitize for ASCII-only)
        name = sanitize_tool_name(request.display_name.lower())

        # Save to database
        store_id = database.create_file_store(
            name=name,
            gemini_store_id=gemini_store_id,
            display_name=request.display_name
        )

        # Auto-create tool if requested
        if request.create_tool:
            tool_name = f"{name}_search"
            tool_config = {
                "type": "gemini_file_search",
                "description": f"Search documents in {request.display_name}",
                "gemini_store_id": gemini_store_id,
                "model": "gemini-2.5-flash"
            }
            created_tool_id = database.create_custom_tool(
                tool_name,
                tool_config,
                icon="FileSearch",
                team_agent_id=team_agent_id,
                visibility="team" if team_agent_id else "global",
                created_by_username=current_user,
            )
            if request.assign_agent_id is not None:
                if not database.user_can_access_agent(current_user, request.assign_agent_id, "admin"):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="You do not have permission to assign tools to this agent",
                    )
                assigned = database.assign_tool_to_agent(
                    agent_id=request.assign_agent_id,
                    tool_id=created_tool_id,
                    team_agent_id=team_agent_id,
                )
                if not assigned:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Failed to auto-assign file store tool to target agent",
                    )

        return MessageResponse(
            message=f"File store created successfully with ID {store_id}. Gemini store: {gemini_store_id}"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create file store: {str(e)}"
        )


@router.delete("/file-stores/{store_id}", response_model=MessageResponse)
async def delete_file_store(
    store_id: int,
    current_user: str = Depends(get_current_user)
):
    """Delete a file store and optionally its Gemini store"""
    require_team_admin_scope_access(current_user)
    store = database.get_file_store_by_id(store_id)

    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File store not found"
        )

    try:
        from app.gemini_service import GeminiFileSearchService

        # Try to delete from Gemini (best effort)
        try:
            service = GeminiFileSearchService()
            service.delete_store(store["gemini_store_id"])
        except Exception as e:
            print(f"Warning: Could not delete Gemini store: {e}")

        # Delete from database (cascades to files)
        success = database.delete_file_store(store_id)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete file store from database"
            )

        return MessageResponse(message="File store deleted successfully")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file store: {str(e)}"
        )


@router.get("/file-stores/{store_id}/files", response_model=List[FileStoreFileResponse])
async def get_files(
    store_id: int,
    current_user: str = Depends(get_current_user)
):
    """Get all files in a file store"""
    require_team_admin_scope_access(current_user)
    store = database.get_file_store_by_id(store_id)

    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File store not found"
        )

    files = database.get_files_by_store(store_id)
    return files


@router.post("/file-stores/{store_id}/upload", response_model=MessageResponse)
async def upload_file(
    store_id: int,
    file: UploadFile = File(...),
    current_user: str = Depends(get_current_user)
):
    """Upload a file to a file store"""
    require_team_admin_scope_access(current_user)
    store = database.get_file_store_by_id(store_id)

    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File store not found"
        )

    try:
        from app.gemini_service import GeminiFileSearchService

        # Save uploaded file temporarily
        temp_dir = Path("/tmp")
        # Use safe ASCII-only temp filename to handle non-ASCII characters
        safe_suffix = Path(file.filename).suffix if file.filename else ""
        temp_path = temp_dir / f"upload_{int(time.time())}{safe_suffix}"

        with open(temp_path, "wb") as f:
            content = await file.read()
            f.write(content)

        try:
            # Upload to Gemini
            service = GeminiFileSearchService()
            result = service.upload_file(
                store_id=store["gemini_store_id"],
                file_path=str(temp_path)
            )

            if not result.get("success"):
                raise Exception(result.get("error", "Upload failed"))

            # Save file record to database
            file_size = len(content)
            database.add_file_to_store(
                file_store_id=store_id,
                filename=result["filename"],
                original_filename=file.filename,
                file_size=file_size
            )

            return MessageResponse(
                message=f"File '{file.filename}' uploaded successfully in {result.get('upload_time', 0):.1f}s"
            )

        finally:
            # Clean up temp file
            if temp_path.exists():
                temp_path.unlink()

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Upload error: {error_trace}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload file: {str(e)}"
        )


@router.delete("/file-stores/files/{file_id}", response_model=MessageResponse)
async def delete_file(
    file_id: int,
    current_user: str = Depends(get_current_user)
):
    """Delete a file from a file store"""
    require_team_admin_scope_access(current_user)
    # Note: Gemini API doesn't support individual file deletion
    # We only delete the record from our database
    success = database.delete_file(file_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )

    return MessageResponse(
        message="File record deleted successfully. Note: File remains in Gemini store."
    )


@router.post("/file-stores/{store_id}/test", response_model=TestFileStoreResponse)
async def test_file_store(
    store_id: int,
    request: TestFileStoreRequest,
    current_user: str = Depends(get_current_user)
):
    """Test a file store by querying it"""
    require_team_admin_scope_access(current_user)
    store = database.get_file_store_by_id(store_id)

    if not store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File store not found"
        )

    try:
        from app.gemini_service import GeminiFileSearchService

        # Query the file store
        service = GeminiFileSearchService()
        start_time = time.time()
        result = service.query(
            store_id=store["gemini_store_id"],
            query=request.query
        )
        response_time = time.time() - start_time

        return TestFileStoreResponse(
            response=result["response"],
            grounding_sources=result.get("grounding_sources", []),
            metadata=result.get("metadata"),
            response_time=response_time
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test file store: {str(e)}"
        )


# VoIP Provider endpoints
@router.get("/voip-providers", response_model=List[VoIPProviderResponse])
async def get_voip_providers(current_user: str = Depends(get_current_user)):
    """Get all VoIP providers"""
    require_user_management_access(current_user)
    providers = database.get_all_voip_providers()
    
    # Initialize default Twilio provider if none exist
    if not providers:
        default_config = {
            "account_sid": "",
            "auth_token": "",
            "phone_number": ""
        }
        database.create_voip_provider("Twilio", "twilio", default_config, is_active=True)
        providers = database.get_all_voip_providers()

    return providers


@router.get("/voip-providers/{provider_id}", response_model=VoIPProviderResponse)
async def get_voip_provider(provider_id: int, current_user: str = Depends(get_current_user)):
    """Get a single VoIP provider by ID"""
    require_user_management_access(current_user)
    provider = database.get_voip_provider_by_id(provider_id)

    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VoIP provider not found"
        )

    return provider


@router.post("/voip-providers", response_model=MessageResponse)
async def create_voip_provider(
    request: CreateVoIPProviderRequest,
    current_user: str = Depends(get_current_user)
):
    """Create a new VoIP provider"""
    require_user_management_access(current_user)
    try:
        provider_id = database.create_voip_provider(
            name=request.name,
            type=request.type,
            config=request.config,
            is_active=request.is_active
        )
        return MessageResponse(message=f"VoIP provider created successfully with ID {provider_id}")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create VoIP provider: {str(e)}"
        )


@router.put("/voip-providers/{provider_id}", response_model=MessageResponse)
async def update_voip_provider(
    provider_id: int,
    request: UpdateVoIPProviderRequest,
    current_user: str = Depends(get_current_user)
):
    """Update a VoIP provider"""
    require_user_management_access(current_user)
    success = database.update_voip_provider(
        provider_id=provider_id,
        name=request.name,
        type=request.type,
        config=request.config,
        is_active=request.is_active
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VoIP provider not found"
        )

    return MessageResponse(message="VoIP provider updated successfully")


@router.delete("/voip-providers/{provider_id}", response_model=MessageResponse)
async def delete_voip_provider(
    provider_id: int,
    current_user: str = Depends(get_current_user)
):
    """Delete a VoIP provider"""
    require_user_management_access(current_user)
    success = database.delete_voip_provider(provider_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VoIP provider not found"
        )

    return MessageResponse(message="VoIP provider deleted successfully")


# Channel Config endpoints
@router.get("/channel-configs", response_model=List[ChannelConfigResponse])
async def get_channel_configs(
    response: Response,
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user),
):
    require_team_access(current_user, team_agent_id, "viewer")
    if team_agent_id is None:
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "Sat, 01 Aug 2026 00:00:00 GMT"
    configs = database.get_all_channel_configs(team_agent_id=team_agent_id)
    existing_types = {config["type"] for config in configs}
    team = database.get_team_agent_by_id(team_agent_id) if team_agent_id is not None else None
    team_prefix = f"/api/public/teams/{team['slug']}" if team else "/api/public"

    defaults = {
        "line": {
            "name": "Line Messaging",
            "config": {
                "channel_id": "",
                "channel_secret": "",
                "channel_access_token": "",
                "webhook_url": f"{team_prefix}/channels/line/webhook"
            },
            "is_active": False
        },
        "facebook": {
            "name": "Facebook Messaging",
            "config": {
                "page_id": "",
                "app_id": "",
                "app_secret": "",
                "page_access_token": "",
                "verify_token": "",
                "webhook_url": f"{team_prefix}/channels/facebook/webhook"
            },
            "is_active": False
        }
    }

    for channel_type, default in defaults.items():
        if channel_type not in existing_types:
            database.upsert_channel_config(
                channel_type=channel_type,
                name=default["name"],
                config=default["config"],
                is_active=default["is_active"],
                team_agent_id=team_agent_id,
            )

    return database.get_all_channel_configs(team_agent_id=team_agent_id)


@router.get("/channel-configs/{channel_type}", response_model=ChannelConfigResponse)
async def get_channel_config(
    channel_type: str,
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user),
):
    require_team_access(current_user, team_agent_id, "viewer")
    if channel_type not in {"line", "facebook"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported channel type"
        )

    config = database.get_channel_config(channel_type, team_agent_id=team_agent_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel config not found"
        )

    return config


@router.put("/channel-configs/{channel_type}", response_model=ChannelConfigResponse)
async def update_channel_config(
    channel_type: str,
    request: UpdateChannelConfigRequest,
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user)
):
    require_team_access(current_user, team_agent_id, "admin")
    if channel_type not in {"line", "facebook"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported channel type"
        )

    return database.upsert_channel_config(
        channel_type=channel_type,
        name=request.name,
        config=request.config,
        is_active=request.is_active,
        team_agent_id=team_agent_id,
    )


# LLM Provider endpoints
@router.get("/llm-providers", response_model=List[LLMProviderResponse])
async def get_llm_providers(current_user: str = Depends(get_current_user)):
    """Get all LLM providers"""
    from app import provider_service
    with database.get_db() as db:
        providers = provider_service.get_all_providers(db)
        return [
            LLMProviderResponse(
                id=p.id,
                name=p.name,
                base_url=p.base_url,
                api_key=p.api_key,
                is_default=p.is_default,
                created_at=p.created_at.isoformat(),
                updated_at=p.updated_at.isoformat()
            )
            for p in providers
        ]


@router.post("/llm-providers", response_model=MessageResponse)
async def create_llm_provider(
    request: CreateLLMProviderRequest,
    current_user: str = Depends(get_current_user)
):
    """Create a new LLM provider (super admin only)"""
    require_super_admin(current_user)
    from app import provider_service
    with database.get_db() as db:
        try:
            provider = provider_service.create_provider(db, request)
            return MessageResponse(message=f"Provider created successfully with ID {provider.id}")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create provider: {str(e)}"
            )


@router.put("/llm-providers/{provider_id}", response_model=MessageResponse)
async def update_llm_provider(
    provider_id: int,
    request: UpdateLLMProviderRequest,
    current_user: str = Depends(get_current_user)
):
    """Update an LLM provider (super admin only)"""
    require_super_admin(current_user)
    from app import provider_service
    with database.get_db() as db:
        provider = provider_service.update_provider(db, provider_id, request)
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Provider not found"
            )
        return MessageResponse(message="Provider updated successfully")


@router.delete("/llm-providers/{provider_id}", response_model=MessageResponse)
async def delete_llm_provider(
    provider_id: int,
    current_user: str = Depends(get_current_user)
):
    """Delete an LLM provider (super admin only)"""
    require_super_admin(current_user)
    from app import provider_service
    with database.get_db() as db:
        success = provider_service.delete_provider(db, provider_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Provider not found"
            )
        return MessageResponse(message="Provider deleted successfully")


@router.get("/llm-providers/{provider_id}/models", response_model=List[dict])
async def get_provider_models(
    provider_id: int,
    current_user: str = Depends(get_current_user)
):
    """Fetch available models from the provider"""
    from app import provider_service
    with database.get_db() as db:
        provider = provider_service.get_provider_by_id(db, provider_id)
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Provider not found"
            )
        
        try:
            models = await provider_service.get_available_models(provider)
            # Return raw model data (usually list of objects or dicts)
            # If models are pydantic objects, dump them
            return [m.model_dump() if hasattr(m, 'model_dump') else m for m in models]
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch models: {str(e)}"
            )


@router.put("/voip-providers/{provider_id}", response_model=MessageResponse)
async def update_voip_provider(
    provider_id: int,
    request: UpdateVoIPProviderRequest,
    current_user: str = Depends(get_current_user)
):
    """Update an existing VoIP provider"""
    require_user_management_access(current_user)
    success = database.update_voip_provider(
        provider_id=provider_id,
        name=request.name,
        type=request.type,
        config=request.config,
        is_active=request.is_active
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VoIP provider not found"
        )

    return MessageResponse(message="VoIP provider updated successfully")


@router.delete("/voip-providers/{provider_id}", response_model=MessageResponse)
async def delete_voip_provider(
    provider_id: int,
    current_user: str = Depends(get_current_user)
):
    """Delete a VoIP provider"""
    require_user_management_access(current_user)
    success = database.delete_voip_provider(provider_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="VoIP provider not found"
        )

    return MessageResponse(message="VoIP provider deleted successfully")


# Analytics endpoints
@router.get("/analytics/summary")
async def get_analytics_summary(
    period: str = "today",
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user)
):
    """
    Get analytics summary for dashboard

    Args:
        period: 'today', 'week', 'month', or 'all'
    """
    try:
        require_team_access(current_user, team_agent_id, "viewer")
        summary = database.get_analytics_summary(period, team_agent_id=team_agent_id)
        return summary
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get analytics summary: {str(e)}"
        )


@router.get("/analytics/conversations")
async def get_conversations(
    limit: int = 50,
    offset: int = 0,
    outcome: str = None,
    sentiment: str = None,
    topic: str = None,
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user)
):
    """
    Get list of conversations with optional filters

    Args:
        limit: Maximum number of conversations to return (default: 50)
        offset: Number of conversations to skip (default: 0)
        outcome: Filter by outcome ('resolved', 'escalated', 'abandoned', 'ongoing')
        sentiment: Filter by sentiment ('positive', 'neutral', 'negative')
        topic: Filter by primary topic
    """
    try:
        require_team_access(current_user, team_agent_id, "viewer")
        conn = database.get_db_connection()
        cursor = conn.cursor()

        # Build query with filters (PostgreSQL syntax with %s)
        query = """
            SELECT
                c.id,
                c.session_id,
                c.started_at,
                c.ended_at,
                c.duration_seconds,
                c.total_messages,
                c.user_messages,
                c.agent_messages,
                c.agents_involved,
                c.tools_used,
                c.outcome,
                c.enrichment_status,
                c.team_agent_id,
                t.name as team_agent_name,
                ca.overall_sentiment,
                ca.sentiment_score,
                ca.primary_topic,
                ca.resolution_quality,
                ca.urgency_level
            FROM conversations c
            LEFT JOIN conversation_analytics ca ON c.id = ca.conversation_id
            LEFT JOIN team_agents t ON c.team_agent_id = t.id
            WHERE c.enrichment_status != 'skipped'
        """
        params = []

        if outcome:
            query += " AND c.outcome = %s"
            params.append(outcome)

        if sentiment:
            query += " AND ca.overall_sentiment = %s"
            params.append(sentiment)

        if topic:
            query += " AND ca.primary_topic = %s"
            params.append(topic)

        if team_agent_id is not None:
            query += " AND c.team_agent_id = %s"
            params.append(team_agent_id)

        query += " ORDER BY c.started_at DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # RealDictCursor returns dict-like rows, convert to regular dicts
        conversations = []
        for row in rows:
            conv_dict = dict(row)
            # Convert datetime to ISO format string
            if conv_dict.get('started_at'):
                conv_dict['started_at'] = conv_dict['started_at'].isoformat()
            if conv_dict.get('ended_at'):
                conv_dict['ended_at'] = conv_dict['ended_at'].isoformat()
            # agents_involved and tools_used are already Python lists from JSONB
            conversations.append(conv_dict)

        # Get total count for pagination (PostgreSQL syntax)
        count_query = "SELECT COUNT(*) FROM conversations c LEFT JOIN conversation_analytics ca ON c.id = ca.conversation_id WHERE c.enrichment_status != 'skipped'"
        count_params = []
        if outcome:
            count_query += " AND c.outcome = %s"
            count_params.append(outcome)
        if sentiment:
            count_query += " AND ca.overall_sentiment = %s"
            count_params.append(sentiment)
        if topic:
            count_query += " AND ca.primary_topic = %s"
            count_params.append(topic)
        if team_agent_id is not None:
            count_query += " AND c.team_agent_id = %s"
            count_params.append(team_agent_id)

        cursor.execute(count_query, count_params)
        total = cursor.fetchone()["count"]

        conn.close()

        return {
            "conversations": conversations,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"❌ Get conversations error: {error_trace}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get conversations: {str(e)}"
        )


@router.get("/analytics/conversations/{conversation_id}")
async def get_conversation_detail(
    conversation_id: int,
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user)
):
    """
    Get detailed conversation information including messages and analytics
    """
    try:
        require_team_access(current_user, team_agent_id, "viewer")
        conn = database.get_db_connection()
        cursor = conn.cursor()

        # Get conversation metadata (PostgreSQL syntax)
        if team_agent_id is not None:
            cursor.execute(
                "SELECT * FROM conversations WHERE id = %s AND team_agent_id = %s",
                (conversation_id, team_agent_id)
            )
        else:
            cursor.execute(
                "SELECT * FROM conversations WHERE id = %s",
                (conversation_id,)
            )
        conv_row = cursor.fetchone()

        if not conv_row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found"
            )

        # RealDictCursor returns dict-like rows
        conversation = dict(conv_row)

        # Resolve team name if team_agent_id is set
        if conversation.get('team_agent_id'):
            team = database.get_team_agent_by_id(conversation['team_agent_id'])
            conversation['team_agent_name'] = team['name'] if team else None
        else:
            conversation['team_agent_name'] = None

        # Convert datetime to ISO format string
        if conversation.get('started_at'):
            conversation['started_at'] = conversation['started_at'].isoformat()
        if conversation.get('ended_at'):
            conversation['ended_at'] = conversation['ended_at'].isoformat()
        if conversation.get('created_at'):
            conversation['created_at'] = conversation['created_at'].isoformat()
        # agents_involved and tools_used are already Python lists from JSONB

        # Get messages
        messages = database.get_conversation_messages(conversation_id)

        # Get analytics if available (PostgreSQL syntax)
        cursor.execute(
            "SELECT * FROM conversation_analytics WHERE conversation_id = %s",
            (conversation_id,)
        )
        analytics_row = cursor.fetchone()

        analytics = None
        if analytics_row:
            # RealDictCursor returns dict-like rows
            analytics = dict(analytics_row)

            # Convert datetime to ISO format string
            if analytics.get('analyzed_at'):
                analytics['analyzed_at'] = analytics['analyzed_at'].isoformat()
            # JSON fields (topics, issues_identified, customer_pain_points, suggestions)
            # are already Python lists from JSONB, no need to parse

        conn.close()

        return {
            "conversation": conversation,
            "messages": messages,
            "analytics": analytics
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get conversation detail: {str(e)}"
        )


@router.get("/analytics/trends")
async def get_analytics_trends(
    period: str = "week",
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user)
):
    """
    Get analytics trends over time for charts

    Args:
        period: 'week' or 'month'
    """
    try:
        require_team_access(current_user, team_agent_id, "viewer")
        conn = database.get_db_connection()
        cursor = conn.cursor()

        # Determine number of days
        days = 7 if period == "week" else 30

        team_filter = " AND team_agent_id = %s" if team_agent_id is not None else ""
        team_join_filter = " AND c.team_agent_id = %s" if team_agent_id is not None else ""

        # Daily conversation volume (PostgreSQL syntax)
        cursor.execute(
            f"""
            SELECT DATE(started_at) as date, COUNT(*) as count
            FROM conversations
            WHERE DATE(started_at) >= CURRENT_DATE - INTERVAL '{days} days'
            AND enrichment_status != 'skipped'
            {team_filter}
            GROUP BY DATE(started_at)
            ORDER BY date ASC
            """,
            (team_agent_id,) if team_agent_id is not None else None
        )
        volume_rows = cursor.fetchall()
        daily_volume = [{"date": str(row["date"]) if row["date"] else None, "count": row["count"]} for row in volume_rows]

        # Daily sentiment trend (PostgreSQL syntax)
        cursor.execute(
            f"""
            SELECT DATE(c.started_at) as date, AVG(ca.sentiment_score) as avg_sentiment
            FROM conversation_analytics ca
            JOIN conversations c ON ca.conversation_id = c.id
            WHERE DATE(c.started_at) >= CURRENT_DATE - INTERVAL '{days} days'
            AND c.enrichment_status != 'skipped'
            AND ca.sentiment_score IS NOT NULL
            {team_join_filter}
            GROUP BY DATE(c.started_at)
            ORDER BY date ASC
            """,
            (team_agent_id,) if team_agent_id is not None else None
        )
        sentiment_rows = cursor.fetchall()
        daily_sentiment = [{"date": str(row["date"]) if row["date"] else None, "sentiment": round(row["avg_sentiment"], 2) if row["avg_sentiment"] else 0} for row in sentiment_rows]

        # Agent performance (PostgreSQL JSON array access)
        cursor.execute(
            f"""
            SELECT
                c.agents_involved->>0 as agent_name,
                COUNT(*) as total_conversations,
                AVG(ca.agent_performance_score) as avg_performance,
                AVG(ca.empathy_score) as avg_empathy,
                AVG(ca.response_clarity_score) as avg_clarity,
                COUNT(CASE WHEN c.outcome = 'resolved' THEN 1 END) * 100.0 / COUNT(*) as resolution_rate
            FROM conversations c
            LEFT JOIN conversation_analytics ca ON c.id = ca.conversation_id
            WHERE c.agents_involved IS NOT NULL
            AND c.agents_involved::text != '[]'
            AND c.enrichment_status != 'skipped'
            {team_join_filter}
            GROUP BY c.agents_involved->>0
            HAVING COUNT(*) >= 1
            ORDER BY total_conversations DESC
            LIMIT 10
            """,
            (team_agent_id,) if team_agent_id is not None else None
        )
        agent_rows = cursor.fetchall()
        agent_performance = []
        for row in agent_rows:
            agent_name = row["agent_name"]
            if agent_name:
                # Remove quotes if present (JSON string value)
                if isinstance(agent_name, str):
                    agent_name = agent_name.strip('"')
                agent_performance.append({
                    "agent": agent_name,
                    "conversations": row["total_conversations"],
                    "performance": round(row["avg_performance"] * 100, 1) if row["avg_performance"] else 0,
                    "empathy": round(row["avg_empathy"] * 100, 1) if row["avg_empathy"] else 0,
                    "clarity": round(row["avg_clarity"] * 100, 1) if row["avg_clarity"] else 0,
                    "resolution_rate": round(row["resolution_rate"], 1) if row["resolution_rate"] else 0
                })

        conn.close()

        return {
            "daily_volume": daily_volume,
            "daily_sentiment": daily_sentiment,
            "agent_performance": agent_performance
        }

    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"❌ Analytics trends error: {error_trace}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get analytics trends: {str(e)}"
        )


@router.get("/analytics/sessions-by-team")
async def get_sessions_by_team(
    period: str = "day",
    current_user: str = Depends(get_current_user),
):
    """Get stacked session counts by time bucket and team with permission filtering."""
    try:
        if period not in {"day", "week", "month"}:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Period must be one of: day, week, month",
            )

        accessible_team_ids = database.get_accessible_team_ids(current_user, "viewer")
        conn = database.get_db_connection()
        cursor = conn.cursor()

        if accessible_team_ids == []:
            return {"series": [], "teams": []}

        if period == "day":
            bucket_trunc = "hour"
            bucket_step = "1 hour"
            start_expr = "date_trunc('day', CURRENT_TIMESTAMP)"
            end_expr = "date_trunc('day', CURRENT_TIMESTAMP) + interval '1 day'"
        elif period == "week":
            bucket_trunc = "day"
            bucket_step = "1 day"
            start_expr = "date_trunc('week', CURRENT_TIMESTAMP)"
            end_expr = "date_trunc('week', CURRENT_TIMESTAMP) + interval '7 days'"
        else:
            bucket_trunc = "day"
            bucket_step = "1 day"
            start_expr = "date_trunc('month', CURRENT_TIMESTAMP)"
            end_expr = "date_trunc('month', CURRENT_TIMESTAMP) + interval '1 month'"

        team_filter = ""
        params: list = []
        if accessible_team_ids is not None:
            team_filter = "AND c.team_agent_id = ANY(%s)"
            params.append(accessible_team_ids)

        cursor.execute(
            f"""
            WITH bounds AS (
                SELECT
                    {start_expr} AS start_ts,
                    {end_expr} AS end_ts
            ),
            buckets AS (
                SELECT
                    generate_series(
                        (SELECT start_ts FROM bounds),
                        (SELECT end_ts - interval '{bucket_step}' FROM bounds),
                        interval '{bucket_step}'
                    ) AS bucket_start
            ),
            session_counts AS (
                SELECT
                    date_trunc('{bucket_trunc}', c.started_at) AS bucket_start,
                    COALESCE(t.name, 'Unknown Team') AS team_agent_name,
                    COUNT(*) AS session_count
                FROM conversations c
                LEFT JOIN team_agents t ON t.id = c.team_agent_id
                WHERE c.started_at >= (SELECT start_ts FROM bounds)
                  AND c.started_at < (SELECT end_ts FROM bounds)
                  AND c.enrichment_status != 'skipped'
                  {team_filter}
                GROUP BY 1, 2
            )
            SELECT
                b.bucket_start,
                sc.team_agent_name,
                sc.session_count
            FROM buckets b
            LEFT JOIN session_counts sc ON sc.bucket_start = b.bucket_start
            ORDER BY b.bucket_start ASC, sc.team_agent_name ASC
            """,
            params,
        )
        rows = cursor.fetchall()
        conn.close()

        bucket_map: dict[str, dict] = {}
        teams: list[str] = []
        for row in rows:
            bucket_start = row["bucket_start"]
            if bucket_start is None:
                continue
            bucket_key = bucket_start.isoformat()
            if period == "day":
                label = bucket_start.strftime("%H:%M")
            elif period == "week":
                label = bucket_start.strftime("%a")
            else:
                label = bucket_start.strftime("%d")

            if bucket_key not in bucket_map:
                bucket_map[bucket_key] = {"label": label}

            team_name = row["team_agent_name"]
            count = row["session_count"]
            if not team_name or count is None:
                continue
            bucket_map[bucket_key][team_name] = count
            if team_name not in teams:
                teams.append(team_name)

        series = [bucket_map[k] for k in sorted(bucket_map.keys())]
        for point in series:
            for team_name in teams:
                point.setdefault(team_name, 0)

        return {"series": series, "teams": teams}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get sessions by team: {str(e)}",
        )


@router.delete("/conversations", response_model=MessageResponse)
async def delete_conversations(current_user: str = Depends(get_current_user)):
    """Delete all conversation history (messages, analytics, summaries)."""
    try:
        result = database.delete_all_conversations()
        return MessageResponse(
            message=(
                "Conversation history deleted "
                f"(conversations: {result.get('conversations', 0)}, "
                f"messages: {result.get('messages', 0)}, "
                f"analytics: {result.get('analytics', 0)}, "
                f"summaries: {result.get('summaries', 0)})"
            )
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete conversations: {str(e)}"
        )


# API Key endpoints
@router.get("/api-keys", response_model=List[ApiKeyResponse])
async def get_api_keys(
    response: Response,
    team_agent_id: Optional[int] = None,
    current_user: str = Depends(get_current_user),
):
    """Get all API keys"""
    require_team_access(current_user, team_agent_id, "viewer")
    if team_agent_id is None:
        response.headers["Deprecation"] = "true"
        response.headers["Sunset"] = "Sat, 01 Aug 2026 00:00:00 GMT"
    keys = database.get_all_api_keys(team_agent_id=team_agent_id)
    return keys


@router.get("/api-keys/{key_id}", response_model=ApiKeyResponse)
async def get_api_key(key_id: int, current_user: str = Depends(get_current_user)):
    """Get a single API key by ID"""
    key = database.get_api_key_by_id(key_id)

    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    require_team_access(current_user, key.get("team_agent_id"), "viewer")

    return key


@router.post("/api-keys", response_model=MessageResponse)
async def create_api_key(
    request: CreateApiKeyRequest,
    current_user: str = Depends(get_current_user)
):
    """Create a new API key"""
    require_team_access(current_user, request.team_agent_id, "admin")
    import secrets
    from datetime import timedelta

    try:
        # Generate a secure random API key
        api_key = f"sk_{secrets.token_urlsafe(32)}"

        # Calculate expiration date if specified
        expires_at = None
        if request.expires_days:
            from datetime import datetime
            expires_at = datetime.utcnow() + timedelta(days=request.expires_days)

        # Create the API key
        key_id = database.create_api_key(
            name=request.name,
            key=api_key,
            expires_at=expires_at,
            created_by=current_user,
            allowed_domains=request.allowed_domains,
            voice_response_enabled=request.voice_response_enabled,
            team_agent_id=request.team_agent_id,
            channel_type=request.channel_type or "web_widget",
        )

        return MessageResponse(
            message=f"API key created successfully. Key: {api_key} (Save this key securely - it won't be shown again!)"
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create API key: {str(e)}"
        )


@router.put("/api-keys/{key_id}", response_model=MessageResponse)
async def update_api_key(
    key_id: int,
    request: UpdateApiKeyRequest,
    current_user: str = Depends(get_current_user)
):
    """Update an API key"""
    existing_key = database.get_api_key_by_id(key_id)
    if not existing_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    require_team_access(current_user, existing_key.get("team_agent_id"), "admin")
    require_team_access(current_user, request.team_agent_id, "admin")
    from datetime import datetime

    # Parse expires_at if provided
    expires_at = None
    if request.expires_at:
        expires_at = datetime.fromisoformat(request.expires_at)

    success = database.update_api_key(
        key_id=key_id,
        name=request.name,
        is_active=request.is_active,
        expires_at=expires_at,
        allowed_domains=request.allowed_domains,
        voice_response_enabled=request.voice_response_enabled,
        team_agent_id=request.team_agent_id,
        channel_type=request.channel_type,
    )

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    return MessageResponse(message="API key updated successfully")


@router.delete("/api-keys/{key_id}", response_model=MessageResponse)
async def delete_api_key(
    key_id: int,
    current_user: str = Depends(get_current_user)
):
    """Delete an API key"""
    key = database.get_api_key_by_id(key_id)
    if not key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )
    require_team_access(current_user, key.get("team_agent_id"), "admin")
    success = database.delete_api_key(key_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    return MessageResponse(message="API key deleted successfully")


# LLM Provider endpoints
@router.get("/llm-providers", response_model=List[LLMProviderResponse])
async def get_llm_providers(current_user: str = Depends(get_current_user)):
    """Get all LLM providers"""
    from app import provider_service
    with database.get_db() as db:
        providers = provider_service.get_all_providers(db)
        return [
            LLMProviderResponse(
                id=p.id,
                name=p.name,
                base_url=p.base_url,
                api_key=p.api_key,
                is_default=p.is_default,
                created_at=p.created_at.isoformat(),
                updated_at=p.updated_at.isoformat()
            )
            for p in providers
        ]


@router.post("/llm-providers", response_model=MessageResponse)
async def create_llm_provider(
    request: CreateLLMProviderRequest,
    current_user: str = Depends(get_current_user)
):
    """Create a new LLM provider (super admin only)"""
    require_super_admin(current_user)
    from app import provider_service
    with database.get_db() as db:
        try:
            provider = provider_service.create_provider(db, request)
            return MessageResponse(message=f"Provider created successfully with ID {provider.id}")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create provider: {str(e)}"
            )


@router.put("/llm-providers/{provider_id}", response_model=MessageResponse)
async def update_llm_provider(
    provider_id: int,
    request: UpdateLLMProviderRequest,
    current_user: str = Depends(get_current_user)
):
    """Update an LLM provider (super admin only)"""
    require_super_admin(current_user)
    from app import provider_service
    with database.get_db() as db:
        provider = provider_service.update_provider(db, provider_id, request)
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Provider not found"
            )
        return MessageResponse(message="Provider updated successfully")


@router.delete("/llm-providers/{provider_id}", response_model=MessageResponse)
async def delete_llm_provider(
    provider_id: int,
    current_user: str = Depends(get_current_user)
):
    """Delete an LLM provider (super admin only)"""
    require_super_admin(current_user)
    from app import provider_service
    with database.get_db() as db:
        success = provider_service.delete_provider(db, provider_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Provider not found"
            )
        return MessageResponse(message="Provider deleted successfully")


@router.get("/llm-providers/{provider_id}/models", response_model=List[dict])
async def get_provider_models(
    provider_id: int,
    current_user: str = Depends(get_current_user)
):
    """Fetch available models from the provider"""
    from app import provider_service
    with database.get_db() as db:
        provider = provider_service.get_provider_by_id(db, provider_id)
        if not provider:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Provider not found"
            )
        
        try:
            models = await provider_service.get_available_models(provider)
            # Return raw model data (usually list of objects or dicts)
            return [m.model_dump() if hasattr(m, 'model_dump') else m for m in models]
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to fetch models: {str(e)}"
            )


# ============================================================================
# Public Endpoints (No Authentication Required)
# ============================================================================

public_router = APIRouter(prefix="/api/public", tags=["public"])


@public_router.post("/channels/line/webhook")
async def line_messaging_webhook(request: Request):
    from app.messaging import get_line_client_from_db, handle_message as run_agent
    import asyncio as _asyncio

    body = await request.body()
    body_str = body.decode("utf-8")
    signature = request.headers.get("X-Line-Signature", "")

    client = get_line_client_from_db(lambda channel_type: database.get_channel_config(channel_type))
    if not client:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="LINE channel is not configured")

    if not client.validate_signature(body_str, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid LINE signature")

    events = client.parse_events(body_str, signature)

    # Process text events asynchronously
    for event in events:
        if event.get("message_type") != "text":
            continue
        reply_token = event.get("reply_token")
        user_id = event.get("user_id", "unknown")
        text = event.get("text", "")

        if reply_token and text:
            try:
                response_text = await run_agent("line", user_id, text)
                if response_text:
                    client.reply_text(reply_token, response_text)
            except Exception:
                pass  # Don't fail the webhook if one message fails

    return {
        "success": True,
        "channel": "line",
        "events_processed": len(events),
    }


@public_router.get("/channels/facebook/webhook")
async def facebook_messaging_verify(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    challenge = params.get("hub.challenge")
    verify_token = params.get("hub.verify_token")

    config = database.get_channel_config("facebook")
    expected_token = (config or {}).get("config", {}).get("verify_token")

    if mode == "subscribe" and challenge and expected_token and verify_token == expected_token:
        return Response(content=challenge, media_type="text/plain")

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid Facebook webhook verification token"
    )


@public_router.post("/channels/facebook/webhook")
async def facebook_messaging_webhook(request: Request):
    from app.messaging import get_facebook_client_from_db, handle_message as run_agent
    import asyncio as _asyncio

    payload = await request.json()

    client = get_facebook_client_from_db(lambda channel_type: database.get_channel_config(channel_type))
    if not client:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Facebook channel is not configured")

    events = client.parse_events(payload)

    for event in events:
        sender_id = event.get("sender_id")
        text = event.get("text")

        if event.get("message_type") != "text" or not text:
            continue
        if not sender_id:
            continue

        try:
            response_text = await run_agent("facebook", sender_id, text)
            if response_text:
                client.send_text(sender_id, response_text)
        except Exception:
            pass

    return {
        "success": True,
        "channel": "facebook",
        "entries_processed": len(events),
    }


# Team-scoped channel webhooks
@public_router.post("/teams/{team_slug}/channels/line/webhook")
async def team_line_webhook(team_slug: str, request: Request):
    """LINE webhook scoped to a specific Team Agent"""
    from app.messaging import get_line_client_from_db, handle_message as run_agent

    # Resolve team
    team = database.get_team_agent_by_slug(team_slug)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    body = await request.body()
    body_str = body.decode("utf-8")
    signature = request.headers.get("X-Line-Signature", "")

    client = get_line_client_from_db(database.get_channel_config, team_agent_id=team["id"])
    if not client:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="LINE channel is not configured")

    if not client.validate_signature(body_str, signature):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid LINE signature")

    events = client.parse_events(body_str, signature)
    team_agent_id = team["id"]

    for event in events:
        if event.get("message_type") != "text":
            continue
        reply_token = event.get("reply_token")
        user_id = event.get("user_id", "unknown")
        text = event.get("text", "")

        if reply_token and text:
            try:
                response_text = await run_agent("line", user_id, text, team_agent_id=team_agent_id)
                if response_text:
                    client.reply_text(reply_token, response_text)
            except Exception:
                pass

    return {
        "success": True,
        "channel": "line",
        "team": team_slug,
        "events_processed": len(events),
    }


@public_router.get("/teams/{team_slug}/channels/facebook/webhook")
async def team_facebook_verify(team_slug: str, request: Request):
    """Facebook webhook verification scoped to a specific Team Agent"""
    team = database.get_team_agent_by_slug(team_slug)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    params = request.query_params
    mode = params.get("hub.mode")
    challenge = params.get("hub.challenge")
    verify_token = params.get("hub.verify_token")

    config = database.get_channel_config("facebook", team_agent_id=team["id"])
    expected_token = (config or {}).get("config", {}).get("verify_token")

    if mode == "subscribe" and challenge and expected_token and verify_token == expected_token:
        return Response(content=challenge, media_type="text/plain")

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid Facebook webhook verification token"
    )


@public_router.post("/teams/{team_slug}/channels/facebook/webhook")
async def team_facebook_webhook(team_slug: str, request: Request):
    """Facebook webhook scoped to a specific Team Agent"""
    from app.messaging import get_facebook_client_from_db, handle_message as run_agent

    team = database.get_team_agent_by_slug(team_slug)
    if not team:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Team not found")

    body = await request.json()
    client = get_facebook_client_from_db(database.get_channel_config, team_agent_id=team["id"])
    if not client:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Facebook channel is not configured")

    events = client.parse_events(body)
    team_agent_id = team["id"]

    for event in events:
        if event.get("message_type") != "text":
            continue
        sender_id = event.get("sender_id")
        text = event.get("text", "")

        if sender_id and text:
            try:
                response_text = await run_agent("facebook", sender_id, text, team_agent_id=team_agent_id)
                if response_text:
                    client.send_text(sender_id, response_text)
            except Exception:
                pass

    return {
        "success": True,
        "channel": "facebook",
        "team": team_slug,
        "entries_processed": len(events),
    }


@public_router.get("/widget-config/{slug}")
async def get_widget_config_by_slug(slug: str):
    """
    Publicly accessible endpoint to get widget configuration by slug.
    This hides the API key from the frontend until the page loads.
    """
    key_data = database.get_api_key_by_slug(slug)
    
    if not key_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shortcut not found"
        )
        
    if not key_data.get("is_active"):
         raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Shortcut is inactive"
        )

    return {
        "apiKey": key_data["key"],
        "voice_response_enabled": key_data.get("voice_response_enabled", True),
        "team_agent_id": key_data.get("team_agent_id"),
        "channel_type": key_data.get("channel_type"),
    }
