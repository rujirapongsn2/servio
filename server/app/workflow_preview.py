"""Private, expiring workflow rehearsals; no channel or conversation persistence."""
import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
import json
import time
from uuid import uuid4

from agents import Runner, RunConfig
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app import database, default_chat_models
from app.auth import get_current_user
from app.orm_models import LLMProvider, Tool

TTL_SECONDS = 1800
MAX_SESSIONS = 100
MAX_USER_SESSIONS = 4
MAX_TURNS = 24
MAX_HISTORY_BYTES = 256_000
MAX_ACTIVE_RUNS = 4
RUN_TIMEOUT_SECONDS = 90
_sessions: dict[str, "PreviewSession"] = {}
_active_runs = 0
class PreviewRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def bounded_body(request: Request):
            size = 0
            chunks = []
            async for chunk in request.stream():
                size += len(chunk)
                if size > 160_000:
                    raise HTTPException(413, "Preview request is too large")
                chunks.append(chunk)
            request._body = b"".join(chunks)
            return await handler(request)
        return bounded_body


router = APIRouter(route_class=PreviewRoute)


class AgentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    instructions: str = Field(max_length=32_000)
    model: str = Field(min_length=1, max_length=100)
    llm_provider_id: int | None = Field(default=None, gt=0)
    tool_ids: list[int] = Field(default_factory=list, max_length=100)
    handoff_agent_ids: list[int] = Field(default_factory=list, max_length=100)
    is_fallback: bool = False


class DraftOverride(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_id: int = Field(gt=0)
    draft: AgentDraft


class CreatePreview(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_agent_id: int | None = Field(default=None, gt=0)
    drafts: list[DraftOverride] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def bounded_snapshot(self):
        if len({item.agent_id for item in self.drafts}) != len(self.drafts):
            raise ValueError("Duplicate agent draft")
        if len(self.model_dump_json().encode()) > 128_000:
            raise ValueError("Preview draft is too large")
        if sum(item.draft.is_fallback for item in self.drafts) > 1:
            raise ValueError("Select one fallback agent")
        return self


class PreviewMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=8000)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.message.strip():
            raise ValueError("Enter a message")
        return self


@dataclass
class PreviewSession:
    owner: str
    team_id: int
    target_agent_id: int | None
    agents: list[dict]
    agent: object
    expires_at: float
    blocked_tools: list[str]
    has_drafts: bool
    history: list = field(default_factory=list)
    turns: int = 0
    busy: bool = False
    task: asyncio.Task | None = None


def _require_admin(user, team_id):
    from app.admin_routes import require_team_access
    require_team_access(user, team_id, "admin")


def _prune():
    now = time.monotonic()
    for key, session in list(_sessions.items()):
        if not session.busy and session.expires_at <= now:
            del _sessions[key]


def _session(user, team_id, preview_id):
    _require_admin(user, team_id)
    _prune()
    session = _sessions.get(preview_id)
    if not session or session.owner != user or session.team_id != team_id or session.expires_at <= time.monotonic():
        raise HTTPException(404, "Preview expired or unavailable. Start a new preview.")
    return session


def _readonly_tool(tool):
    if tool["name"] in {"DateTimeTool", "WebSearchTool"}:
        return True
    config = json.loads(tool.get("config") or "{}")
    return (tool.get("type") == "okf_knowledge_graph" and config.get("type") == "okf_knowledge_graph"
            and isinstance(config.get("okf_bundle_id"), int))


def _validate_access(team_id, agents):
    current_members = {member["agent_id"] for member in (database.get_team_agent_by_id(team_id) or {}).get("members", [])}
    if not {agent["id"] for agent in agents}.issubset(current_members):
        raise HTTPException(409, "Team membership changed. Start a new preview.")
    with database.get_db() as db:
        for agent in agents:
            for tool in agent["tools"]:
                if not database._tool_available_to_team(db, tool["id"], team_id):
                    raise HTTPException(403, "A preview tool is no longer available to this team.")
            provider = agent.get("llm_provider")
            if provider:
                current = db.get(LLMProvider, provider["id"])
                if not current or not current.base_url or not current.api_key:
                    raise HTTPException(403, "A preview provider is no longer available.")
                if current.base_url != provider["base_url"] or current.api_key != provider["api_key"]:
                    raise HTTPException(409, "Provider configuration changed. Start a new preview.")


def _capture(team_id, request, saved_agents=None):
    team = deepcopy(database.get_team_agent_by_id(team_id))
    if not team:
        raise HTTPException(404, "Team Agent not found")
    agents = deepcopy(saved_agents if saved_agents is not None else database.get_all_agents(team_agent_id=team_id))
    if not agents:
        raise HTTPException(400, "Save an agent in this team before starting a preview.")
    if len(agents) > 32 or len(json.dumps(agents).encode()) > 512_000:
        raise HTTPException(400, "This team is too large for a private preview.")
    by_id = {agent["id"]: agent for agent in agents}
    if request.target_agent_id is not None and request.target_agent_id not in by_id:
        raise HTTPException(400, "Save the agent in this team before previewing it.")
    fallback = next((member["agent_id"] for member in team["members"] if member["role"] == "starting"), None)
    with database.get_db() as db:
        for item in request.drafts:
            if item.agent_id not in by_id:
                raise HTTPException(400, "Save the agent in this team before previewing it.")
            draft = item.draft
            if not draft.name.strip() or not draft.model.strip():
                raise HTTPException(400, "Agent name and model must not be empty")
            if item.agent_id in draft.handoff_agent_ids or not set(draft.handoff_agent_ids).issubset(by_id):
                raise HTTPException(400, "Handoffs must target another agent in this team")
            agent = by_id[item.agent_id]
            agent.update(name=draft.name.strip(), instructions=draft.instructions, model=draft.model.strip())
            agent["handoffs"] = [{"id": target, "name": by_id[target]["name"]} for target in draft.handoff_agent_ids]
            agent["tools"] = []
            for tool_id in set(draft.tool_ids):
                if not database._tool_available_to_team(db, tool_id, team_id):
                    raise HTTPException(400, "One or more tools are unavailable to this team")
                tool = db.get(Tool, tool_id)
                agent["tools"].append({"id": tool.id, "name": tool.name, "type": tool.type, "config": json.dumps(tool.config or {})})
            provider = db.get(LLMProvider, draft.llm_provider_id) if draft.llm_provider_id else None
            if draft.llm_provider_id and (not provider or not provider.base_url or not provider.api_key):
                raise HTTPException(400, "Select a configured LLM provider")
            agent["llm_provider"] = {"id": provider.id, "name": provider.name, "base_url": provider.base_url, "api_key": provider.api_key} if provider else None
            if draft.is_fallback:
                fallback = item.agent_id
    if any(item.agent_id == fallback and not item.draft.is_fallback for item in request.drafts):
        raise HTTPException(400, "Select a fallback agent before starting a preview")
    for member in team["members"]:
        member["role"] = "starting" if member["agent_id"] == fallback else "member"
    _validate_access(team_id, agents)
    return team, agents


def _build(team_id, team, agents, target_agent_id):
    from app.agent_config import get_runtime_starting_agent
    safe_agents = deepcopy(agents)
    blocked = set()
    for agent in safe_agents:
        allowed = []
        for tool in agent["tools"]:
            if _readonly_tool(tool):
                allowed.append(tool)
            else:
                blocked.add(tool["name"])
        agent["tools"] = allowed
    coordinator = get_runtime_starting_agent(team_id, captured_team=team, captured_agents=safe_agents)
    runtime_agents = list(coordinator.handoffs)
    for agent in runtime_agents:
        for tool in agent.tools:
            if not hasattr(tool, "on_invoke_tool"):
                continue
            invoke = tool.on_invoke_tool
            async def safe_invoke(context, arguments, invoke=invoke):
                try:
                    value = await invoke(context, arguments)
                    return "Knowledge search is temporarily unavailable." if isinstance(value, str) and value.startswith("Error searching OKF knowledge:") else value
                except Exception:
                    return "Preview tool is temporarily unavailable."
            tool.on_invoke_tool = safe_invoke
    if target_agent_id is not None:
        target = next((runtime for captured, runtime in zip(safe_agents, runtime_agents)
                       if captured["id"] == target_agent_id), None)
        if target is None:
            raise HTTPException(503, "Preview agent could not be prepared.")
        coordinator = target
    return coordinator, sorted(blocked)


@router.post("/team-agents/{team_id}/workflow/previews")
async def create_preview(team_id: int, request: CreatePreview, current_user: str = Depends(get_current_user)):
    _require_admin(current_user, team_id)
    _prune()
    if len(_sessions) >= MAX_SESSIONS or sum(session.owner == current_user for session in _sessions.values()) >= MAX_USER_SESSIONS:
        raise HTTPException(429, "Close an existing preview before starting another.")
    saved = {agent["id"]: agent for agent in database.get_all_agents(team_agent_id=team_id)}
    for item in request.drafts:
        if item.agent_id not in saved:
            raise HTTPException(400, "Save the agent in this team before previewing it.")
        await default_chat_models.validate_selection(item.draft.model, item.draft.llm_provider_id, saved[item.agent_id])
    team, agents = _capture(team_id, request, list(saved.values()))
    try:
        agent, blocked = _build(team_id, team, agents, request.target_agent_id)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Preview could not be prepared. Check agent configuration.")
    preview_id = str(uuid4())
    _sessions[preview_id] = PreviewSession(current_user, team_id, request.target_agent_id, agents, agent,
                                          time.monotonic() + TTL_SECONDS, blocked, bool(request.drafts))
    return {"id": preview_id, "target_agent_id": request.target_agent_id, "has_drafts": bool(request.drafts),
            "blocked_tools": blocked, "expires_in_seconds": TTL_SECONDS}


async def _run(session, message):
    from app.agent_config import start_tool_logging, get_tool_log, get_tool_citations
    from app.knowledge_image_presentations import hydrate_knowledge_images
    from app.knowledge_audio_presentations import hydrate_knowledge_media
    from app.local_video_rag import hydrate_knowledge_videos
    from app.product_presentations import parse_product_carousel

    history = deepcopy(session.history) + [{"role": "user", "content": message}]
    start_tool_logging()
    output = await Runner.run(session.agent, history, max_turns=12, run_config=RunConfig(tracing_disabled=True))
    calls, presentations = {}, {}
    for run_item in output.new_items:
        item = run_item.to_input_item()
        call_id = item.get("call_id")
        if item.get("type") == "function_call" and isinstance(call_id, str):
            bundle_id = next((getattr(tool, "_servio_knowledge_bundle_id", None)
                              for tool in run_item.agent.tools if getattr(tool, "name", None) == item.get("name")), None)
            calls[call_id] = bundle_id
        elif item.get("type") == "function_call_output" and isinstance(call_id, str):
            bundle_id = calls.pop(call_id, None)
            value = item.get("output")
            presentation = parse_product_carousel(value)
            if presentation is None and bundle_id is not None:
                presentation = hydrate_knowledge_images(value, session.team_id, bundle_id) or hydrate_knowledge_media(value, session.team_id, bundle_id) or hydrate_knowledge_videos(value, session.team_id, bundle_id)
            if presentation is not None and len(presentations) < 50:
                presentations[call_id] = presentation.model_dump(exclude_none=True)
    new_history = output.to_input_list()
    if session.expires_at <= time.monotonic():
        raise HTTPException(404, "Preview expired. Restart the preview.")
    if len(json.dumps(new_history, ensure_ascii=False).encode()) > MAX_HISTORY_BYTES:
        raise HTTPException(409, "Preview conversation is full. Start a new preview.")
    session.history, session.agent = new_history, output.last_agent
    session.turns += 1
    return {"response": str(output.final_output or "No response"), "agent_name": output.last_agent.name,
            "presentations": presentations, "tool_calls": get_tool_log(), "citations": get_tool_citations()}


@router.post("/team-agents/{team_id}/workflow/previews/{preview_id}/messages")
async def send_preview_message(team_id: int, preview_id: str, request: PreviewMessage,
                               current_user: str = Depends(get_current_user)):
    global _active_runs
    session = _session(current_user, team_id, preview_id)
    if session.busy:
        raise HTTPException(409, "Wait for the current preview reply.")
    if session.turns >= MAX_TURNS:
        raise HTTPException(409, "Preview conversation is full. Start a new preview.")
    if _active_runs >= MAX_ACTIVE_RUNS:
        raise HTTPException(429, "Previews are busy. Try again shortly.")
    _validate_access(team_id, session.agents)
    session.busy = True
    _active_runs += 1
    task = asyncio.create_task(_run(session, request.message))
    session.task = task
    def release(completed):
        global _active_runs
        session.busy = False
        session.task = None
        _active_runs -= 1
        if not completed.cancelled():
            completed.exception()
    try:
        result = await asyncio.wait_for(asyncio.shield(task), timeout=RUN_TIMEOUT_SECONDS)
        _require_admin(current_user, team_id)
        _validate_access(team_id, session.agents)
        return result
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        session.expires_at = time.monotonic()
        raise HTTPException(504, "Preview expired after taking too long. Restart the preview.")
    except Exception:
        raise HTTPException(503, "Preview could not complete. Try again or start a new preview.")
    finally:
        if task.done():
            release(task)
        else:
            session.expires_at = time.monotonic()
            task.add_done_callback(release)


@router.delete("/team-agents/{team_id}/workflow/previews/{preview_id}")
async def delete_preview(team_id: int, preview_id: str, current_user: str = Depends(get_current_user)):
    session = _session(current_user, team_id, preview_id)
    session.expires_at = time.monotonic()
    del _sessions[preview_id]
    return {"success": True}
