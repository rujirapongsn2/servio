"""Team membership, grants and captured credentials checked at execution boundaries."""
import json
from fastapi import HTTPException
from app import database
from app.orm_models import Tool, LLMProvider


def validate_runtime_access(team_id, agents):
    current_members = {member["agent_id"] for member in (database.get_team_agent_by_id(team_id) or {}).get("members", [])}
    if not {agent["id"] for agent in agents}.issubset(current_members):
        raise HTTPException(409, "Team membership changed. Start a new preview.")
    with database.get_db() as db:
        for agent in agents:
            for tool in agent["tools"]:
                if not database._tool_available_to_team(db, tool["id"], team_id):
                    raise HTTPException(403, "A preview tool is no longer available to this team.")
                current = db.get(Tool, tool['id'])
                if (not current or current.name != tool['name'] or current.type != tool['type']
                        or (current.config or {}) != json.loads(tool.get('config') or '{}')):
                    raise HTTPException(409, "Tool configuration changed. Start a new preview.")
            provider = agent.get("llm_provider")
            if provider:
                current = db.get(LLMProvider, provider["id"])
                if not current or not current.base_url or not current.api_key:
                    raise HTTPException(403, "A preview provider is no longer available.")
                if current.base_url != provider["base_url"] or current.api_key != provider["api_key"]:
                    raise HTTPException(409, "Provider configuration changed. Start a new preview.")
