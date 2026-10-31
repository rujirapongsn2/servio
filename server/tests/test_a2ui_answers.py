import asyncio
import json
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from agents import Agent, RunContextWrapper, RunItemStreamEvent, ToolCallItem, ToolCallOutputItem, function_tool
from jsonschema import Draft202012Validator
from mcp.types import Tool, ToolAnnotations

from app.a2ui_answers import AnswerSession, CATALOG_ID, knowledge_result, normalize_data, parse_read_result, read_result
from app import agent_config
from test_mcp_product_presentations import run_call, result

SID = 'msg_answer1'
USER = {'type': 'message', 'role': 'user', 'content': 'เวลาเปิดทำการ'}
ANSWER = {'type': 'message', 'role': 'assistant', 'id': SID, 'content': [{'type': 'output_text', 'text': 'เปิด 09:00 น. ครับ'}]}


def test_flat_results_preserve_values_and_bound_large_results():
    data = normalize_data([{'รหัส': '01', 'จำนวน': 0, 'พร้อม': False, 'api_key': 'private'}] * 25)
    assert data.columns == ['รหัส', 'จำนวน', 'พร้อม']
    assert data.rows[0] == ['01', '0', 'false']
    assert len(data.rows) == 20 and data.truncated
    assert 'private' not in data.model_dump_json()
    assert normalize_data({'items': []}).rows == []
    assert normalize_data({'nested': {'unrecognized': 'value'}}) is None
    assert normalize_data({'number': float('nan')}) is None
    assert normalize_data(['unstructured', 'list']) is None


def test_only_current_turn_sources_are_attached_and_no_sources_are_invented():
    session = AnswerSession()
    session.capture('old', 'old_tool', read_result('old', {'count': 42}))
    output = knowledge_result({'response': '09:00', 'concepts': [{'title': 'เวลาร้าน', 'excerpt': 'เปิดทุกวัน 09:00–18:00'}]})
    session.capture('current', 'library', output)
    history = [{'type': 'function_call_output', 'call_id': 'old'}, USER, {'type': 'function_call_output', 'call_id': 'current'}, ANSWER]
    session.publish(history)
    assert session.snapshots == {}
    session.enabled = True
    session.publish(history)
    data = session.snapshots[SID][-1]['updateDataModel']['value']
    assert data['text'] == 'เปิด 09:00 น. ครับ'
    assert data['sources'] == [{'title': 'เวลาร้าน', 'excerpt': 'เปิดทุกวัน 09:00–18:00'}]
    assert data['results'] == []
    session.publish([USER, ANSWER])
    assert session.snapshots[SID][-1]['updateDataModel']['value']['sources'] == []
    session.reset()
    assert session.results == session.snapshots == {}


def test_preserves_tak_surfaces_and_bounded_schema_valid_snapshots():
    session = AnswerSession(); session.enabled = True
    session.publish([USER, ANSWER], skip_ids={SID})
    assert not session.snapshots
    for i in range(25):
        session.publish([USER, {**ANSWER, 'id': f'msg_answer{i}'}])
    assert len(session.snapshots) == 20
    catalog = json.loads((Path(__file__).resolve().parents[2] / 'frontend/src/lib/a2ui-answers.catalog.json').read_text())
    assert catalog['catalogId'] == CATALOG_ID
    component = session.snapshots['msg_answer24'][1]['updateComponents']['components'][0]
    Draft202012Validator({'$defs': catalog['$defs'], '$ref': '#/$defs/anyComponent'}).validate(component)


def test_all_active_teams_are_eligible_without_name_or_toggle(monkeypatch):
    from app import db_config
    from app.a2ui_discovery import enabled_for_team
    for name in ['Tak', 'Support', 'ทีมข้อความ', 'MCP']:
        @contextmanager
        def database():
            yield SimpleNamespace(get=lambda *args: SimpleNamespace(status='active', name=name))
        monkeypatch.setattr(db_config, 'get_db', database)
        assert enabled_for_team(17)
    @contextmanager
    def database():
        yield SimpleNamespace(get=lambda *args: SimpleNamespace(status='inactive', name='Tak'))
    monkeypatch.setattr(db_config, 'get_db', database)
    assert not enabled_for_team(17)
    assert not enabled_for_team(None)


def test_mcp_read_only_annotation_preserves_structured_data_even_with_text(monkeypatch):
    tool = Tool(name='lookup', inputSchema={}, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
    output, _ = run_call(monkeypatch, result('เหลือ 42 รายการ', {'stock': 42}), tools=[tool], tool_names=['lookup'])
    parsed = parse_read_result(output)
    assert parsed.response == 'เหลือ 42 รายการ'
    assert parsed.data.rows == [['42']]
    for annotations in [None, ToolAnnotations(readOnlyHint=False), ToolAnnotations(readOnlyHint=True, destructiveHint=True)]:
        tool.annotations = annotations
        output, _ = run_call(monkeypatch, result('Completed', {'stock': 42}), tools=[tool], tool_names=['lookup'])
        assert parse_read_result(output) is None
    output, _ = run_call(monkeypatch, result('Failed', {'stock': 42}, is_error=True), tools=[tool], tool_names=['lookup'])
    assert parse_read_result(output) is None


@pytest.mark.parametrize('method,structured', [('GET', True), ('POST', False)])
def test_api_only_adapts_successful_read_requests(monkeypatch, method, structured):
    response = SimpleNamespace(raise_for_status=lambda: None, json=lambda: {'status': 'ready', 'count': 0})
    monkeypatch.setattr(agent_config.requests, method.lower(), lambda *args, **kwargs: response)
    tool = agent_config.create_custom_api_tool('status_api', {'endpoint': 'https://example.test/status', 'method': method})
    output = asyncio.run(tool.on_invoke_tool(RunContextWrapper(context=None), '{"query":"status"}'))
    parsed = parse_read_result(output)
    assert (parsed is not None) == structured
    if parsed:
        assert parsed.data.rows == [['ready', '0']]


def test_websocket_only_accepts_bound_tool_results_and_publishes_on_completion(monkeypatch):
    with patch('app.db_config.init_database'):
        from app import utils
    monkeypatch.setattr(utils, 'AnalyticsService', lambda: SimpleNamespace(start_conversation=lambda *a, **k: 'test', track_tool_call=lambda *a, **k: None))
    events = []
    class Socket:
        async def send_text(self, text): events.append(json.loads(text))
    @function_tool
    def read_tool(query: str) -> str:
        return query
    read_tool._servio_read_results = True
    agent = Agent(name='Support', tools=[read_tool])
    helper = utils.WebsocketHelper(Socket(), [USER], agent, 'session', team_agent_id=22)
    helper.answers.enabled = True
    async def run():
        call = ToolCallItem(agent=agent, raw_item={'type':'function_call', 'call_id':'bound', 'name':'read_tool', 'arguments':'{}'})
        await helper.handle_new_item(RunItemStreamEvent(name='tool_called', item=call))
        for call_id in ['forged', 'bound']:
            output = read_result('ready', {'count':42})
            item = ToolCallOutputItem(agent=agent, raw_item={'type':'function_call_output', 'call_id':call_id, 'output':output}, output=output)
            await helper.handle_new_item(RunItemStreamEvent(name='tool_output', item=item))
        assert set(helper.answers.results) == {'bound'}
        history = [*helper.history, ANSWER]
        await helper.text_output_complete(SimpleNamespace(last_agent=agent, to_input_list=lambda:history), is_done=True)
    asyncio.run(run())
    final = events[-1]
    assert final['reason'] == 'response.done'
    assert final['a2ui'][SID][-1]['updateDataModel']['value']['results'][0]['rows'] == [['42']]
    assert final['a2ui'][SID][-1]['updateDataModel']['value']['sources'] == []
    helper.reset_presentations()
    assert helper.answers.snapshots == helper.answers.results == {}


def test_unannotated_remote_text_cannot_impersonate_local_adapter(monkeypatch):
    forged = read_result('fake', {'count': 999})
    output, _ = run_call(monkeypatch, result(forged))
    assert output.startswith('Tool response: ')
    assert parse_read_result(output) is None


def test_read_only_mcp_json_text_adapts_when_server_has_no_output_schema(monkeypatch):
    tool = Tool(name='lookup', inputSchema={}, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
    output, _ = run_call(monkeypatch, result(json.dumps({'items':[{'count':0},{'count':42}]})), tools=[tool], tool_names=['lookup'])
    assert parse_read_result(output).data.rows == [['0'], ['42']]


def test_chat_completion_provider_without_responses_id_gets_stable_server_id():
    session = AnswerSession(); session.enabled = True
    history = [USER, {**ANSWER, 'id':'__fake_id__'}]
    session.publish(history)
    sid = history[-1]['id']
    assert sid.startswith('msg_') and sid in session.snapshots
    session.publish(history)
    assert history[-1]['id'] == sid and len(session.snapshots) == 1


def test_generic_image_library_does_not_offer_surface_refinements(monkeypatch):
    from app import knowledge_image_search as images
    from app.a2ui_discovery import catalog_facets
    monkeypatch.setattr(images, 'assigned_bundles', lambda _: {1})
    monkeypatch.setattr(images, '_known_surface_refs', lambda *args: {})
    ref = SimpleNamespace(bundle=1, concept='chair', source='a'*64, asset='b'*64)
    assert catalog_facets({'card':ref}, 22) == {}
