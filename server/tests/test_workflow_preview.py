"""Private workflow rehearsals against isolated SQLite; inference is faked."""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from test_workflow_creation import workspace, headers
from app import workflow_preview as preview
from app.orm_models import Agent, AgentTool, TeamAgentMember, Tool, LLMProvider


@pytest.fixture(autouse=True)
def clean_sessions():
    preview._sessions.clear()
    preview._active_runs = 0
    yield
    preview._sessions.clear()


def create(client, body=None, user="owner", team=1):
    return client.post(f"/api/admin/team-agents/{team}/workflow/previews", json=body or {}, headers=headers(user))


def send(client, preview_id, message="hello", user="owner", team=1):
    return client.post(f"/api/admin/team-agents/{team}/workflow/previews/{preview_id}/messages", json={"message": message}, headers=headers(user))


def draft(**changes):
    value = dict(name="Draft name", instructions="Draft instructions", model="test", llm_provider_id=None,
                 tool_ids=[], handoff_agent_ids=[], is_fallback=True)
    value.update(changes)
    return {"agent_id": 1, "draft": value}


def fake_runner(monkeypatch, calls):
    async def run(agent, history, **kwargs):
        calls.append((agent, history, kwargs))
        return SimpleNamespace(new_items=[], final_output="reply", last_agent=agent,
                               to_input_list=lambda: history + [{"role": "assistant", "content": "reply"}])
    monkeypatch.setattr(preview.Runner, "run", run)


def test_admin_scope_isolation_and_drafts_do_not_write(workspace, monkeypatch):
    client, get_db = workspace
    assert create(client, user="viewer").status_code == 403
    assert create(client, user="other").status_code == 403
    response = create(client, {"target_agent_id": 1, "drafts": [draft()]})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["has_drafts"] is True
    session = preview._sessions[data["id"]]
    assert session.agent.name == "Draft name"
    assert "Draft instructions" in session.agent.instructions
    assert send(client, data["id"], user="other", team=2).status_code == 404
    calls = []
    fake_runner(monkeypatch, calls)
    assert send(client, data["id"], "first").status_code == 200
    assert send(client, data["id"], "second").status_code == 200
    assert calls[1][1] == [{"role": "user", "content": "first"}, {"role": "assistant", "content": "reply"}, {"role": "user", "content": "second"}]
    assert calls[0][2]["run_config"].tracing_disabled
    with get_db() as db:
        assert db.get(Agent, 1).name == "Existing"
        assert db.get(Agent, 1).instructions == "old"
    assert client.delete(f"/api/admin/team-agents/1/workflow/previews/{data['id']}", headers=headers()).status_code == 200
    assert send(client, data["id"]).status_code == 404


def test_coordinator_default_and_unsafe_tools_not_constructed(workspace, monkeypatch):
    client, get_db = workspace
    with get_db() as db:
        db.add(AgentTool(agent_id=1, tool_id=2))
        db.add(Tool(id=4, name="PretendReadOnly", type="mcp_streamable_http", owner_team_agent_id=1,
                    config={"type": "mcp_streamable_http", "readOnlyHint": True}))
        db.flush()
        db.add(AgentTool(agent_id=1, tool_id=4))
    import app.agent_config as config
    original = config.get_tool_by_name
    constructed = []
    def construct(name, *args, **kwargs):
        constructed.append(name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(config, "get_tool_by_name", construct)
    result = create(client)
    assert result.status_code == 200, result.text
    assert result.json()["blocked_tools"] == ["OwnTool", "PretendReadOnly"]
    assert set(constructed) == {"DateTimeTool"}
    session = preview._sessions[result.json()["id"]]
    assert session.agent.name == "Coordinator Agent"
    assert session.agent.handoffs[0].name == "Existing"


def test_captured_config_and_revalidation(workspace, monkeypatch):
    client, get_db = workspace
    result = create(client, {"target_agent_id": 1, "drafts": [draft(tool_ids=[2], llm_provider_id=1)]}).json()
    with get_db() as db:
        db.get(Agent, 1).instructions = "Changed live"
    calls = []
    fake_runner(monkeypatch, calls)
    assert send(client, result["id"]).status_code == 200
    assert "Draft instructions" in calls[0][0].instructions
    with get_db() as db:
        db.get(Tool, 2).owner_team_agent_id = 2
    assert send(client, result["id"]).status_code == 403
    assert len(calls) == 1


def test_membership_provider_expiry_and_request_limits(workspace, monkeypatch):
    client, get_db = workspace
    assert create(client, {"drafts": [draft(tool_ids=[3])]}).status_code == 400
    assert create(client, {"target_agent_id": 2}).status_code == 400
    assert create(client, {"drafts": [draft(instructions="x" * 32001)]}).status_code == 422
    result = create(client).json()
    assert send(client, result["id"], " " * 10).status_code == 422
    assert send(client, result["id"], "x" * 8001).status_code == 422
    session = preview._sessions[result["id"]]
    session.expires_at = 0
    assert send(client, result["id"]).status_code == 404
    result = create(client, {"drafts": [draft(llm_provider_id=1)]}).json()
    with get_db() as db:
        db.get(LLMProvider, 1).api_key = ""
    assert send(client, result["id"]).status_code == 403
    with get_db() as db:
        db.get(LLMProvider, 1).api_key = "restored"
        db.query(TeamAgentMember).filter_by(team_agent_id=1).delete()
    assert send(client, result["id"]).status_code == 409


def test_busy_and_turn_limits_and_errors_hide_secrets(workspace, monkeypatch):
    client, _ = workspace
    result = create(client).json()
    session = preview._sessions[result["id"]]
    session.busy = True
    assert send(client, result["id"]).status_code == 409
    session.busy = False
    session.turns = preview.MAX_TURNS
    assert send(client, result["id"]).status_code == 409
    session.turns = 0
    def fail(*args, **kwargs):
        raise RuntimeError("credentials super-secret")
    monkeypatch.setattr(preview.Runner, "run", fail)
    response = send(client, result["id"])
    assert response.status_code == 503
    assert "super-secret" not in response.text
    assert not session.busy
    assert preview._active_runs == 0
    assert session.history == []


def test_concurrent_message_is_rejected_and_limits_are_bounded(workspace, monkeypatch):
    client, _ = workspace
    result = create(client).json()
    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()
        async def run(session, message):
            entered.set()
            await release.wait()
            return {"response": "done"}
        monkeypatch.setattr(preview, "_run", run)
        first = asyncio.create_task(preview.send_preview_message(1, result["id"], preview.PreviewMessage(message="one"), "owner"))
        await entered.wait()
        with pytest.raises(HTTPException) as error:
            await preview.send_preview_message(1, result["id"], preview.PreviewMessage(message="two"), "owner")
        assert error.value.status_code == 409
        release.set()
        await first
    asyncio.run(exercise())
    for _ in range(preview.MAX_USER_SESSIONS - 1):
        assert create(client).status_code == 200
    assert create(client).status_code == 429


def test_private_even_between_team_admins_and_history_budget(workspace, monkeypatch):
    from app.orm_models import TeamUserMembership
    client, get_db = workspace
    with get_db() as db:
        db.add(TeamUserMembership(admin_id=3, team_agent_id=1, role="admin"))
    result = create(client).json()
    assert send(client, result["id"], user="other").status_code == 404
    calls = []
    fake_runner(monkeypatch, calls)
    monkeypatch.setattr(preview, "MAX_HISTORY_BYTES", 1)
    assert send(client, result["id"]).status_code == 409
    assert preview._sessions[result["id"]].history == []
    assert client.post("/api/admin/team-agents/1/workflow/previews", content='{"junk":"' + "x" * 160_000 + '"}', headers={**headers(), "Content-Type": "application/json"}).status_code == 413


def test_presentations_and_last_agent_are_retained(workspace, monkeypatch):
    from agents import Agent as RuntimeAgent, ToolCallItem, ToolCallOutputItem, function_tool
    import app.knowledge_image_presentations as images
    import app.knowledge_audio_presentations as media
    from app.knowledge_image_presentations import KnowledgeImages
    client, _ = workspace
    @function_tool
    def knowledge(query: str) -> str:
        return query
    knowledge._servio_knowledge_bundle_id = 7
    specialist = RuntimeAgent(name="Specialist", tools=[knowledge])
    items = [ToolCallItem(agent=specialist, raw_item={"type": "function_call", "call_id": "local", "name": "knowledge", "arguments": '{"query":"bed"}'}),
             ToolCallOutputItem(agent=specialist, raw_item={"type": "function_call_output", "call_id": "local", "output": "trusted"}, output="trusted"),
             ToolCallOutputItem(agent=specialist, raw_item={"type": "function_call_output", "call_id": "unknown", "output": "untrusted"}, output="untrusted")]
    asset = "a" * 64
    presentation = KnowledgeImages(type="knowledge_images", version=1, response="Bed", images=[{
        "asset_id": asset, "title": "Bed", "source_label": "bed.jpg", "image_url": f"/api/knowledge-images/{asset}?token=test"}])
    hydrated = []
    def hydrate(value, team, bundle):
        hydrated.append((value, team, bundle))
        return presentation
    monkeypatch.setattr(images, "hydrate_knowledge_images", hydrate)
    monkeypatch.setattr(media, "hydrate_knowledge_media", lambda *args: None)
    async def run(agent, history, **kwargs):
        return SimpleNamespace(new_items=items, last_agent=specialist, final_output="Bed", to_input_list=lambda: history + [{"role": "assistant", "content": "Bed"}])
    monkeypatch.setattr(preview.Runner, "run", run)
    result = create(client).json()
    response = send(client, result["id"])
    assert response.status_code == 200, response.text
    assert response.json()["presentations"] == {"local": presentation.model_dump()}
    assert hydrated == [("trusted", 1, 7)]
    assert preview._sessions[result["id"]].agent is specialist


def test_captured_build_failure_cannot_shift_direct_target(workspace, monkeypatch):
    import app.agent_config as config
    client, get_db = workspace
    with get_db() as db:
        db.add(TeamAgentMember(team_agent_id=1, agent_id=2, role="member"))
    original = config.build_agent_from_db
    def build(data, *args, **kwargs):
        if data["id"] == 1:
            raise RuntimeError("credential secret")
        return original(data, *args, **kwargs)
    monkeypatch.setattr(config, "build_agent_from_db", build)
    response = create(client, {"target_agent_id": 2})
    assert response.status_code == 503
    assert "credential secret" not in response.text
    assert not preview._sessions


def test_timed_out_retrieval_keeps_capacity_until_thread_finishes(workspace, monkeypatch):
    import threading
    client, _ = workspace
    first = create(client).json()["id"]
    second = create(client).json()["id"]
    entered, release_thread = threading.Event(), threading.Event()
    def blocking_retrieval():
        entered.set()
        release_thread.wait(timeout=3)
    async def run(agent, history, **kwargs):
        await asyncio.to_thread(blocking_retrieval)
        return SimpleNamespace(new_items=[], final_output="late", last_agent=agent,
                               to_input_list=lambda: history + [{"role": "assistant", "content": "late"}])
    monkeypatch.setattr(preview.Runner, "run", run)
    monkeypatch.setattr(preview, "RUN_TIMEOUT_SECONDS", .03)
    monkeypatch.setattr(preview, "MAX_ACTIVE_RUNS", 1)
    async def exercise():
        try:
            with pytest.raises(HTTPException) as timeout:
                await preview.send_preview_message(1, first, preview.PreviewMessage(message="one"), "owner")
            assert timeout.value.status_code == 504
            assert entered.is_set()
            assert preview._active_runs == 1
            assert preview._sessions[first].busy
            with pytest.raises(HTTPException) as capacity:
                await preview.send_preview_message(1, second, preview.PreviewMessage(message="two"), "owner")
            assert capacity.value.status_code == 429
        finally:
            task = preview._sessions[first].task
            release_thread.set()
            if task:
                await asyncio.gather(task, return_exceptions=True)
                await asyncio.sleep(0)
        assert preview._active_runs == 0
        assert not preview._sessions[first].busy
        assert preview._sessions[first].history == []
    asyncio.run(exercise())


def test_delete_busy_preview_retires_it_without_cancelling_work_or_leaking_sessions(workspace, monkeypatch):
    client, _ = workspace
    preview_id = create(client).json()["id"]
    session = preview._sessions[preview_id]
    async def exercise():
        entered, finish = asyncio.Event(), asyncio.Event()
        async def run(agent, history, **kwargs):
            entered.set()
            await finish.wait()
            return SimpleNamespace(new_items=[], final_output="discard", last_agent=agent,
                                   to_input_list=lambda: history + [{"role": "assistant", "content": "discard"}])
        monkeypatch.setattr(preview.Runner, "run", run)
        sending = asyncio.create_task(preview.send_preview_message(1, preview_id, preview.PreviewMessage(message="hello"), "owner"))
        await entered.wait()
        assert await preview.delete_preview(1, preview_id, "owner") == {"success": True}
        assert preview_id not in preview._sessions
        assert preview._active_runs == 1
        assert session.busy
        finish.set()
        with pytest.raises(HTTPException) as expired:
            await sending
        assert expired.value.status_code == 404
        assert not session.history
        assert preview._active_runs == 0
        assert not session.busy
    asyncio.run(exercise())
