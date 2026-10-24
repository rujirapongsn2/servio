"""Team-scoped workflow snapshots and transactional agent edits."""
import hashlib
import json
import math
from urllib.parse import urlsplit
from datetime import datetime
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app import database
from app.model_settings import default_agent_model
from app.models import CreateWorkflowAgentRequest, CreateWorkflowToolRequest, UpdateWorkflowAgentRequest, UpdateWorkflowMembersRequest, DeleteWorkflowAgentRequest
from app.orm_models import Admin, TeamToolAssignment, WorkflowCreationReceipt, Agent, AgentHandoff, AgentTool, LLMProvider, OKFBundle, TeamAgent, TeamAgentMember, TeamUserMembership, Tool


class WorkflowConflict(ValueError):
    pass


def get_snapshot(team_id: int) -> dict[str, Any] | None:
    with database.get_db() as db:
        team = db.get(TeamAgent, team_id)
        if not team:
            return None
        members = db.query(TeamAgentMember).filter_by(team_agent_id=team_id).order_by(TeamAgentMember.sort_order, TeamAgentMember.agent_id).all()
        member_ids = {member.agent_id for member in members}
        agents = db.query(Agent).options(selectinload(Agent.tools), selectinload(Agent.handoff_to)).filter(Agent.id.in_(member_ids)).all()
        by_id = {agent.id: agent for agent in agents}
        counts = dict(db.query(TeamAgentMember.agent_id, func.count()).filter(TeamAgentMember.agent_id.in_(member_ids)).group_by(TeamAgentMember.agent_id).all())
        tools = [tool for tool in db.query(Tool).order_by(Tool.name).all() if database._tool_available_to_team(db, tool.id, team_id)]
        knowledge_tools = [tool for tool in tools if tool.type == "okf_knowledge_graph"
                           and isinstance(tool.config, dict) and isinstance(tool.config.get("okf_bundle_id"), int)]
        bundle_ids = {tool.config["okf_bundle_id"] for tool in knowledge_tools}
        knowledge_names = dict(db.query(OKFBundle.id, OKFBundle.display_name).filter(OKFBundle.id.in_(bundle_ids)).all())
        display_names = {tool.id: knowledge_names.get(tool.config["okf_bundle_id"], tool.name) for tool in knowledge_tools}
        return {
            "team_id": team.id,
            "default_agent_model": default_agent_model(),
            "team_name": team.name,
            "fallback_agent_id": next((member.agent_id for member in members if member.role == "starting"), None),
            "agents": [{
                "id": agent.id, "name": agent.name, "instructions": agent.instructions,
                "model": agent.model, "llm_provider_id": agent.llm_provider_id,
                "tool_ids": [tool.id for tool in agent.tools],
                "handoff_agent_ids": [target.id for target in agent.handoff_to if target.id in member_ids],
                "shared": counts[agent.id] > 1,
                "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
            } for member in members if (agent := by_id.get(member.agent_id))],
            "tools": [{"id": tool.id, "name": display_names.get(tool.id, tool.name), "type": tool.type} for tool in tools],
            "providers": [{"id": provider.id, "name": provider.name} for provider in db.query(LLMProvider).order_by(LLMProvider.name)],
        }


def update_workflow_agent(team_id: int, agent_id: int, request: UpdateWorkflowAgentRequest) -> int:
    with database.get_db() as db:
        team = _lock_team(db, team_id)
        agent = db.query(Agent).filter_by(id=agent_id).with_for_update().first()
        member = db.query(TeamAgentMember).filter_by(team_agent_id=team_id, agent_id=agent_id).first()
        if not team or not agent or not member:
            raise LookupError("Agent not found in this Team Agent")
        if db.query(TeamAgentMember).filter_by(agent_id=agent_id).count() > 1:
            raise WorkflowConflict("Shared agents are read-only. Remove sharing before editing this agent.")
        actual_updated_at = agent.updated_at.isoformat() if agent.updated_at else None
        if request.expected_updated_at != actual_updated_at:
            raise WorkflowConflict("This agent changed since you opened it. Reload the workflow before saving.")
        member_ids = set(database._team_member_agent_ids(db, team_id))
        name, model, tool_ids, handoff_ids = _validate_agent(db, team_id, request, member_ids, agent_id)
        if member.role == "starting" and not request.is_fallback:
            raise ValueError("Select another agent as fallback before clearing this fallback")
        if request.is_fallback and member.role != "starting":
            fallback = db.query(TeamAgentMember).filter_by(team_agent_id=team_id, role="starting").first()
            actual_fallback_id = fallback.agent_id if fallback else None
            if actual_fallback_id != request.expected_fallback_agent_id:
                raise WorkflowConflict("The team fallback changed. Reload the workflow before saving.")
        if request.is_fallback:
            db.query(TeamAgentMember).filter_by(team_agent_id=team_id, role="starting").update({"role": "member"}, synchronize_session="fetch")
            db.flush()
            member.role = "starting"
        agent.name, agent.instructions, agent.model = name, request.instructions, model
        agent.llm_provider_id = request.llm_provider_id
        agent.updated_at = datetime.utcnow()
        db.query(AgentTool).filter_by(agent_id=agent_id).delete(synchronize_session=False)
        db.add_all([AgentTool(agent_id=agent_id, tool_id=tool_id) for tool_id in tool_ids])
        db.query(AgentHandoff).filter(AgentHandoff.from_agent_id == agent_id, AgentHandoff.to_agent_id.in_(member_ids)).delete(synchronize_session=False)
        db.add_all([AgentHandoff(from_agent_id=agent_id, to_agent_id=target) for target in handoff_ids])
        return agent_id


def _validate_agent(db, team_id, request, member_ids, agent_id=None):
    name, model = request.name.strip(), request.model.strip()
    if not name or not model:
        raise ValueError("Agent name and model must not be empty")
    if request.llm_provider_id is not None:
        provider = db.get(LLMProvider, request.llm_provider_id)
        if not provider or not provider.base_url or not provider.api_key:
            raise ValueError("Select a configured LLM provider")
    handoff_ids = set(request.handoff_agent_ids)
    if agent_id in handoff_ids or not handoff_ids.issubset(member_ids):
        raise ValueError("Handoffs must target another agent in this team")
    tool_ids = set(request.tool_ids)
    datetime_tool = db.query(Tool).filter_by(name="DateTimeTool").first()
    if datetime_tool and database._tool_available_to_team(db, datetime_tool.id, team_id):
        tool_ids.add(datetime_tool.id)
    if any(not database._tool_available_to_team(db, tool_id, team_id) for tool_id in tool_ids):
        raise ValueError("One or more tools are not available to this Team Agent")
    return name, model, tool_ids, handoff_ids


def _lock_team(db, team_id):
    if db.bind.dialect.name == "sqlite":
        db.execute(text("BEGIN IMMEDIATE"))
    team = db.query(TeamAgent).filter_by(id=team_id).with_for_update().first()
    if not team:
        raise LookupError("Team Agent not found")
    return team


def _creation_replay(db, team_id, request, kind):
    payload = request.model_dump(mode="json", exclude={"request_id"})
    fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    receipt = db.get(WorkflowCreationReceipt, (team_id, str(request.request_id)))
    if receipt:
        if receipt.payload_hash != fingerprint or receipt.resource_kind != kind:
            raise WorkflowConflict("This creation request was already used with different data")
        if kind == "agent":
            exists = db.get(Agent, receipt.resource_id) and db.get(TeamAgentMember, (team_id, receipt.resource_id))
        else:
            tool = db.get(Tool, receipt.resource_id)
            exists = tool and tool.owner_team_agent_id == team_id
        if not exists:
            raise WorkflowConflict("The resource from this creation request is no longer available")
        return receipt.resource_id, fingerprint
    return None, fingerprint


def _record_creation(db, team_id, request_id, kind, resource_id, fingerprint):
    db.add(WorkflowCreationReceipt(team_agent_id=team_id, request_id=str(request_id), resource_kind=kind,
                                   resource_id=resource_id, payload_hash=fingerprint))


def create_workflow_agent(team_id: int, request: CreateWorkflowAgentRequest) -> int:
    with database.get_db() as db:
        _lock_team(db, team_id)
        replay_id, fingerprint = _creation_replay(db, team_id, request, "agent")
        if replay_id is not None:
            return replay_id
        members = db.query(TeamAgentMember).filter_by(team_agent_id=team_id).all()
        member_ids = {member.agent_id for member in members}
        name, model, tool_ids, handoff_ids = _validate_agent(db, team_id, request, member_ids)
        fallback = next((member.agent_id for member in members if member.role == "starting"), None)
        if request.is_fallback and fallback != request.expected_fallback_agent_id:
            raise WorkflowConflict("The team fallback changed. Reload the workflow before saving.")
        is_fallback = request.is_fallback or not members
        if is_fallback:
            db.query(TeamAgentMember).filter_by(team_agent_id=team_id, role="starting").update({"role": "member"}, synchronize_session="fetch")
            db.flush()
        agent = Agent(name=name, instructions=request.instructions, model=model,
                      llm_provider_id=request.llm_provider_id, is_starting_agent=False)
        db.add(agent)
        db.flush()
        order = max((member.sort_order for member in members), default=-1) + 1
        db.add(TeamAgentMember(team_agent_id=team_id, agent_id=agent.id,
                               role="starting" if is_fallback else "member", sort_order=order))
        db.add_all([AgentTool(agent_id=agent.id, tool_id=tool_id) for tool_id in tool_ids])
        db.add_all([AgentHandoff(from_agent_id=agent.id, to_agent_id=target) for target in handoff_ids])
        _record_creation(db, team_id, request.request_id, "agent", agent.id, fingerprint)
        return agent.id


def _validate_tool_config(config):
    from app.custom_api import validate_custom_api_config

    kind = config.get("type", "custom_api")
    if kind not in {"custom_api", "mcp_streamable_http"}:
        raise ValueError("Choose a Custom API or MCP tool")
    endpoint = config.get("endpoint")
    try:
        url = urlsplit(endpoint) if isinstance(endpoint, str) else None
        if (not url or url.scheme not in {"http", "https"} or not url.hostname
                or url.username is not None or url.password is not None or url.fragment
                or any(c.isspace() or ord(c) < 32 for c in endpoint)):
            raise ValueError()
        _ = url.port
    except ValueError:
        raise ValueError("Enter a valid HTTP or HTTPS endpoint") from None
    timeout = config.get("timeout_seconds", 60)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Enter a positive timeout")
    token = config.get("auth_token", "")
    if not isinstance(token, str) or any(c in token for c in "\r\n"):
        raise ValueError("Invalid authentication token")
    validate_custom_api_config(config)
    if kind == "custom_api" and config.get("method", "POST") not in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}:
        raise ValueError("Invalid API method")
    if kind == "mcp_streamable_http":
        if config.get("transport", "streamable_http") not in {"streamable_http", "sse"}:
            raise ValueError("Invalid MCP transport")
        if config.get("auth_mode", "bearer") not in {"bearer", "query", "header", "none"}:
            raise ValueError("Invalid MCP authentication mode")
        tools = config.get("tools", [])
        if not isinstance(tools, list) or any(not isinstance(name, str) or not name.strip() for name in tools):
            raise ValueError("Invalid MCP tool names")
    return kind


def create_workflow_tool(team_id: int, request: CreateWorkflowToolRequest, current_user: str) -> int:
    with database.get_db() as db:
        _lock_team(db, team_id)
        replay_id, fingerprint = _creation_replay(db, team_id, request, "tool")
        if replay_id is not None:
            return replay_id
        name = request.name.strip()
        if not name:
            raise ValueError("Tool name must not be empty")
        kind = _validate_tool_config(request.config)
        if db.query(Tool).filter_by(name=name).first():
            raise WorkflowConflict("A tool with this name already exists")
        creator = db.query(Admin).filter_by(username=current_user).first()
        tool = Tool(name=name, type=kind, config=request.config, owner_team_agent_id=team_id,
                    visibility="team", created_by_admin_id=creator.id if creator else None)
        db.add(tool)
        try:
            db.flush()
        except IntegrityError:
            raise WorkflowConflict("Unable to create tool. Choose a unique tool name and retry.") from None
        db.add(TeamToolAssignment(team_agent_id=team_id, tool_id=tool.id, relationship="owned"))
        _record_creation(db, team_id, request.request_id, "tool", tool.id, fingerprint)
        return tool.id


def _accessible_team_ids(db, username):
    if not db.query(TeamUserMembership).first():
        return None
    admin = db.query(Admin).filter_by(username=username).first()
    if not admin:
        return set()
    if admin.is_super_admin:
        return None
    return {membership.team_agent_id for membership in db.query(TeamUserMembership).filter_by(admin_id=admin.id)
            if database.ROLE_RANK.get(membership.role, 0) >= database.ROLE_RANK["viewer"]}


def get_member_options(team_id: int, current_user: str):
    with database.get_db() as db:
        if not db.get(TeamAgent, team_id):
            raise LookupError("Team Agent not found")
        accessible = _accessible_team_ids(db, current_user)
        memberships = db.query(TeamAgentMember).all()
        eligible = {member.agent_id for member in memberships
                    if member.team_agent_id == team_id or accessible is None or member.team_agent_id in accessible}
        counts = {}
        for member in memberships:
            counts[member.agent_id] = counts.get(member.agent_id, 0) + 1
        agents = db.query(Agent.id, Agent.name, Agent.model).order_by(Agent.name, Agent.id)
        if accessible is not None:
            agents = agents.filter(Agent.id.in_(eligible))
        return {"agents": [{"id": agent.id, "name": agent.name, "model": agent.model,
                            "shared": counts.get(agent.id, 0) > 1, "membership_count": counts.get(agent.id, 0)}
                           for agent in agents]}


def _membership_state(db, team_id):
    members = db.query(TeamAgentMember).filter_by(team_agent_id=team_id).order_by(TeamAgentMember.sort_order, TeamAgentMember.agent_id).all()
    return [member.agent_id for member in members], next((member.agent_id for member in members if member.role == "starting"), None)


def _check_membership_expected(actual, request):
    if actual != (request.expected_member_agent_ids, request.expected_fallback_agent_id):
        raise WorkflowConflict("Team membership or fallback changed. Reload the workflow before saving.")


def _replace_members(db, team_id, member_ids, fallback_id):
    db.query(TeamAgentMember).filter_by(team_agent_id=team_id).delete(synchronize_session=False)
    db.flush()
    db.add_all([TeamAgentMember(team_agent_id=team_id, agent_id=agent_id, sort_order=order,
                                role="starting" if agent_id == fallback_id else "member")
                for order, agent_id in enumerate(member_ids)])


def update_workflow_members(team_id: int, request: UpdateWorkflowMembersRequest, current_user: str):
    with database.get_db() as db:
        _lock_team(db, team_id)
        actual = _membership_state(db, team_id)
        requested = (request.member_agent_ids, request.fallback_agent_id)
        if (bool(request.member_agent_ids) != (request.fallback_agent_id is not None)
                or request.fallback_agent_id is not None and request.fallback_agent_id not in request.member_agent_ids):
            raise ValueError("Select a fallback from the team members, or clear it for an empty team")
        affected = set(actual[0]) | set(request.member_agent_ids)
        agents = db.query(Agent).filter(Agent.id.in_(affected)).order_by(Agent.id).with_for_update().all()
        if not set(request.member_agent_ids).issubset({agent.id for agent in agents}):
            raise ValueError("One or more agents do not exist")
        if actual == requested:
            return
        _check_membership_expected(actual, request)
        accessible = _accessible_team_ids(db, current_user)
        additions = set(request.member_agent_ids) - set(actual[0])
        if additions and accessible is not None:
            permitted = {member.agent_id for member in db.query(TeamAgentMember).filter(
                TeamAgentMember.agent_id.in_(additions), TeamAgentMember.team_agent_id.in_(accessible))}
            if additions - permitted:
                raise PermissionError("One or more agents are not accessible")
        _replace_members(db, team_id, request.member_agent_ids, request.fallback_agent_id)


def delete_workflow_agent(team_id: int, agent_id: int, request: DeleteWorkflowAgentRequest):
    with database.get_db() as db:
        _lock_team(db, team_id)
        actual = _membership_state(db, team_id)
        agents = db.query(Agent).filter(Agent.id.in_(actual[0])).order_by(Agent.id).with_for_update().all()
        agent = next((agent for agent in agents if agent.id == agent_id), None)
        if not agent:
            raise LookupError("Agent not found in this Team Agent")
        _check_membership_expected(actual, request)
        if db.query(TeamAgentMember).filter_by(agent_id=agent_id).count() > 1:
            raise WorkflowConflict("Shared agents cannot be deleted. Remove them from this team instead.")
        if request.expected_updated_at != (agent.updated_at.isoformat() if agent.updated_at else None):
            raise WorkflowConflict("This agent changed since you opened it. Reload the workflow before deleting.")
        remaining = [member_id for member_id in actual[0] if member_id != agent_id]
        replacement = request.replacement_fallback_agent_id
        if (remaining and replacement not in remaining) or (not remaining and replacement is not None):
            raise ValueError("Select a replacement fallback from the remaining members")
        if actual[1] != agent_id and replacement != actual[1]:
            raise ValueError("Keep the current fallback when deleting another agent")
        _replace_members(db, team_id, remaining, replacement)
        db.flush()
        db.delete(agent)
        return agent_id
