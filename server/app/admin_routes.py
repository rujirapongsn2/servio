from fastapi import APIRouter, Depends, HTTPException, status, Request, UploadFile, File, Response
import json
import os
import time
from typing import List
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
    TestFileStoreRequest,
    TestFileStoreResponse,
    VoIPProviderResponse,
    CreateVoIPProviderRequest,
    UpdateVoIPProviderRequest,
)

router = APIRouter(prefix="/api/admin", tags=["admin"])


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


@router.get("/system-info", response_model=SystemInfoResponse)
async def system_info(request: Request, current_user: str = Depends(get_current_user)):
    """Return dynamic system information for the Admin UI."""
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
    tools = db.get_all_tools()

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


# File Store endpoints
@router.get("/file-stores", response_model=List[FileStoreResponse])
async def get_file_stores(current_user: str = Depends(get_current_user)):
    """Get all file stores"""
    stores = database.get_all_file_stores()
    return stores


@router.post("/file-stores", response_model=MessageResponse)
async def create_file_store(
    request: CreateFileStoreRequest,
    current_user: str = Depends(get_current_user)
):
    """Create a new file search store"""
    try:
        from app.gemini_service import GeminiFileSearchService

        # Initialize Gemini service
        service = GeminiFileSearchService()

        # Create Gemini store
        result = service.create_store(display_name=request.display_name)
        gemini_store_id = result["store_id"]

        # Generate unique name from display name
        name = request.display_name.lower().replace(" ", "_")

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
            database.create_custom_tool(tool_name, tool_config, icon="FileSearch")

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
        temp_path = temp_dir / f"upload_{int(time.time())}_{file.filename}"

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
    """Update an existing VoIP provider"""
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
    current_user: str = Depends(get_current_user)
):
    """
    Get analytics summary for dashboard

    Args:
        period: 'today', 'week', 'month', or 'all'
    """
    try:
        summary = database.get_analytics_summary(period)
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
                ca.overall_sentiment,
                ca.sentiment_score,
                ca.primary_topic,
                ca.resolution_quality,
                ca.urgency_level
            FROM conversations c
            LEFT JOIN conversation_analytics ca ON c.id = ca.conversation_id
            WHERE 1=1
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
        count_query = "SELECT COUNT(*) FROM conversations c LEFT JOIN conversation_analytics ca ON c.id = ca.conversation_id WHERE 1=1"
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
    current_user: str = Depends(get_current_user)
):
    """
    Get detailed conversation information including messages and analytics
    """
    try:
        conn = database.get_db_connection()
        cursor = conn.cursor()

        # Get conversation metadata (PostgreSQL syntax)
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
    current_user: str = Depends(get_current_user)
):
    """
    Get analytics trends over time for charts

    Args:
        period: 'week' or 'month'
    """
    try:
        conn = database.get_db_connection()
        cursor = conn.cursor()

        # Determine number of days
        days = 7 if period == "week" else 30

        # Daily conversation volume (PostgreSQL syntax)
        cursor.execute(
            f"""
            SELECT DATE(started_at) as date, COUNT(*) as count
            FROM conversations
            WHERE DATE(started_at) >= CURRENT_DATE - INTERVAL '{days} days'
            GROUP BY DATE(started_at)
            ORDER BY date ASC
            """
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
            AND ca.sentiment_score IS NOT NULL
            GROUP BY DATE(c.started_at)
            ORDER BY date ASC
            """
        )
        sentiment_rows = cursor.fetchall()
        daily_sentiment = [{"date": str(row["date"]) if row["date"] else None, "sentiment": round(row["avg_sentiment"], 2) if row["avg_sentiment"] else 0} for row in sentiment_rows]

        # Agent performance (PostgreSQL JSON array access)
        cursor.execute(
            """
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
            GROUP BY c.agents_involved->>0
            HAVING COUNT(*) >= 1
            ORDER BY total_conversations DESC
            LIMIT 10
            """
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
