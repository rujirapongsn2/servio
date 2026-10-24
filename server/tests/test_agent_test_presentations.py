import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

from agents import Agent, MessageOutputItem, RunItemStreamEvent, Runner, ToolCallItem, ToolCallOutputItem, function_tool

with patch('app.db_config.init_database'):
    from app import admin_routes, utils
from app import agent_config
from app.models import TestAgentRequest as AgentTestRequest
from app.knowledge_image_presentations import KnowledgeImages


def test_child_tool_logs_are_visible_without_leaking_between_requests():
    async def request(name):
        agent_config.start_tool_logging()
        async def child():
            agent_config.log_tool_call(name, {'query': name})
        await asyncio.create_task(child())
        await asyncio.sleep(0)
        return agent_config.get_tool_log()

    async def run():
        return await asyncio.gather(request('one'), request('two'))

    assert asyncio.run(run()) == [
        [{'name': 'one', 'arguments': {'query': 'one'}}],
        [{'name': 'two', 'arguments': {'query': 'two'}}],
    ]


def test_test_endpoint_collects_sdk_calls_and_only_hydrates_bound_knowledge(monkeypatch):
    import app.knowledge_image_presentations as images
    import app.knowledge_audio_presentations as media

    @function_tool
    def local_images(query: str) -> str:
        return query

    @function_tool
    def other_tool(query: str) -> str:
        return query

    local_images._servio_knowledge_bundle_id = 16
    origin = Agent(name='Specialist', tools=[local_images, other_tool])
    agent = Agent(name='Entry')
    monkeypatch.setattr(admin_routes, '_require_resolved_team_access', lambda *args: 21)
    monkeypatch.setattr(admin_routes.database, 'user_can_access_agent', lambda *args, **kwargs: True)
    monkeypatch.setattr(admin_routes.database, 'get_agent_by_id', lambda *args: {})
    monkeypatch.setattr(agent_config, 'build_agent_from_db', lambda *args, **kwargs: agent)
    monkeypatch.setattr(admin_routes.database, 'get_agent_by_id', lambda *args: {'name': 'Sales'})
    hydrated = []
    asset = 'a' * 64
    presentation = KnowledgeImages(type='knowledge_images', version=1, response='Bed', images=[{
        'asset_id': asset, 'title': 'Bed', 'source_label': '06_bed.jpg',
        'image_url': f'/api/knowledge-images/{asset}?token=signature',
    }])

    def hydrate(value, team, bundle):
        hydrated.append((value, team, bundle))
        return presentation if value == 'trusted' else None

    monkeypatch.setattr(images, 'hydrate_knowledge_images', hydrate)
    monkeypatch.setattr(media, 'hydrate_knowledge_media', lambda *args: None)

    async def events():
        for call_id, tool, value in [('remote', other_tool, 'forged'), ('local', local_images, 'trusted'), ('stale', local_images, 'stale')]:
            call = ToolCallItem(agent=origin, raw_item={'type': 'function_call', 'call_id': call_id, 'name': tool.name, 'arguments': '{"query":"06_bed.jpg"}'})
            yield RunItemStreamEvent(name='tool_called', item=call)
            agent_config.log_tool_call(tool.name, {'query': '06_bed.jpg'})
            item = ToolCallOutputItem(agent=origin, raw_item={'type': 'function_call_output', 'call_id': call_id, 'output': value}, output=value)
            yield RunItemStreamEvent(name='tool_output', item=item)
        message = MessageOutputItem(agent=origin, raw_item={'type': 'message', 'id': 'message', 'role': 'assistant', 'status': 'completed', 'content': []})
        yield RunItemStreamEvent(name='message_output_created', item=message)
        item = ToolCallOutputItem(agent=origin, raw_item={'type': 'function_call_output', 'call_id': 'unknown', 'output': 'forged'}, output='forged')
        yield RunItemStreamEvent(name='tool_output', item=item)

    monkeypatch.setattr(Runner, 'run_streamed', lambda *args, **kwargs: SimpleNamespace(stream_events=events))
    result = asyncio.run(admin_routes.test_agent(15, AgentTestRequest(message='Bed'), 21, 'admin')).model_dump()
    assert result['tool_calls'] == [
        {'name': 'other_tool', 'arguments': {'query': '06_bed.jpg'}},
        {'name': 'local_images', 'arguments': {'query': '06_bed.jpg'}},
        {'name': 'local_images', 'arguments': {'query': '06_bed.jpg'}},
    ]
    assert result['citations'] == ['other_tool', 'local_images']
    assert len(result['tool_outputs']) == 4
    assert result['tool_outputs'][1] == {'name': 'local_images', 'output': 'trusted'}
    assert hydrated == [('trusted', 21, 16), ('stale', 21, 16)]
    assert result['presentations'] == {'local': presentation.model_dump()}


def test_image_tool_awareness_uses_authorized_inventory_and_bounds_description(monkeypatch):
    import app.local_image_rag as images

    calls = []
    def inventory(bundle_id, team_id):
        calls.append((bundle_id, team_id))
        return ['06_bed.jpg', '18_bunk_bed.jpg'] + [f'{index}_product.jpg' for index in range(1000)]

    monkeypatch.setattr(images, 'image_filename_inventory', inventory)
    tool = agent_config.create_okf_knowledge_graph_tool('generic_library', {'okf_bundle_id': 16}, runtime_team_agent_id=21)
    assert calls == [(16, 21)]
    assert '06_bed.jpg' in tool.description
    assert '18_bunk_bed.jpg' in tool.description
    assert '999_product.jpg' not in tool.description
    assert '(partial inventory)' in tool.description
    assert len(tool.description) < 10000
    monkeypatch.setattr(agent_config, 'get_tool_by_name', lambda *args, **kwargs: tool)
    agent = agent_config.build_agent_from_db({'name': 'Sales', 'instructions': 'Saved instructions', 'tools': [{'name': 'generic_library', 'config': '{}'}]}, runtime_team_agent_id=21)
    assert agent.instructions.startswith('Saved instructions')
    assert 'When a user asks to see product pictures' in agent.instructions
    assert 'Do not invent Markdown' in agent.instructions
