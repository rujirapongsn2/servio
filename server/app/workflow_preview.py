"""Private, expiring workflow rehearsals; no channel or conversation persistence."""
import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
import json
import time
import tempfile
import base64
from pathlib import Path
from uuid import uuid4
from typing import Callable

from agents import Runner
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app import database, default_chat_models
from app.auth import get_current_user
from app.orm_models import LLMProvider, Tool
from app.tool_execution import protect_tools, redact
from app.chat_inputs import ChatInput, prepare_input
from app.a2ui_discovery import ActionRequest
from app.chat_presentations import private_presenter, present_result, current_turn_presentations
from app.agent_execution import (execution_scope, run_agent, SESSION_IDLE_SECONDS, MAX_HISTORY_BYTES,
                                  MAX_ACTIVE_RUNS, TIMEOUT_SECONDS, MAX_MESSAGE_CHARS)

TTL_SECONDS = SESSION_IDLE_SECONDS
MAX_SESSIONS = 100
MAX_USER_SESSIONS = 4
RUN_TIMEOUT_SECONDS = TIMEOUT_SECONDS
MAX_REQUEST_BYTES = 72 * 1024 * 1024
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
                if size > MAX_REQUEST_BYTES:
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
    drafts: list[DraftOverride] = Field(default_factory=list, max_length=2048)
    confirm_real_tools: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def bounded_snapshot(self):
        if len({item.agent_id for item in self.drafts}) != len(self.drafts):
            raise ValueError("Duplicate agent draft")
        if len(self.model_dump_json().encode()) > MAX_REQUEST_BYTES:
            raise ValueError("Preview draft is too large")
        if sum(item.draft.is_fallback for item in self.drafts) > 1:
            raise ValueError("Select one fallback agent")
        return self


class PreviewMessage(ChatInput):
    action: ActionRequest | None = None


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
    check_access: Callable[[], None]
    secrets: set[str] = field(default_factory=set)
    session_id: str = field(default_factory=lambda: str(uuid4()))
    presenter: object = None
    media_directory: object = field(default_factory=lambda: tempfile.TemporaryDirectory(prefix='servio-private-'))
    media: dict = field(default_factory=dict)
    last_reply: dict | None = None
    secure_media: bool = False
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
            session.media_directory.cleanup()
            del _sessions[key]


def _session(user, team_id, preview_id):
    _require_admin(user, team_id)
    _prune()
    session = _sessions.get(preview_id)
    if not session or session.owner != user or session.team_id != team_id or session.expires_at <= time.monotonic():
        raise HTTPException(404, "Preview expired or unavailable. Start a new preview.")
    return session


from app.runtime_access import validate_runtime_access as _validate_access


def _capture(team_id, request, saved_agents=None):
    team = deepcopy(database.get_team_agent_by_id(team_id))
    if not team:
        raise HTTPException(404, "Team Agent not found")
    agents = deepcopy(saved_agents if saved_agents is not None else database.get_all_agents(team_agent_id=team_id))
    if not agents:
        raise HTTPException(400, "Save an agent in this team before starting a preview.")
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


def _build(team_id, team, agents, target_agent_id, check):
    from app.agent_config import get_runtime_starting_agent
    coordinator = get_runtime_starting_agent(team_id, captured_team=team, captured_agents=agents)
    runtime_agents = list(coordinator.handoffs)
    secrets = protect_tools([coordinator, *runtime_agents], agents, check)
    if target_agent_id is not None:
        target = next((runtime for captured, runtime in zip(agents, runtime_agents)
                       if captured["id"] == target_agent_id), None)
        if target is None:
            raise HTTPException(503, "Preview agent could not be prepared.")
        coordinator = target
    return coordinator, secrets


@router.post("/team-agents/{team_id}/workflow/previews")
async def create_preview(team_id: int, request: CreatePreview, response: Response, http_request: Request, current_user: str = Depends(get_current_user)):
    _require_admin(current_user, team_id)
    if request.confirm_real_tools is not True:
        raise HTTPException(428, "Confirm that Private Chat can execute real tools and change external data before starting a session.")
    _prune()
    if len(_sessions) >= MAX_SESSIONS or sum(session.owner == current_user for session in _sessions.values()) >= MAX_USER_SESSIONS:
        raise HTTPException(429, "Close an existing preview before starting another.")
    saved = {agent["id"]: agent for agent in database.get_all_agents(team_agent_id=team_id)}
    for item in request.drafts:
        if item.agent_id not in saved:
            raise HTTPException(400, "Save the agent in this team before previewing it.")
        await default_chat_models.validate_selection(item.draft.model, item.draft.llm_provider_id, saved[item.agent_id])
    team, agents = _capture(team_id, request, list(saved.values()))
    def check():
        _require_admin(current_user, team_id)
        _validate_access(team_id, agents)
    try:
        agent, secrets = _build(team_id, team, agents, request.target_agent_id, check)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "Preview could not be prepared. Check agent configuration.")
    preview_id = str(uuid4())
    _sessions[preview_id] = PreviewSession(current_user, team_id, request.target_agent_id, agents, agent,
                                          time.monotonic() + TTL_SECONDS, [], bool(request.drafts), check, secrets)
    _sessions[preview_id].session_id = preview_id
    _sessions[preview_id].secure_media = http_request.url.scheme == 'https'
    _media_cookie(_sessions[preview_id], response)
    return {"id": preview_id, "target_agent_id": request.target_agent_id, "has_drafts": bool(request.drafts),
            "blocked_tools": [], "expires_in_seconds": TTL_SECONDS, "real_tools_confirmed": True}


async def _run_text(session, message, context=None):
    from app.agent_config import start_tool_logging

    history = deepcopy(session.history) + [{"role": "user", "content": message}]
    start_tool_logging()
    from app.agent_execution import knowledge_context
    evidence = knowledge_context(context)
    with execution_scope(session.agent, session.check_access) as events:
        output = await run_agent(session.agent, history + ([evidence] if evidence else []), session.check_access)
    presenter = private_presenter(session)
    presenter.history = history.copy()
    presentations, surfaces = await present_result(presenter, output)
    new_history = [item for item in output.to_input_list() if evidence is None or item != evidence]
    if session.expires_at <= time.monotonic():
        raise HTTPException(404, "Preview expired. Restart the preview.")
    if len(json.dumps(new_history, ensure_ascii=False).encode()) > MAX_HISTORY_BYTES:
        raise HTTPException(409, "Preview conversation is full. Start a new preview.")
    session.history, session.agent = redact(new_history, session.secrets), output.last_agent
    session.turns += 1
    session.expires_at = time.monotonic() + TTL_SECONDS
    used_calls = {item.to_input_item().get('call_id') for item in output.new_items}
    citations = []
    for call_id, (_, result) in presenter.answers.results.items():
        if call_id in used_calls:
            for source in result.sources:
                if source.model_dump() not in citations:
                    citations.append(source.model_dump())
    return redact({"response": str(output.final_output or "No response"), "agent_name": output.last_agent.name,
            "presentations": presentations, "tool_calls": events, "citations": citations,
            "a2ui": surfaces, "expires_in_seconds": TTL_SECONDS, "status": "completed"}, session.secrets)


def _image_bundles(session, team_id):
    if team_id != session.team_id:
        return set()
    session.check_access()
    from app.orm_models import OKFBundle
    from app.okf_service import _bundle_available_to_team
    result = set()
    with database.get_db() as db:
        for agent in session.agents:
            for tool in agent['tools']:
                config = json.loads(tool.get('config') or '{}')
                bundle_id = config.get('okf_bundle_id')
                if tool['type'] == 'okf_knowledge_graph' and type(bundle_id) is int:
                    bundle = db.get(OKFBundle, bundle_id)
                    if bundle and bundle.status == 'ready' and _bundle_available_to_team(db, bundle, team_id):
                        result.add(bundle_id)
    return result


async def _run(session, request):
    from app.knowledge_image_search import runtime_bundle_scope
    token = runtime_bundle_scope.set(lambda team_id: _image_bundles(session, team_id))
    try:
        return await _run_input(session, request)
    finally:
        runtime_bundle_scope.reset(token)


async def _run_input(session, request):
    if request.action is not None:
        return await _run_action(session, request.action)
    from app.chat_media import video, speech
    from app.knowledge_image_search import ImageSearchRequest, assigned_bundles
    from app.knowledge_video import build_video_card
    presenter = private_presenter(session)
    with execution_scope(session.agent, session.check_access):
        if request.image_search and assigned_bundles(session.team_id):
            attachment = request.attachments[0]
            image = ImageSearchRequest(type='knowledge.image.search', request_id=uuid4().hex,
                image={'mime': attachment.mime, 'base64': attachment.base64}, query=request.message)
            generation = presenter.image_search_session.begin(image.request_id)
            await presenter.search_knowledge_image(image, generation)
            session.check_access()
            session.history = presenter.history
            summary = next((item.get('content', '') for item in reversed(session.history)
                            if item.get('role') == 'assistant'), 'Image search completed')
            if isinstance(summary, list):
                summary = '\n'.join(part.get('text', '') for part in summary if isinstance(part, dict))
            session.expires_at = time.monotonic() + TTL_SECONDS
            presentations, surfaces = current_turn_presentations(presenter)
            return {'response': summary, 'agent_name': session.agent.name, 'status': 'completed',
                    'presentations': presentations, 'tool_calls': [], 'citations': [],
                    'a2ui': surfaces, 'expires_in_seconds': TTL_SECONDS}
        videos = [item for item in request.attachments if item.kind == 'video']
        if len(videos) > 1:
            raise ValueError('Attach one video per request')
        remaining = request.model_copy(update={'attachments': [item for item in request.attachments if item.kind != 'video']})
        content = await prepare_input(remaining)
        manifests = []
        for attachment in videos:
            directory = Path(session.media_directory.name) / uuid4().hex
            directory.mkdir()
            context, manifest = await video(attachment, directory)
            content = [{'type': 'input_text', 'text': content}] if isinstance(content, str) else content
            content.append({'type': 'input_text', 'text': context})
            metadata = manifest['video']
            asset = metadata['asset_id']
            session.media[asset] = (directory / manifest['video_asset_path'], attachment.mime)
            for frame, path in manifest['video_frame_paths'].items():
                session.media[frame] = (directory / path, 'image/jpeg')
            card = build_video_card(metadata, title=attachment.name, source_label=attachment.name,
                media_url=_media_url(session, asset), frame_url=lambda frame: _media_url(session, frame))
            manifests.append(card)
        response = await _run_text(session, content)
        if manifests:
            response['presentations']['uploaded_video'] = {'type': 'knowledge_video', 'version': 1,
                'response': response['response'], 'videos': manifests}
        if request.speak:
            try:
                data = await speech(response['response'])
                asset = uuid4().hex * 2
                path = Path(session.media_directory.name) / (asset + '.wav'); path.write_bytes(data)
                session.media[asset] = (path, 'audio/wav')
                response['audio_url'] = _media_url(session, asset)
            except Exception:
                response['media_error'] = 'Speech output is unavailable; the text response is retained.'
        return response


def _media_url(session, asset):
    import jwt
    from app.auth import SECRET_KEY, ALGORITHM
    token = jwt.encode({'purpose': 'private-chat-media', 'owner': session.owner,
        'team': session.team_id, 'session': session.session_id, 'asset': asset,
        'exp': int(time.time()) + TTL_SECONDS}, SECRET_KEY, algorithm=ALGORITHM)
    return f'/api/admin/private-chat-media/{session.session_id}/{asset}?token={token}'


def _media_cookie(session, response):
    if response is None:
        return
    import jwt
    from app.auth import SECRET_KEY, ALGORITHM
    value = jwt.encode({'purpose': 'private-chat-session', 'session': session.session_id,
        'owner': session.owner, 'exp': int(time.time()) + TTL_SECONDS}, SECRET_KEY, algorithm=ALGORITHM)
    response.set_cookie('servio_private_' + session.session_id, value, httponly=True,
        samesite='strict', secure=session.secure_media, max_age=TTL_SECONDS, path=f'/api/admin/private-chat-media/{session.session_id}')


@router.get('/private-chat-media/{preview_id}/{asset}')
async def private_media(preview_id: str, asset: str, token: str, request: Request):
    import jwt
    from fastapi.responses import FileResponse
    from app.auth import SECRET_KEY, ALGORITHM
    try:
        claims = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        browser = jwt.decode(request.cookies.get('servio_private_' + preview_id, ''), SECRET_KEY, algorithms=[ALGORITHM])
        if browser.get('purpose') != 'private-chat-session' or browser.get('session') != preview_id or browser.get('owner') != claims.get('owner'):
            raise ValueError()
        authorization = request.headers.get('authorization', '')
        if authorization:
            caller = jwt.decode(authorization.removeprefix('Bearer '), SECRET_KEY, algorithms=[ALGORITHM])
            if caller.get('sub') != claims.get('owner'):
                raise ValueError()
        if claims['purpose'] != 'private-chat-media' or claims['session'] != preview_id or claims['asset'] != asset:
            raise ValueError()
        session = _session(claims['owner'], claims['team'], preview_id)
        session.check_access()
        path, mime = session.media[asset]
        return FileResponse(path, media_type=mime)
    except (jwt.PyJWTError, ValueError, KeyError):
        raise HTTPException(404, 'Private media is unavailable') from None



@router.post("/team-agents/{team_id}/workflow/previews/{preview_id}/messages")
async def send_preview_message(team_id: int, preview_id: str, request: PreviewMessage,
                               current_user: str = Depends(get_current_user), response: Response = None):
    global _active_runs
    session = _session(current_user, team_id, preview_id)
    if session.busy:
        raise HTTPException(409, "Wait for the current preview reply.")
    if _active_runs >= MAX_ACTIVE_RUNS:
        raise HTTPException(429, "Previews are busy. Try again shortly.")
    _validate_access(team_id, session.agents)
    session.busy = True
    _active_runs += 1
    async def execute():
        response = await _run(session, request)
        response['request_id'] = request.request_id
        session.last_reply = response
        return response
    task = asyncio.create_task(execute())
    session.task = task
    def release(completed):
        global _active_runs
        session.busy = False
        session.task = None
        if session.expires_at <= time.monotonic():
            session.media_directory.cleanup()
        _active_runs -= 1
        if not completed.cancelled():
            completed.exception()
    try:
        result = await asyncio.wait_for(asyncio.shield(task), timeout=RUN_TIMEOUT_SECONDS)
        _require_admin(current_user, team_id)
        _validate_access(team_id, session.agents)
        _media_cookie(session, response)
        return result
    except HTTPException:
        raise
    except asyncio.TimeoutError:
        raise HTTPException(504, "Response is still processing. Do not resend operations; wait for completion and check external systems.")
    except Exception:
        raise HTTPException(503, "Preview could not complete. Try again or start a new preview.")
    finally:
        if task.done():
            release(task)
        else:
            task.add_done_callback(release)


async def _run_action(session, request):
    team_id = session.team_id
    presenter = private_presenter(session)
    action = request.action
    try:
        original = presenter.discovery.require(action.surfaceId)
        if action.name == 'discovery.refine':
            image = original.model_copy(update={'request_id': request.request_id, 'refinement': action.context})
            generation = presenter.image_search_session.begin(request.request_id)
            await presenter.search_knowledge_image(image, generation, action.surfaceId)
            session.check_access()
            session.history = presenter.history
            return {'response': '', 'agent_name': session.agent.name, 'status': 'completed',
                'presentations': presenter.presentations, 'a2ui': presenter.discovery.snapshots,
                'tool_calls': [], 'citations': [], 'expires_in_seconds': TTL_SECONDS}
        from app.knowledge_image_search import KnowledgeInquiryRequest, resolve_inquiry
        inquiry = KnowledgeInquiryRequest(type='knowledge.product.inquire',
            message_id=action.surfaceId, card_id=action.context.card_id)
        reference = presenter.image_search_session.reference(inquiry)
        message, context = await asyncio.to_thread(resolve_inquiry, team_id, reference)
    except (ValueError, OSError, KeyError):
        raise HTTPException(409, 'This product reference is unavailable; search again') from None
    return await _run_text(session, message, context)


@router.post('/team-agents/{team_id}/workflow/previews/{preview_id}/actions')
async def private_action(team_id: int, preview_id: str, request: ActionRequest,
                         current_user: str = Depends(get_current_user)):
    return await send_preview_message(team_id, preview_id,
        PreviewMessage(message='Product action', action=request), current_user)


@router.get('/team-agents/{team_id}/workflow/previews/{preview_id}')
async def preview_status(team_id: int, preview_id: str, current_user: str = Depends(get_current_user)):
    session = _session(current_user, team_id, preview_id)
    session.check_access()
    return {'busy': session.busy, 'reply': session.last_reply if not session.busy else None, 'expires_in_seconds': max(1, int(session.expires_at-time.monotonic()))}


@router.delete("/team-agents/{team_id}/workflow/previews/{preview_id}")
async def delete_preview(team_id: int, preview_id: str, current_user: str = Depends(get_current_user)):
    session = _session(current_user, team_id, preview_id)
    session.expires_at = time.monotonic()
    del _sessions[preview_id]
    if not session.busy:
        session.media_directory.cleanup()
    return {"success": True}
