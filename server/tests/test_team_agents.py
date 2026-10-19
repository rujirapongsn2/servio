"""
Team Agents Test Suite

Run inside Docker: docker exec voice-agent-backend /app/.venv/bin/python -m pytest tests/ -v
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database import (
    get_all_team_agents,
    get_team_agent_by_id,
    get_team_agent_by_slug,
    create_team_agent,
    update_team_agent,
    delete_team_agent,
    get_team_agent_members,
    set_team_agent_members,
    set_starting_agent,
    get_all_tools,
    create_custom_tool,
    delete_custom_tool,
    get_default_team_id,
    get_all_api_keys,
    create_api_key,
    delete_api_key,
    has_team_access,
    set_user_team_role,
    get_team_users,
    get_admin_by_username,
    create_admin,
    delete_admin,
    get_all_channel_configs,
    upsert_channel_config,
    get_channel_config,
)
from app.agent_config import get_runtime_starting_agent


class TestTeamAgentCRUD:
    """Phase 1: Team Agent CRUD operations"""

    def test_get_all_team_agents(self):
        teams = get_all_team_agents()
        assert len(teams) > 0
        default = next((t for t in teams if t["slug"] == "default"), None)
        assert default is not None
        assert default["name"] == "Default Team"
        assert default["status"] == "active"

    def test_get_team_agent_by_id(self):
        team = get_team_agent_by_id(1)
        assert team is not None
        assert team["slug"] == "default"
        assert "members" in team

    def test_get_team_agent_by_slug(self):
        team = get_team_agent_by_slug("default")
        assert team is not None
        assert team["id"] == 1

    def test_create_and_delete_team(self):
        team_id = create_team_agent("Test CRUD Team", "test-crud", "Test description")
        assert team_id > 0

        team = get_team_agent_by_id(team_id)
        assert team["name"] == "Test CRUD Team"

        # Update
        assert update_team_agent(team_id, name="Updated Team")
        team = get_team_agent_by_id(team_id)
        assert team["name"] == "Updated Team"

        # Delete
        assert delete_team_agent(team_id)
        assert get_team_agent_by_id(team_id) is None

    def test_default_team_id(self):
        default_id = get_default_team_id()
        assert default_id is not None
        assert default_id > 0


class TestTeamMembers:
    """Phase 1-2: Team member management"""

    def test_get_members(self):
        members = get_team_agent_members(1)
        assert len(members) > 0
        for m in members:
            assert "agent_id" in m
            assert "agent_name" in m
            assert "role" in m

    def test_set_starting_agent(self):
        members = get_team_agent_members(1)
        if len(members) > 0:
            first_agent_id = members[0]["agent_id"]
            result = set_starting_agent(1, first_agent_id)
            assert result is True

            team = get_team_agent_by_id(1)
            starting = next((m for m in team["members"] if m["role"] == "starting"), None)
            assert starting is not None
            assert starting["agent_id"] == first_agent_id


class TestTeamTools:
    """Phase 3: Team-scoped tools"""

    def test_get_all_tools_unfiltered(self):
        tools = get_all_tools()
        assert len(tools) > 0

    def test_get_team_tools_filtered(self):
        tools = get_all_tools(team_agent_id=1)
        assert len(tools) > 0
        # All tools should be either owned by team 1 or global
        for t in tools:
            assert t["owner_team_agent_id"] == 1 or t["visibility"] == "global"

    def test_create_team_tool(self):
        tool_id = create_custom_tool(
            "test_team_scoped_tool",
            {"type": "custom_api", "description": "Test tool", "endpoint": "https://example.com"},
            team_agent_id=1,
        )
        assert tool_id > 0

        # Should appear in team 1 tools
        tools = get_all_tools(team_agent_id=1)
        assert any(t["id"] == tool_id for t in tools)

        # Clean up
        assert delete_custom_tool(tool_id, team_agent_id=1)

    def test_ownership_protection(self):
        tool_id = create_custom_tool(
            "test_owned_tool",
            {"type": "custom_api", "description": "Owned by team 1"},
            team_agent_id=1,
        )
        # Team 2 (or non-existent team) should not be able to delete
        result = delete_custom_tool(tool_id, team_agent_id=999)
        assert result is False  # Should fail

        # Clean up with correct team
        assert delete_custom_tool(tool_id, team_agent_id=1)


class TestRuntimeAgentResolution:
    """Phase 2: Team-scoped runtime agent resolution"""

    def test_resolve_with_team(self):
        agent = get_runtime_starting_agent(team_agent_id=1)
        assert agent is not None
        assert agent.name == "Coordinator Agent"
        assert len(agent.handoffs) > 0

    def test_resolve_without_team(self):
        agent = get_runtime_starting_agent()
        assert agent is not None
        assert len(agent.handoffs) > 0

    def test_different_teams_different_agents(self):
        # Create a temporary team with no members
        team_id = create_team_agent("Empty Team", "empty-team")
        agent = get_runtime_starting_agent(team_agent_id=team_id)
        assert agent is not None
        # Empty team should have no handoffs, but must still answer directly.
        assert len(agent.handoffs) == 0
        assert "answer the user directly" in agent.instructions
        assert "Do not try to transfer" in agent.instructions

        # Default team should have handoffs
        agent_default = get_runtime_starting_agent(team_agent_id=1)
        assert len(agent_default.handoffs) > 0

        # Clean up
        delete_team_agent(team_id)


class TestAPIKeys:
    """Phase 4: Team-scoped API keys"""

    def test_create_team_api_key(self):
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits
        key = "sk_test_" + "".join(secrets.choice(alphabet) for _ in range(32))

        key_id = create_api_key(
            "Test Team Key", key,
            team_agent_id=1,
        )
        assert key_id > 0

        # Should appear in team 1 keys
        keys = get_all_api_keys(team_agent_id=1)
        assert any(k["id"] == key_id for k in keys)

        # Clean up
        delete_api_key(key_id)


class TestChannelConfigs:
    """Phase 4: Team-scoped channel configs"""

    def test_get_team_channel_configs(self):
        configs = get_all_channel_configs(team_agent_id=1)
        assert len(configs) >= 2  # LINE + Facebook

    def test_team_channel_isolation(self):
        team_id = create_team_agent("Channel Test Team", "channel-test")
        configs = get_all_channel_configs(team_agent_id=team_id)
        # Auto-created defaults for new team
        types = {c["type"] for c in configs}
        assert "line" in types or "facebook" in types
        delete_team_agent(team_id)

    def test_upsert_channel(self):
        config = upsert_channel_config(
            "line", "Test LINE", {"channel_access_token": "test", "channel_secret": "secret"},
            is_active=False, team_agent_id=1
        )
        assert config["type"] == "line"
        assert config["team_agent_id"] == 1


class TestRBAC:
    """Phase 7: Role-based access control"""

    def test_has_team_access_legacy(self):
        # Legacy fallback: no memberships = full access
        result = has_team_access("admin", 1, "viewer")
        assert result is True

    def test_role_ranking(self):
        result = has_team_access("admin", 1, "owner")
        assert result is True  # Legacy fallback grants owner

    def test_create_and_assign_user(self):
        user_id = create_admin("testuser_rbac", "test123")
        assert user_id > 0

        # Assign to team
        result = set_user_team_role(user_id, 1, "viewer")
        assert result is True

        # Verify team users
        users = get_team_users(1)
        usernames = [u["username"] for u in users]
        assert "testuser_rbac" in usernames

        # Clean up
        set_user_team_role(user_id, 1, None)  # Remove from team
        delete_admin(user_id)
