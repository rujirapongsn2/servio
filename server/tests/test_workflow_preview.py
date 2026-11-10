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
    return client.post(f"/api/admin/team-agents/{team}/workflow/previews", json={"confirm_real_tools": True, **(body or {})}, headers=headers(user))


@pytest.fixture(autouse=True)
def valid_api_configuration(workspace, monkeypatch):
    import app.agent_config as config
    import httpx
    def blocked(*args, **kwargs):
        raise AssertionError('External HTTP is forbidden in Private Chat regressions')
    async def blocked_async(*args, **kwargs):
        raise AssertionError('External model/MCP HTTP is forbidden in Private Chat regressions')
    monkeypatch.setattr(config.requests, 'request', blocked)
    monkeypatch.setattr(config.requests, 'post', blocked)
    monkeypatch.setattr(config.requests, 'get', blocked)
    monkeypatch.setattr(httpx.AsyncClient, 'send', blocked_async)
    _, get_db = workspace
    with get_db() as db:
        db.get(Tool, 2).config = {"type": "custom_api", "endpoint": "https://api.invalid", "method": "POST"}


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


def test_coordinator_uses_channel_factories_for_all_assigned_types(workspace, monkeypatch):
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
    assert result.json()["blocked_tools"] == []
    assert set(constructed) == {"DateTimeTool", "OwnTool", "PretendReadOnly"}
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
    assert send(client, result["id"], "x" * (preview.MAX_MESSAGE_CHARS + 1)).status_code == 422
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


def test_busy_budget_and_errors_hide_secrets(workspace, monkeypatch):
    client, _ = workspace
    result = create(client).json()
    session = preview._sessions[result["id"]]
    session.busy = True
    assert send(client, result["id"]).status_code == 409
    session.busy = False
    session.turns = 100  # No preview-only message cap.
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


def test_explicit_confirmation_precedes_build_or_execution(workspace, monkeypatch):
    client, _ = workspace
    def forbidden(*args, **kwargs):
        pytest.fail('Runtime must not be constructed before consent')
    monkeypatch.setattr(preview, '_build', forbidden)
    url = '/api/admin/team-agents/1/workflow/previews'
    assert client.post(url, json={}, headers=headers()).status_code == 428
    assert create(client, {'confirm_real_tools': False}).status_code == 428
    assert create(client, {'confirm_real_tools': 'true'}).status_code == 422
    assert not preview._sessions


@pytest.mark.parametrize('kind', ['custom_api', 'mcp_streamable_http'])
def test_real_sdk_routing_handoffs_and_tool_arguments_use_channel_factories(workspace, monkeypatch, capsys, kind):
    import json
    from contextlib import asynccontextmanager
    from agents import Model, ModelResponse, Usage
    from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
    from app import agent_config
    from app.orm_models import AgentHandoff
    from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool as McpTool

    client, get_db = workspace
    vin = 'MR053BK4007006295'
    observed = []
    token = 'synthetic-preview-credential-42'
    api = {'type': kind, 'endpoint': 'https://service.invalid/api', 'auth_token': token,
           'method': 'POST', 'tools': ['lookup_vin']}
    if kind == 'custom_api':
        api['request'] = {'version': 1, 'headers': [{'name': 'X-API-Key', 'value': token}],
                          'query': [{'name': 'vin', 'value': '{{query}}'}],
                          'body': {'kind': 'json', 'value': {'vin': '{{query}}'}}}
    with get_db() as db:
        db.get(Tool, 2).config = api
        db.add(Agent(id=3, name='Parts', instructions='Look up exact vehicle', model='test'))
        db.flush()
        db.add(TeamAgentMember(team_agent_id=1, agent_id=3))
        db.add(AgentTool(agent_id=3, tool_id=2))
        db.add(AgentHandoff(from_agent_id=1, to_agent_id=3))

    class Response:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {'model': 'TOYOTA CAMRY/HYBRID (ASIA)', 'api_key': token}
    def request(method, endpoint, **kwargs):
        observed.append((method, endpoint, kwargs))
        return Response()
    monkeypatch.setattr(agent_config.requests, 'request', request)
    @asynccontextmanager
    async def transport(endpoint, **kwargs):
        observed.append((endpoint, kwargs['headers']))
        yield object(), object(), None
    class Session:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return False
        async def initialize(self): pass
        async def list_tools(self):
            return ListToolsResult(tools=[McpTool(name='lookup_vin', inputSchema={'type': 'object', 'properties': {'vin': {'type': 'string'}}, 'required': ['vin']})])
        async def call_tool(self, name, arguments):
            observed.append((name, arguments))
            return CallToolResult(content=[TextContent(type='text', text=json.dumps(Response().json()))])
    monkeypatch.setattr(agent_config, 'streamablehttp_client', transport)
    monkeypatch.setattr(agent_config, 'ClientSession', Session)
    monkeypatch.delenv('DISABLE_MCP', raising=False)
    monkeypatch.delenv('AGENTS_SAFE_MODE_DISABLE_EXTERNAL', raising=False)

    class ScriptedModel(Model):
        def __init__(self, route): self.route = route
        async def get_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing):
            outputs = [item for item in input if isinstance(item, dict) and item.get('type') == 'function_call_output']
            if self.route:
                name, arguments = handoffs[0].tool_name, '{}'
            elif not any(item.get('call_id') == 'lookup' for item in outputs):
                name, arguments = 'OwnTool', json.dumps({'query': vin})
            else:
                return ModelResponse(output=[ResponseOutputMessage(id='answer', type='message', role='assistant', status='completed', content=[ResponseOutputText(type='output_text', text=str(outputs[-1]['output']), annotations=[])])], usage=Usage(), referenceable_id=None)
            return ModelResponse(output=[ResponseFunctionToolCall(id='call', type='function_call', call_id='route' + name if self.route else 'lookup', name=name, arguments=arguments)], usage=Usage(), referenceable_id=None)
        async def stream_response(self, *args, **kwargs):
            raise NotImplementedError
            yield
    result = create(client)
    assert result.status_code == 200, result.text
    session = preview._sessions[result.json()['id']]
    session.agent.model = ScriptedModel(True)
    for agent in session.agent.handoffs:
        agent.model = ScriptedModel(agent.name != 'Parts')
    response = send(client, result.json()['id'], vin)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['agent_name'] == 'Parts' and data['status'] == 'completed'
    assert 'CAMRY/HYBRID (ASIA)' in data['response'] and 'Hilux' not in data['response']
    assert data['tool_calls'] == [{'name': 'OwnTool', 'status': 'succeeded'}]
    assert token not in response.text and token not in capsys.readouterr().out
    assert session.agent.name == 'Parts'
    assert token not in json.dumps(session.history)
    if kind == 'custom_api':
        assert observed[0][0] == 'POST'
        kwargs = observed[0][2]
        assert kwargs['headers']['Authorization'] == 'Bearer ' + token
        assert kwargs['params'] == [('vin', vin)]
        assert json.loads(kwargs['data']) == {'vin': vin}
    else:
        assert observed[0][1] == {'Authorization': 'Bearer ' + token}
        assert observed[1] == ('lookup_vin', {'vin': vin})


@pytest.mark.parametrize('failure', ['exception', 'error_result', 'no_call', 'revoked', 'changed', 'role_revoked', 'membership_revoked'])
def test_tool_failure_recovers_and_no_call_answers_are_not_replaced(workspace, monkeypatch, failure):
    from agents import RunContextWrapper
    from app import agent_config
    client, get_db = workspace
    with get_db() as db:
        db.add(AgentTool(agent_id=1, tool_id=2))
        db.get(Tool, 2).config = {'type': 'custom_api', 'endpoint': 'https://api.invalid', 'method': 'POST', 'auth_token': 'must-not-leak'}
    invoked = []
    def request(*args, **kwargs):
        invoked.append(True)
        if failure == 'exception': raise RuntimeError('must-not-leak')
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'error': 'must-not-leak'})
    monkeypatch.setattr(agent_config.requests, 'post', request)
    result = create(client, {'target_agent_id': 1}).json()
    async def run(agent, history, **kwargs):
        if failure in ('revoked', 'changed', 'role_revoked', 'membership_revoked'):
            with get_db() as db:
                if failure == 'revoked': db.get(Tool, 2).owner_team_agent_id = 2
                elif failure == 'changed': db.get(Tool, 2).config = {'type': 'custom_api', 'endpoint': 'https://changed.invalid'}
                elif failure == 'membership_revoked': db.query(TeamAgentMember).filter_by(team_agent_id=1).delete()
                else:
                    from app.orm_models import TeamUserMembership
                    db.query(TeamUserMembership).filter_by(team_agent_id=1, admin_id=1).delete()
        if failure != 'no_call':
            tool = next(tool for tool in agent.tools if tool.name == 'OwnTool')
            await tool.on_invoke_tool(RunContextWrapper(context=None), '{"query":"VIN"}')
        return SimpleNamespace(new_items=[], final_output='Hello' if failure == 'no_call' else 'Tool unavailable; please clarify', last_agent=agent, to_input_list=lambda: history)
    monkeypatch.setattr(preview.Runner, 'run', run)
    response = send(client, result['id'])
    assert 'must-not-leak' not in response.text and 'Hilux' not in response.text
    if failure in ('revoked', 'changed', 'role_revoked', 'membership_revoked'):
        assert response.status_code in (403, 409) and not invoked
    else:
        assert response.status_code == 200
        assert response.json()['status'] == 'completed'
        assert response.json()['response'] == ('Hello' if failure == 'no_call' else 'Tool unavailable; please clarify')
        if failure != 'no_call':
            assert response.json()['tool_calls'][0]['status'] == 'failed'
            assert send(client, result['id']).status_code == 200


def test_unknown_runtime_type_fails_explicitly_instead_of_silently_dropping_tool(workspace):
    client, get_db = workspace
    with get_db() as db:
        db.get(Tool, 2).config = {'type': 'unknown', 'auth_token': 'hidden'}
        db.add(AgentTool(agent_id=1, tool_id=2))
    result = create(client)
    assert result.status_code == 503 and 'hidden' not in result.text
    assert not preview._sessions


def test_disabled_mcp_is_a_failed_tool_not_a_successful_answer(workspace, monkeypatch):
    from agents import RunContextWrapper
    client, get_db = workspace
    with get_db() as db:
        db.get(Tool, 2).type = 'mcp_streamable_http'
        db.get(Tool, 2).config = {'type': 'mcp_streamable_http', 'endpoint': 'https://mcp.invalid', 'auth_token': 'never-show'}
        db.add(AgentTool(agent_id=1, tool_id=2))
    monkeypatch.setenv('DISABLE_MCP', 'true')
    async def run(agent, history, **kwargs):
        tool = next(tool for tool in agent.tools if tool.name != 'DateTimeTool')
        await tool.on_invoke_tool(RunContextWrapper(context=None), '{"query":"VIN"}')
        return SimpleNamespace(new_items=[], last_agent=agent, final_output='Tool unavailable', to_input_list=lambda: history)
    monkeypatch.setattr(preview.Runner, 'run', run)
    result = create(client, {'target_agent_id': 1}).json()
    response = send(client, result['id'])
    assert response.status_code == 200
    assert response.json()['status'] == 'completed'
    assert 'never-show' not in response.text


def test_parallel_function_calls_stop_after_first_failure_without_second_write(workspace, monkeypatch):
    from agents import RunContextWrapper
    from app import agent_config
    client, get_db = workspace
    with get_db() as db: db.add(AgentTool(agent_id=1, tool_id=2))
    writes = []
    def fail(*args, **kwargs):
        writes.append(True)
        raise RuntimeError('failed after write')
    monkeypatch.setattr(agent_config.requests, 'post', fail)
    async def run(agent, history, **kwargs):
        tool = next(tool for tool in agent.tools if tool.name == 'OwnTool')
        await asyncio.gather(*(tool.on_invoke_tool(RunContextWrapper(context=None), '{"query":"write"}') for _ in range(2)))
        return SimpleNamespace(new_items=[], last_agent=agent, final_output='Tool unavailable', to_input_list=lambda: history)
    monkeypatch.setattr(preview.Runner, 'run', run)
    result = create(client, {'target_agent_id': 1}).json()
    response = send(client, result['id'])
    assert response.json()['status'] == 'completed'
    assert len(writes) == 1


def test_private_log_records_redact_credentials_without_changing_other_contexts(caplog):
    import logging
    from app.preview_tools import install_log_redaction, log_secrets, credential_values
    secrets = credential_values([{'llm_provider': {'api_key': 'provider-42'}, 'tools': [{'config': '{"auth_token":"api-42","request":{"headers":[{"name":"X-API-Key","value":"header-42"}]}}'}]}])
    install_log_redaction()
    token = log_secrets.set(secrets)
    try:
        with caplog.at_level(logging.WARNING):
            try: raise RuntimeError('api-42')
            except RuntimeError:
                logging.getLogger('httpx').warning('Request ?apikey=%s provider=%s X-API-Key=%s', 'api-42', 'provider-42', 'header-42', exc_info=True)
        assert all(value not in caplog.text for value in ('api-42', 'provider-42', 'header-42'))
        assert '[REDACTED]' in caplog.text
    finally:
        log_secrets.reset(token)
    caplog.clear()
    with caplog.at_level(logging.WARNING): logging.getLogger('httpx').warning('Outside private session')
    assert 'Outside private session' in caplog.text


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
    monkeypatch.setattr(preview, "MAX_REQUEST_BYTES", 1000)
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
    import app.utils as utils
    monkeypatch.setattr(utils, "hydrate_knowledge_images", hydrate)
    monkeypatch.setattr(utils, "hydrate_knowledge_media", lambda *args: None)
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
        assert preview._sessions[first].history[-1]["content"] == "late"
        assert preview._sessions[first].last_reply["response"] == "late"
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
