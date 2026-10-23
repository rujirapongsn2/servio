"""Team authoring HTTP regressions with persisted isolated SQLite state."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from uuid import uuid4
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session

with patch("app.db_config.init_database"):
    from app import admin_routes as routes, database
from app.auth import create_access_token
from app.orm_models import (Admin, Agent, AgentHandoff, AgentTool, Base, LLMProvider,
                            TeamAgent, TeamAgentMember, TeamToolAssignment,
                            TeamUserMembership, Tool, WorkflowCreationReceipt)


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'workflow.sqlite'}", connect_args={"check_same_thread": False, "timeout": 15})

    @event.listens_for(engine, "connect")
    def configure(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX ix_team_agent_members_starting"))
        connection.execute(text("CREATE UNIQUE INDEX ix_team_agent_members_starting ON team_agent_members(team_agent_id) WHERE role = 'starting'"))

    @contextmanager
    def get_db():
        with Session(engine, expire_on_commit=False) as db:
            with db.begin():
                yield db

    monkeypatch.setattr(database, "get_db", get_db)
    with get_db() as db:
        db.add_all([Admin(id=1, username="owner", password_hash="unused"), Admin(id=2, username="viewer", password_hash="unused"), Admin(id=3, username="other", password_hash="unused")])
        db.add_all([TeamAgent(id=1, name="Team", slug="team"), TeamAgent(id=2, name="Other", slug="other"), TeamAgent(id=3, name="Empty", slug="empty")])
        db.flush()
        db.add_all([TeamUserMembership(admin_id=1, team_agent_id=1, role="admin"), TeamUserMembership(admin_id=1, team_agent_id=3, role="admin"), TeamUserMembership(admin_id=2, team_agent_id=1, role="viewer"), TeamUserMembership(admin_id=3, team_agent_id=2, role="admin")])
        db.add_all([Agent(id=1, name="Existing", instructions="old", model="test", is_starting_agent=True), Agent(id=2, name="Outside", instructions="outside", model="test")])
        db.add(LLMProvider(id=1, name="Configured", api_key="secret", base_url="https://provider.example/v1"))
        db.add(LLMProvider(id=2, name="Incomplete", api_key="", base_url="https://provider.example/v1"))
        db.flush()
        db.add_all([TeamAgentMember(team_agent_id=1, agent_id=1, role="starting"), TeamAgentMember(team_agent_id=2, agent_id=2, role="starting")])
        db.add_all([Tool(id=1, name="DateTimeTool", type="builtin", visibility="global"), Tool(id=2, name="OwnTool", type="custom_api", owner_team_agent_id=1), Tool(id=3, name="OtherTool", type="custom_api", owner_team_agent_id=2)])
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as client:
        yield client, get_db
    engine.dispose()


def headers(user="owner"):
    return {"Authorization": "Bearer " + create_access_token({"sub": user})}


def agent_body(**changes):
    body = dict(request_id=str(uuid4()), name="New Agent", instructions="Be helpful", model="test", llm_provider_id=1,
                tool_ids=[2], handoff_agent_ids=[1], is_fallback=False, expected_fallback_agent_id=1)
    body.update(changes)
    return body


def tool_body(**changes):
    body = dict(request_id=str(uuid4()), name="NewTool", visibility="team", icon="Wrench", config={
        "type": "custom_api", "endpoint": "https://api.example/v1", "method": "POST", "auth_token": "private-secret",
        "request": {"version": 1, "headers": [], "query": [], "body": {"kind": "json", "value": {"query": "{{query}}"}}}})
    body.update(changes)
    return body


def create(client, kind, body, team=1, user="owner"):
    return client.post(f"/api/admin/team-agents/{team}/workflow/{kind}", json=body, headers=headers(user))


@pytest.mark.parametrize("kind,body", [("agents", agent_body()), ("tools", tool_body())])
@pytest.mark.parametrize("user", ["viewer", "other"])
def test_creation_requires_team_admin(workspace, kind, body, user):
    client, get_db = workspace
    assert create(client, kind, body, user=user).status_code == 403
    with get_db() as db:
        assert db.query(WorkflowCreationReceipt).count() == 0


def test_create_agent_persists_membership_links_without_global_fallback(workspace):
    client, get_db = workspace
    response = create(client, "agents", agent_body(name=" New Agent ", model=" test ", tool_ids=[2, 2]))
    assert response.status_code == 200, response.text
    agent_id = response.json()["agent_id"]
    with get_db() as db:
        agent = db.get(Agent, agent_id)
        assert (agent.name, agent.model, agent.instructions, agent.llm_provider_id) == ("New Agent", "test", "Be helpful", 1)
        assert not agent.is_starting_agent
        assert db.get(Agent, 1).is_starting_agent
        assert db.get(TeamAgentMember, (1, agent_id)).role == "member"
        assert db.get(TeamAgentMember, (1, 1)).role == "starting"
        assert db.get(TeamAgentMember, (2, 2)).role == "starting"
        assert {link.tool_id for link in db.query(AgentTool).filter_by(agent_id=agent_id)} == {1, 2}
        assert db.get(AgentHandoff, (agent_id, 1)) is not None


def test_empty_team_selects_first_agent_as_fallback(workspace):
    client, get_db = workspace
    response = create(client, "agents", agent_body(tool_ids=[], handoff_agent_ids=[], expected_fallback_agent_id=None), team=3)
    assert response.status_code == 200, response.text
    with get_db() as db:
        agent_id = response.json()["agent_id"]
        assert db.get(TeamAgentMember, (3, agent_id)).role == "starting"
        assert not db.get(Agent, agent_id).is_starting_agent


@pytest.mark.parametrize("changes", [{"name": " "}, {"model": " "}, {"llm_provider_id": 999}, {"llm_provider_id": 2}, {"tool_ids": [3]}, {"tool_ids": [999]}, {"handoff_agent_ids": [2]}, {"handoff_agent_ids": [999]}])
def test_invalid_agent_creation_rolls_back(workspace, changes):
    client, get_db = workspace
    response = create(client, "agents", agent_body(**changes))
    assert response.status_code == 400, response.text
    with get_db() as db:
        assert db.query(Agent).count() == 2
        assert db.query(WorkflowCreationReceipt).count() == 0
        assert db.query(AgentTool).count() == 0
        assert db.get(TeamAgentMember, (1, 1)).role == "starting"


def test_fallback_creation_checks_expected_version_and_replays_before_conflict(workspace):
    client, get_db = workspace
    body = agent_body(is_fallback=True)
    response = create(client, "agents", body)
    assert response.status_code == 200, response.text
    created_id = response.json()["agent_id"]
    with get_db() as db:
        db.get(TeamAgentMember, (1, created_id)).role = "member"
        db.flush()
        db.get(TeamAgentMember, (1, 1)).role = "starting"
    assert create(client, "agents", body).json() == {"agent_id": created_id}
    assert create(client, "agents", agent_body(is_fallback=True, expected_fallback_agent_id=created_id)).status_code == 409
    assert create(client, "agents", {**body, "name": "Changed"}).status_code == 409
    with get_db() as db:
        assert db.query(Agent).count() == 3
        assert db.get(TeamAgentMember, (1, 1)).role == "starting"
        assert db.query(WorkflowCreationReceipt).count() == 1


def test_deleted_agent_replay_conflicts(workspace):
    client, get_db = workspace
    body = agent_body()
    agent_id = create(client, "agents", body).json()["agent_id"]
    with get_db() as db:
        db.delete(db.get(Agent, agent_id))
    assert create(client, "agents", body).status_code == 409


def test_concurrent_identical_creation_and_fallback_conflict(workspace):
    client, get_db = workspace
    body = agent_body()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: create(client, "agents", body), range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    requests = [agent_body(is_fallback=True, name=f"Fallback {i}") for i in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda request: create(client, "agents", request), requests))
    assert sorted(response.status_code for response in responses) == [200, 409]
    with get_db() as db:
        assert db.query(Agent).count() == 4
        assert db.query(TeamAgentMember).filter_by(team_agent_id=1, role="starting").count() == 1


def test_tool_creation_is_team_owned_unbound_and_receipt_contains_no_secret(workspace):
    client, get_db = workspace
    body = tool_body()
    response = create(client, "tools", body)
    assert response.status_code == 200, response.text
    tool_id = response.json()["tool_id"]
    assert create(client, "tools", body).json() == {"tool_id": tool_id}
    with get_db() as db:
        tool = db.get(Tool, tool_id)
        assert (tool.owner_team_agent_id, tool.visibility, tool.created_by_admin_id, tool.type) == (1, "team", 1, "custom_api")
        assert tool.config == body["config"]
        assert db.get(TeamToolAssignment, (1, tool_id)).relationship == "owned"
        assert not db.query(AgentTool).filter_by(tool_id=tool_id).first()
        receipt = db.query(WorkflowCreationReceipt).one()
        assert len(receipt.payload_hash) == 64
        assert "private-secret" not in repr(receipt.__dict__)
        assert not database._tool_available_to_team(db, tool_id, 2)
    snapshot = client.get("/api/admin/team-agents/1/workflow", headers=headers())
    assert "private-secret" not in snapshot.text
    assert tool_id in {tool["id"] for tool in snapshot.json()["tools"]}
    assert create(client, "tools", {**body, "config": {**body["config"], "auth_token": "changed"}}).status_code == 409
    assert create(client, "agents", agent_body(request_id=body["request_id"])).status_code == 409
    with get_db() as db:
        db.delete(db.get(Tool, tool_id))
    assert create(client, "tools", body).status_code == 409


@pytest.mark.parametrize("config", [
    {"type": "builtin", "endpoint": "https://api.example"},
    {"type": "custom_api", "endpoint": "file:///etc/passwd"},
    {"type": "mcp_streamable_http", "endpoint": "https://user:secret@api.example"},
    {"type": "mcp_streamable_http", "endpoint": "https://api.example", "timeout_seconds": -1},
    {"type": "mcp_streamable_http", "endpoint": "https://api.example", "tools": "bad"},
    {"type": "custom_api", "endpoint": "https://api.example", "request": {"version": 99}},
])
def test_invalid_tool_configuration_rolls_back(workspace, config):
    client, get_db = workspace
    response = create(client, "tools", tool_body(config=config))
    assert response.status_code == 400, response.text
    with get_db() as db:
        assert db.query(Tool).count() == 3
        assert db.query(WorkflowCreationReceipt).count() == 0


def test_mcp_creation_and_legacy_structured_tool_response(workspace):
    client, get_db = workspace
    config = {"type": "mcp_streamable_http", "endpoint": "https://mcp.example/mcp", "transport": "streamable_http", "tools": ["search"], "auth_mode": "bearer", "auth_token": "secret"}
    response = create(client, "tools", tool_body(name="MCP", config=config))
    assert response.status_code == 200, response.text
    response = client.post("/api/admin/tools?team_agent_id=1", headers=headers(), json={"name": "Legacy", "config": config, "visibility": "team"})
    assert response.status_code == 200, response.text
    assert isinstance(response.json()["tool_id"], int)
    assert response.json()["success"] is True
    assert "created successfully" in response.json()["message"]
    with get_db() as db:
        assert db.get(Tool, response.json()["tool_id"]).name == "Legacy"
