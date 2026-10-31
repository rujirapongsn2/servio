"""Knowledge searches are reused within a run, never across user turns."""
import asyncio
import json

from agents import RunContextWrapper

from app import agent_config, okf_service
from test_knowledge_runtime_scope import runtime


def tool_for_team(team=1):
    return agent_config.create_okf_knowledge_graph_tool('knowledge_search', {'okf_bundle_id': 1}, runtime_team_agent_id=team)


def test_same_question_searches_once_within_a_turn(runtime):
    _, _, searches, _ = runtime
    tool = tool_for_team()
    async def run():
        context = RunContextWrapper(context=None)
        first = await tool.on_invoke_tool(context, '{"query":"refund"}')
        second = await tool.on_invoke_tool(context, '{"query":" REFUND  "}')
        assert first == second and 'ALPHA-7391' in first
    asyncio.run(run())
    assert searches == ['refund']


def test_parallel_duplicates_share_one_search(runtime):
    _, _, searches, _ = runtime
    tool = tool_for_team()
    async def run():
        context = RunContextWrapper(context=None)
        outputs = await asyncio.gather(*[tool.on_invoke_tool(context, '{"query":"refund"}') for _ in range(3)])
        assert all('ALPHA-7391' in output for output in outputs)
    asyncio.run(run())
    assert searches == ['refund']


def test_new_turn_searches_again_and_different_questions_are_independent(runtime):
    _, _, searches, _ = runtime
    tool = tool_for_team()
    async def run():
        first = RunContextWrapper(context=None)
        await tool.on_invoke_tool(first, '{"query":"refund"}')
        await tool.on_invoke_tool(first, '{"query":"warranty"}')
        await tool.on_invoke_tool(RunContextWrapper(context=None), '{"query":"refund"}')
    asyncio.run(run())
    assert searches == ['refund', 'warranty', 'refund']


def test_same_context_does_not_share_private_results_with_another_team(runtime):
    owner = tool_for_team(1)
    other = tool_for_team(2)
    async def run():
        context = RunContextWrapper(context=None)
        assert 'ALPHA-7391' in await owner.on_invoke_tool(context, '{"query":"refund"}')
        assert 'ALPHA-7391' not in await other.on_invoke_tool(context, '{"query":"refund"}')
    asyncio.run(run())


def test_failed_search_can_be_retried_within_the_same_turn(runtime, monkeypatch):
    attempts = []
    def search(self, **kwargs):
        attempts.append(kwargs['query'])
        if len(attempts) == 1:
            raise RuntimeError('temporary search failure')
        return {'response': 'Recovered product evidence'}
    monkeypatch.setattr(okf_service.OKFService, 'query_bundle', search)
    tool = tool_for_team()
    async def run():
        context = RunContextWrapper(context=None)
        assert 'Error searching' in await tool.on_invoke_tool(context, '{"query":"refund"}')
        assert json.loads(await tool.on_invoke_tool(context, '{"query":"refund"}'))["response"] == 'Recovered product evidence'
    asyncio.run(run())
    assert attempts == ['refund', 'refund']


def test_quoted_filename_spaces_remain_distinct(runtime):
    _, _, searches, _ = runtime
    tool = tool_for_team()
    async def run():
        context = RunContextWrapper(context=None)
        for query in ['"red  sofa.png"', '"red sofa.png"']:
            await tool.on_invoke_tool(context, json.dumps({'query': query}))
    asyncio.run(run())
    assert searches == ['"red  sofa.png"', '"red sofa.png"']
