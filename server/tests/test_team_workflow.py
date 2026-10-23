"""Workflow HTTP and persistence regressions using isolated SQLite databases."""
from contextlib import contextmanager
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

with patch("app.db_config.init_database"):
    from app import admin_routes as routes, database
from app.auth import create_access_token
from app.orm_models import Base, Admin, Agent, AgentHandoff, AgentTool, LLMProvider, TeamAgent, TeamAgentMember, TeamToolAssignment, TeamUserMembership, Tool, OKFBundle


@pytest.fixture
def workspace(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
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
        db.add_all([TeamAgent(id=1, name="First", slug="first"), TeamAgent(id=2, name="Second", slug="second")])
        db.flush()
        db.add_all([TeamUserMembership(admin_id=1, team_agent_id=1, role="admin"), TeamUserMembership(admin_id=2, team_agent_id=1, role="viewer"), TeamUserMembership(admin_id=3, team_agent_id=2, role="admin")])
        db.add(LLMProvider(id=1, name="Provider", api_key="provider-secret", base_url="https://private-provider.example/v1"))
        db.add_all([Agent(id=1, name="Editable", instructions="old", model="test", is_starting_agent=True), Agent(id=2, name="Shared", instructions="shared", model="test"), Agent(id=3, name="Outside", instructions="outside", model="test")])
        db.flush()
        db.add_all([TeamAgentMember(team_agent_id=1, agent_id=1, role="member", sort_order=1), TeamAgentMember(team_agent_id=1, agent_id=2, role="starting", sort_order=0), TeamAgentMember(team_agent_id=2, agent_id=2, role="member"), TeamAgentMember(team_agent_id=2, agent_id=3, role="starting")])
        db.add_all([Tool(id=1, name="DateTimeTool", type="builtin", visibility="global"), Tool(id=2, name="TeamTool", type="custom_api", owner_team_agent_id=1, config={"secret":"tool-secret"}), Tool(id=3, name="PrivateTool", type="custom_api", owner_team_agent_id=2)])
        db.flush()
        db.add_all([AgentHandoff(from_agent_id=1, to_agent_id=2), AgentHandoff(from_agent_id=2, to_agent_id=3), AgentHandoff(from_agent_id=1, to_agent_id=3), AgentTool(agent_id=1, tool_id=1)])
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as client:
        yield client, get_db
    engine.dispose()


def headers(user="owner"):
    return {"Authorization": "Bearer " + create_access_token({"sub": user})}


def snapshot(client, user="owner", team=1):
    return client.get(f"/api/admin/team-agents/{team}/workflow", headers=headers(user))


def payload(client, agent=1, **changes):
    state = snapshot(client).json()
    item = next(row for row in state["agents"] if row["id"] == agent)
    result = {key: item[key] for key in ("name", "instructions", "model", "llm_provider_id", "tool_ids", "handoff_agent_ids")}
    result.update(is_fallback=state["fallback_agent_id"] == agent, expected_updated_at=item["updated_at"], expected_fallback_agent_id=state["fallback_agent_id"])
    result.update(changes)
    return result


def save(client, body, agent=1, user="owner"):
    return client.put(f"/api/admin/team-agents/1/workflow/agents/{agent}", headers=headers(user), json=body)


def test_snapshot_projects_graph_and_hides_credentials(workspace):
    client, _ = workspace
    response = snapshot(client)
    assert response.status_code == 200
    state = response.json()
    assert state["can_edit"] is True
    assert state["fallback_agent_id"] == 2
    assert [row["id"] for row in state["agents"]] == [2, 1]
    assert state["agents"][0]["shared"] is True
    assert state["agents"][0]["handoff_agent_ids"] == []
    assert state["agents"][1]["handoff_agent_ids"] == [2]
    assert {tool["id"] for tool in state["tools"]} == {1, 2}
    assert state["providers"] == [{"id": 1, "name": "Provider"}]
    assert "provider-secret" not in response.text
    assert "tool-secret" not in response.text
    assert "private-provider" not in response.text
    assert "Outside" not in response.text


def test_access_requires_team_role_and_viewer_cannot_save(workspace):
    client, _ = workspace
    assert snapshot(client, user="other").status_code == 403
    assert snapshot(client, user="viewer").json()["can_edit"] is False
    assert save(client, payload(client), user="viewer").status_code == 403


def test_save_is_atomic_scoped_and_rejects_stale_revision(workspace):
    client, get_db = workspace
    body = payload(client, name=" Changed ", instructions="new", model=" new-model ", llm_provider_id=1, tool_ids=[2,2], handoff_agent_ids=[], is_fallback=True)
    assert save(client, body).json() == {"agent_id": 1}
    state = snapshot(client).json()
    agent = next(row for row in state["agents"] if row["id"] == 1)
    assert (agent["name"], agent["instructions"], agent["model"]) == ("Changed", "new", "new-model")
    assert agent["tool_ids"] == [1, 2]
    assert agent["handoff_agent_ids"] == []
    assert state["fallback_agent_id"] == 1
    with get_db() as db:
        assert db.get(Agent, 1).is_starting_agent is True
        assert db.get(TeamAgentMember, (2, 3)).role == "starting"
        assert db.get(AgentHandoff, (1, 3)) is not None
        assert db.get(AgentHandoff, (2, 3)) is not None
    assert save(client, body).status_code == 409
    assert next(row for row in snapshot(client).json()["agents"] if row["id"] == 1)["name"] == "Changed"


@pytest.mark.parametrize("changes", [{"tool_ids":[3]}, {"tool_ids":[999]}, {"handoff_agent_ids":[3]}, {"handoff_agent_ids":[1]}, {"llm_provider_id":999}, {"model":" "}, {"name":" "}])
def test_invalid_save_rolls_back_all_changes(workspace, changes):
    client, _ = workspace
    before = snapshot(client).json()
    assert save(client, payload(client, **{"name":"Should not persist", **changes})).status_code == 400
    assert snapshot(client).json() == before


def test_shared_agent_cannot_be_changed_through_workflow_or_manage(workspace):
    client, _ = workspace
    before = snapshot(client).json()
    assert save(client, payload(client, agent=2, name="Unsafe"), agent=2).status_code == 409
    legacy = payload(client, agent=2, name="Unsafe")
    legacy["is_starting_agent"] = legacy.pop("is_fallback")
    response = client.put("/api/admin/agents/2?team_agent_id=1", headers=headers(), json=legacy)
    assert response.status_code == 400
    assert client.delete("/api/admin/agents/2?team_agent_id=1", headers=headers()).status_code == 409
    assert snapshot(client).json() == before


def test_membership_changes_preserve_other_teams_handoffs(workspace):
    client, get_db = workspace
    assert database.set_team_agent_members(1, [2])
    with get_db() as db:
        assert db.get(AgentHandoff, (2,3)) is not None
        assert db.get(TeamAgentMember, (2,3)).role == "starting"
    assert database.get_all_agents(team_agent_id=1)[0]["handoffs"] == []
    assert database.get_all_agents(team_agent_id=1)[0]["is_starting_agent"] is True
    assert snapshot(client).json()["fallback_agent_id"] == 2


def test_scoped_create_sets_team_fallback_without_global_changes(workspace):
    _, get_db = workspace
    agent_id = database.create_agent("New", "new", "test", [], [], True, team_agent_id=1)
    with get_db() as db:
        assert db.get(Agent, 1).is_starting_agent is True
        assert db.get(Agent, agent_id).is_starting_agent is False
        assert db.get(TeamAgentMember, (1,agent_id)).role == "starting"
        assert db.get(TeamAgentMember, (2,3)).role == "starting"


def test_team_scoped_detail_uses_team_fallback(workspace):
    client, _ = workspace
    assert client.get("/api/admin/agents/1?team_agent_id=1", headers=headers()).json()["is_starting_agent"] is False
    assert client.get("/api/admin/agents/2?team_agent_id=1", headers=headers()).json()["is_starting_agent"] is True


def test_concurrent_fallback_change_is_not_overwritten(workspace):
    client, _ = workspace
    new_id = database.create_agent("Another", "", "test", [], [], team_agent_id=1)
    first_draft = payload(client, is_fallback=True)
    second_draft = payload(client, agent=new_id, is_fallback=True)
    assert save(client, second_draft, agent=new_id).status_code == 200
    assert save(client, first_draft).status_code == 409
    assert snapshot(client).json()["fallback_agent_id"] == new_id


def test_last_fallback_cannot_be_cleared(workspace):
    client, _ = workspace
    assert save(client, payload(client, is_fallback=True)).status_code == 200
    assert save(client, payload(client, is_fallback=False)).status_code == 400
    assert snapshot(client).json()["fallback_agent_id"] == 1


def test_outside_agent_cannot_be_updated(workspace):
    client, _ = workspace
    assert save(client, payload(client), agent=3).status_code == 404


def test_delete_fallback_selects_remaining_member(workspace):
    client, get_db = workspace
    assert save(client, payload(client, is_fallback=True)).status_code == 200
    assert database.delete_agent(1)
    assert snapshot(client).json()["fallback_agent_id"] == 2
    with get_db() as db:
        assert db.get(Agent, 1) is None
        assert db.get(TeamAgentMember, (2, 3)).role == "starting"


def test_delete_team_preserves_shared_agents_and_resources(workspace):
    client, get_db = workspace
    with get_db() as db:
        db.add(AgentTool(agent_id=2, tool_id=2))
    assert database.delete_team_agent(1)
    with get_db() as db:
        assert db.get(Agent, 1) is None
        assert db.get(Agent, 2).name == "Shared"
        assert db.get(TeamAgentMember, (2, 2)) is not None
        assert db.get(AgentHandoff, (2, 3)) is not None
        assert db.get(Tool, 2).owner_team_agent_id is None
        assert db.get(Tool, 2).visibility == "team"
        assert db.get(AgentTool, (2, 2)) is not None
        assert db.get(TeamToolAssignment, (2, 2)).relationship == "shared_in"
    state = snapshot(client, user="other", team=2).json()
    assert 2 in {tool["id"] for tool in state["tools"]}
    agent = next(row for row in state["agents"] if row["id"] == 2)
    body = {key: agent[key] for key in ("name", "instructions", "model", "llm_provider_id", "tool_ids", "handoff_agent_ids")}
    body.update(is_fallback=False, expected_updated_at=agent["updated_at"], expected_fallback_agent_id=state["fallback_agent_id"])
    response = client.put("/api/admin/team-agents/2/workflow/agents/2", headers=headers("other"), json=body)
    assert response.status_code == 200, response.text
    assert snapshot(client, user="other", team=2).json()["fallback_agent_id"] == 3


@pytest.mark.parametrize("assigned_to_agent", [True, False])
def test_delete_team_preserves_shared_okf_visibility_without_global_access(workspace, tmp_path, assigned_to_agent):
    from app.okf_service import _bundle_available_to_team

    client, get_db = workspace
    storage = tmp_path / "knowledge"
    storage.mkdir()
    with get_db() as db:
        db.add(TeamAgent(id=3, name="Unrelated", slug="unrelated"))
        db.add(OKFBundle(id=1, name="knowledge", display_name="Knowledge", storage_path=str(storage), owner_team_agent_id=1))
        db.add(Tool(id=4, name="Knowledge", type="okf_knowledge_graph", owner_team_agent_id=1, config={"okf_bundle_id": 1}))
        db.flush()
        if assigned_to_agent:
            db.add(AgentTool(agent_id=2, tool_id=4))
        else:
            db.add(TeamToolAssignment(team_agent_id=2, tool_id=4, relationship="shared_in"))
    assert database.delete_team_agent(1)
    with get_db() as db:
        bundle = db.get(OKFBundle, 1)
        assert bundle is not None
        assert bundle.owner_team_agent_id is None
        assert bundle.visibility == "team"
        assert db.get(Tool, 4).visibility == "team"
        assert db.get(TeamToolAssignment, (2, 4)).relationship == "shared_in"
        assert _bundle_available_to_team(db, bundle, 2)
        assert not _bundle_available_to_team(db, bundle, 3)
        assert not database._tool_available_to_team(db, 4, 3)
    assert storage.exists()
    state = snapshot(client, user="other", team=2).json()
    assert 4 in {tool["id"] for tool in state["tools"]}


def test_shared_agent_tool_assignment_is_refused(workspace):
    _, get_db = workspace
    assert database.assign_tool_to_agent(2, 2, team_agent_id=1) is False
    with get_db() as db:
        assert db.get(AgentTool, (2, 2)) is None


def test_manage_tool_assignment_invalidates_workflow_draft(workspace):
    client, _ = workspace
    body = payload(client)
    assert database.assign_tool_to_agent(1, 2, team_agent_id=1)
    assert save(client, body).status_code == 409
    assert next(row for row in snapshot(client).json()["agents"] if row["id"] == 1)["tool_ids"] == [1, 2]


def test_snapshot_preserves_readable_knowledge_name(workspace, tmp_path):
    client, get_db = workspace
    with get_db() as db:
        db.add(OKFBundle(id=1, name="product-guide", display_name="Product guide", storage_path=str(tmp_path), owner_team_agent_id=1))
        db.add(Tool(id=4, name="Product_guide_okf_1", type="okf_knowledge_graph", owner_team_agent_id=1, config={"okf_bundle_id": 1}))
    tools = snapshot(client).json()["tools"]
    assert next(tool for tool in tools if tool["id"] == 4)["name"] == "Product guide"
    assert next(tool for tool in tools if tool["id"] == 2)["name"] == "TeamTool"
