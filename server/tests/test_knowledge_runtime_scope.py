"""Runtime Knowledge isolation with disposable storage and no embedding requests."""
import asyncio
from contextlib import contextmanager
import json

import pytest
from agents import RunContextWrapper
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import agent_config, db_config, local_rag, okf_service
from app.orm_models import Base, OKFBundle, TeamAgent, TeamToolAssignment, Tool


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    with monkeypatch.context() as imports:
        imports.setattr(db_config, "init_database", lambda: None)
        from app import database

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)

    @contextmanager
    def get_db():
        with sessions.begin() as session:
            yield session

    with get_db() as session:
        session.add_all([
            TeamAgent(id=1, name="Owner", slug="default"),
            TeamAgent(id=2, name="Other", slug="other"),
            OKFBundle(id=1, name="private", display_name="Private", storage_path=str(tmp_path), owner_team_agent_id=1, visibility="team"),
            Tool(id=10, name="knowledge_search", type="okf_knowledge_graph", config={"okf_bundle_id": 1}, owner_team_agent_id=1, visibility="team"),
        ])

    agent_data = {
        "id": 7, "name": "Shared member", "instructions": "Search Knowledge", "model": "gpt-4o-mini",
        "is_starting_agent": True,
        "tools": [{"name": "knowledge_search", "config": json.dumps({"type": "okf_knowledge_graph", "okf_bundle_id": 1, "team_agent_id": 1})}],
    }
    teams = {
        team: {"id": team, "name": name, "members": [{"agent_id": 7, "agent_name": "Shared member", "role": "starting"}]}
        for team, name in [(1, "Owner"), (2, "Other")]
    }
    embeddings = []

    def retrieve(bundle_id, query, limit):
        embeddings.append(query)
        return {"response": "Private ALPHA-7391", "concepts": [{"concept_id": "policy"}]}

    monkeypatch.setattr(database, "get_all_agents", lambda: [agent_data])
    monkeypatch.setattr(database, "get_team_agent_by_id", teams.get)
    monkeypatch.setattr(database, "get_default_team_id", lambda: 1)
    monkeypatch.setattr(okf_service, "get_db", get_db)
    monkeypatch.setattr(local_rag, "enabled", lambda: True)
    monkeypatch.setattr(local_rag, "indexed_count", lambda _: 1)
    monkeypatch.setattr(local_rag, "query_bundle", retrieve)
    yield agent_data, get_db, embeddings, database
    engine.dispose()


def invoke_agent(agent):
    member = next((a for a in agent.handoffs if a.name == "Shared member"), agent)
    tool = next((t for t in member.tools if t.name == "knowledge_search"), None)
    if tool is None:
        return "Knowledge tool unavailable."
    return asyncio.run(tool.on_invoke_tool(RunContextWrapper(context=None), json.dumps({"query": "refund"})))


def invoke(team_id=None):
    return invoke_agent(agent_config.get_runtime_starting_agent(team_id))


def test_shared_member_cannot_read_foreign_private_knowledge(runtime):
    _, _, embeddings, _ = runtime
    assert "ALPHA-7391" in invoke(1)
    embeddings.clear()
    assert "ALPHA-7391" not in invoke(2)
    assert embeddings == []


def test_editable_tool_scope_cannot_change_runtime_identity(runtime):
    agent_data, _, embeddings, _ = runtime
    config = json.loads(agent_data["tools"][0]["config"])
    config["team_agent_id"] = 2
    agent_data["tools"][0]["config"] = json.dumps(config)
    assert "ALPHA-7391" in invoke(1)
    embeddings.clear()
    assert "ALPHA-7391" not in invoke(2)
    assert embeddings == []


@pytest.mark.parametrize("grant", ["shared_in", "global_bundle", "global_tool"])
def test_explicit_sharing_remains_usable(runtime, grant):
    _, get_db, embeddings, _ = runtime
    with get_db() as session:
        if grant == "shared_in":
            session.add(TeamToolAssignment(team_agent_id=2, tool_id=10, relationship="shared_in"))
        elif grant == "global_bundle":
            session.get(OKFBundle, 1).visibility = "global"
        else:
            session.get(Tool, 10).visibility = "global"
    assert "ALPHA-7391" in invoke(2)
    assert embeddings == ["refund"]


def test_unknown_team_does_not_load_other_teams_agents(runtime):
    _, _, embeddings, _ = runtime
    agent = agent_config.get_runtime_starting_agent(999)
    assert agent.handoffs == []
    assert "ALPHA-7391" not in invoke(999)
    assert embeddings == []


def test_global_runtime_uses_database_default_not_stored_tool_scope(runtime):
    agent_data, _, embeddings, _ = runtime
    monkey_config = json.loads(agent_data["tools"][0]["config"])
    monkey_config["team_agent_id"] = 2
    agent_data["tools"][0]["config"] = json.dumps(monkey_config)
    assert "ALPHA-7391" in invoke()
    assert embeddings == ["refund"]


@pytest.mark.parametrize("caller", ["builder", "legacy_loader"])
def test_legacy_callers_cannot_impersonate_private_tool_owner(runtime, monkeypatch, caller):
    agent_data, _, embeddings, database = runtime
    monkeypatch.setattr(database, "get_default_team_id", lambda: 2)
    agent = (
        agent_config.build_agent_from_db(agent_data)
        if caller == "builder"
        else agent_config.load_agents_from_db()
    )
    assert "ALPHA-7391" not in invoke_agent(agent)
    assert embeddings == []


def test_global_runtime_cannot_impersonate_private_tool_owner(runtime, monkeypatch):
    _, _, embeddings, database = runtime
    monkeypatch.setattr(database, "get_default_team_id", lambda: 2)
    assert "ALPHA-7391" not in invoke()
    assert embeddings == []


def test_missing_default_team_denies_knowledge(runtime, monkeypatch):
    _, _, embeddings, database = runtime
    monkeypatch.setattr(database, "get_default_team_id", lambda: None)
    assert "ALPHA-7391" not in invoke()
    assert embeddings == []


def test_unscoped_direct_factory_denies_knowledge(runtime):
    _, _, embeddings, _ = runtime
    tool = agent_config.get_tool_by_name("knowledge_search", {"type": "okf_knowledge_graph", "okf_bundle_id": 1, "team_agent_id": 1})
    response = asyncio.run(tool.on_invoke_tool(RunContextWrapper(context=None), json.dumps({"query": "refund"})))
    assert "ALPHA-7391" not in response
    assert embeddings == []
