"""Persisted HTTP coverage for Workflow membership and deletion."""
from concurrent.futures import ThreadPoolExecutor
import pytest
from test_workflow_creation import workspace, headers
from app.orm_models import Agent, AgentHandoff, AgentTool, TeamAgentMember, TeamUserMembership

@pytest.fixture
def populated(workspace):
    (client, get_db) = workspace
    with get_db() as db:
        db.add_all([Agent(id=3, name='Candidate', instructions='candidate-secret', model='test'), Agent(id=4, name='Orphan', instructions='orphan-secret', model='test')])
        db.flush()
        db.add(TeamAgentMember(team_agent_id=3, agent_id=3, role='starting'))
        db.add_all([AgentHandoff(from_agent_id=1, to_agent_id=2), AgentHandoff(from_agent_id=3, to_agent_id=1), AgentTool(agent_id=1, tool_id=2)])
    return (client, get_db)

def members(client, ids, fallback, expected_ids=None, expected_fallback=1, user='owner'):
    return client.put('/api/admin/team-agents/1/workflow/members', headers=headers(user), json={'member_agent_ids': ids, 'fallback_agent_id': fallback, 'expected_member_agent_ids': [1] if expected_ids is None else expected_ids, 'expected_fallback_agent_id': expected_fallback})

def deletion(client, get_db, agent_id=1, **changes):
    with get_db() as db:
        agent = db.get(Agent, agent_id)
        body = {'expected_updated_at': agent.updated_at.isoformat() if agent and agent.updated_at else None, 'expected_member_agent_ids': [1], 'expected_fallback_agent_id': 1, 'replacement_fallback_agent_id': None}
    user = changes.pop('user', 'owner')
    body.update(changes)
    return client.request('DELETE', f'/api/admin/team-agents/1/workflow/agents/{agent_id}', headers=headers(user), json=body)

def snapshot(client):
    response = client.get('/api/admin/team-agents/1/workflow', headers=headers())
    assert response.status_code == 200
    return response.json()

def test_options_only_exposes_accessible_metadata(populated):
    (client, _) = populated
    response = client.get('/api/admin/team-agents/1/workflow/member-options', headers=headers())
    assert response.status_code == 200
    options = response.json()['agents']
    assert {item['id'] for item in options} == {1, 3}
    assert all((set(item) == {'id', 'name', 'model', 'shared', 'membership_count'} for item in options))
    assert 'secret' not in response.text

@pytest.mark.parametrize('user', ['viewer', 'other'])
def test_admin_required(populated, user):
    (client, get_db) = populated
    assert members(client, [], None, user=user).status_code == 403
    assert client.get('/api/admin/team-agents/1/workflow/member-options', headers=headers(user)).status_code == 403
    assert deletion(client, get_db, user=user).status_code == 403
    assert [item['id'] for item in snapshot(client)['agents']] == [1]

def test_membership_preserves_configs_other_teams_and_handoffs(populated):
    (client, get_db) = populated
    response = members(client, [3, 1], 3)
    assert response.status_code == 200, response.text
    data = snapshot(client)
    assert [agent['id'] for agent in data['agents']] == [3, 1]
    assert data['fallback_agent_id'] == 3
    assert data['agents'][0]['shared']
    with get_db() as db:
        assert db.get(TeamAgentMember, (3, 3)).role == 'starting'
        assert db.get(TeamAgentMember, (2, 2)).role == 'starting'
        assert db.get(Agent, 1).is_starting_agent
        assert not db.get(Agent, 3).is_starting_agent
        assert db.get(Agent, 3).instructions == 'candidate-secret'
        assert db.get(AgentHandoff, (1, 2)) and db.get(AgentHandoff, (3, 1))
        assert db.get(AgentTool, (1, 2))
    assert members(client, [1], 1, expected_ids=[3, 1], expected_fallback=3).status_code == 200
    with get_db() as db:
        assert db.get(Agent, 3) and db.get(TeamAgentMember, (3, 3)) and db.get(AgentHandoff, (3, 1))

@pytest.mark.parametrize('ids,fallback,status', [([1, 2], 1, 403), ([1, 4], 1, 403), ([1, 999], 1, 400), ([1], None, 400), ([], 1, 400), ([1], 3, 400)])
def test_invalid_membership_rolls_back(populated, ids, fallback, status):
    (client, _) = populated
    response = members(client, ids, fallback)
    assert response.status_code == status, response.text
    assert [agent['id'] for agent in snapshot(client)['agents']] == [1]
    assert snapshot(client)['fallback_agent_id'] == 1

@pytest.mark.parametrize('ids', [[True], ['1'], [1.0], [0], [-1], [1, 1]])
def test_ids_are_strict_positive_unique(populated, ids):
    (client, _) = populated
    assert members(client, ids, 1).status_code == 422
    assert members(client, [1], 1, expected_ids=ids).status_code == 422

def test_stale_order_fallback_and_replay(populated):
    (client, _) = populated
    assert members(client, [1, 3], 1).status_code == 200
    assert members(client, [3, 1], 3).status_code == 409
    assert members(client, [3, 1], 3, expected_ids=[3, 1]).status_code == 409
    assert members(client, [3, 1], 3, expected_ids=[1, 3], expected_fallback=3).status_code == 409
    assert members(client, [1, 3], 1).status_code == 200
    assert members(client, [3, 1], 3, expected_ids=[1, 3]).status_code == 200

def test_concurrent_conflict_and_identical_retry(populated):
    (client, _) = populated
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: members(client, [1, 3], 1), range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda args: members(client, *args, expected_ids=[1, 3]), [([3], 3), ([3, 1], 3)]))
    assert sorted((response.status_code for response in responses)) == [200, 409]

def test_empty_membership_retains_agent_config_and_links(populated):
    (client, get_db) = populated
    assert members(client, [], None).status_code == 200
    assert snapshot(client)['agents'] == []
    with get_db() as db:
        assert db.get(Agent, 1) and db.get(AgentTool, (1, 2)) and db.get(AgentHandoff, (1, 2))
    assert members(client, [1], 1, expected_ids=[], expected_fallback=None).status_code == 403
    assert members(client, [3], 3, expected_ids=[], expected_fallback=None).status_code == 200

def test_authorization_uses_current_membership(populated):
    (client, get_db) = populated
    with get_db() as db:
        db.query(TeamUserMembership).filter_by(admin_id=1, team_agent_id=3).delete()
    assert members(client, [1, 3], 1).status_code == 403
    options = client.get('/api/admin/team-agents/1/workflow/member-options', headers=headers()).json()['agents']
    assert {item['id'] for item in options} == {1}

def test_delete_last_agent_preserves_other_teams(populated):
    (client, get_db) = populated
    response = deletion(client, get_db)
    assert response.status_code == 200, response.text
    assert response.json() == {'agent_id': 1}
    assert snapshot(client)['agents'] == []
    with get_db() as db:
        assert db.get(Agent, 1) is None
        assert db.get(Agent, 2).instructions == 'outside'
        assert db.get(TeamAgentMember, (2, 2)).role == 'starting'
        assert db.get(TeamAgentMember, (3, 3)).role == 'starting'
        assert db.query(AgentHandoff).count() == 0 and db.query(AgentTool).count() == 0

def test_shared_agent_rejects_delete_and_edit(populated):
    (client, get_db) = populated
    assert members(client, [1, 3], 1).status_code == 200
    assert deletion(client, get_db, 3, expected_member_agent_ids=[1, 3], replacement_fallback_agent_id=1).status_code == 409
    with get_db() as db:
        agent = db.get(Agent, 3)
        body = {'name': 'Changed', 'instructions': 'new', 'model': 'test', 'tool_ids': [], 'handoff_agent_ids': [], 'is_fallback': False, 'expected_updated_at': agent.updated_at.isoformat(), 'expected_fallback_agent_id': 1}
    response = client.put('/api/admin/team-agents/1/workflow/agents/3', headers=headers(), json=body)
    assert response.status_code == 409
    with get_db() as db:
        assert db.get(Agent, 3).name == 'Candidate' and db.get(TeamAgentMember, (3, 3))

@pytest.mark.parametrize('changes', [{'expected_updated_at': None}, {'expected_member_agent_ids': []}, {'expected_fallback_agent_id': None}])
def test_delete_conflicts_do_not_mutate(populated, changes):
    (client, get_db) = populated
    assert deletion(client, get_db, **changes).status_code == 409
    with get_db() as db:
        assert db.get(Agent, 1) and db.get(AgentTool, (1, 2))
        assert db.get(TeamAgentMember, (1, 1)).role == 'starting'

def test_delete_fallback_needs_explicit_replacement(populated):
    (client, get_db) = populated
    assert members(client, [1, 3], 1).status_code == 200
    assert deletion(client, get_db, expected_member_agent_ids=[1, 3]).status_code == 400
    assert deletion(client, get_db, expected_member_agent_ids=[1, 3], replacement_fallback_agent_id=2).status_code == 400
    response = deletion(client, get_db, expected_member_agent_ids=[1, 3], replacement_fallback_agent_id=3)
    assert response.status_code == 200, response.text
    assert snapshot(client)['fallback_agent_id'] == 3
    with get_db() as db:
        assert db.get(TeamAgentMember, (3, 3)).role == 'starting'

def test_delete_nonfallback_keeps_current_fallback(populated):
    (client, get_db) = populated
    with get_db() as db:
        db.add(Agent(id=5, name='Disposable', instructions='local', model='test'))
        db.flush()
        db.add(TeamAgentMember(team_agent_id=1, agent_id=5, role='member', sort_order=1))
    assert deletion(client, get_db, 5, expected_member_agent_ids=[1, 5]).status_code == 400
    assert deletion(client, get_db, 5, expected_member_agent_ids=[1, 5], replacement_fallback_agent_id=1).status_code == 200
    assert snapshot(client)['fallback_agent_id'] == 1

def test_delete_outside_agent_not_found(populated):
    (client, get_db) = populated
    assert deletion(client, get_db, 2).status_code == 404
    with get_db() as db:
        assert db.get(Agent, 2)

@pytest.mark.parametrize('user', ['owner', 'viewer', 'other'])
def test_provider_creation_still_requires_superadmin(populated, user):
    (client, get_db) = populated
    response = client.post('/api/admin/llm-providers', headers=headers(user), json={'name': 'Inline provider', 'base_url': 'https://provider.example/v1', 'api_key': 'secret'})
    assert response.status_code == 403
    from app.orm_models import LLMProvider
    with get_db() as db:
        assert db.query(LLMProvider).count() == 2

def test_provider_creation_returns_structured_id(populated, monkeypatch):
    from contextlib import contextmanager
    from sqlalchemy.orm import Session
    from app import database
    from app.orm_models import Admin, LLMProvider
    (client, get_db) = populated
    with get_db() as db:
        db.get(Admin, 1).is_super_admin = True
        engine = db.bind

    @contextmanager
    def provider_db():
        with Session(engine) as db:
            yield db
            db.commit()
    monkeypatch.setattr(database, 'get_db', provider_db)
    response = client.post('/api/admin/llm-providers', headers=headers(), json={'name': 'Inline provider', 'base_url': 'https://provider.example/v1', 'api_key': 'secret'})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['success'] is True and body['provider_id'] > 0
    assert 'created successfully' in body['message']
    assert 'secret' not in response.text
    with get_db() as db:
        assert db.get(LLMProvider, body['provider_id']).name == 'Inline provider'


@pytest.mark.parametrize("bad_id", [True, "1", 0, -1, 1.0])
def test_fallback_ids_are_strict(populated, bad_id):
    client, get_db = populated
    assert members(client, [1], bad_id).status_code == 422
    assert members(client, [1], 1, expected_fallback=bad_id).status_code == 422
    assert deletion(client, get_db, replacement_fallback_agent_id=bad_id).status_code == 422


def test_superadmin_may_assign_unassigned_and_other_team_agents(populated):
    from app.orm_models import Admin
    client, get_db = populated
    with get_db() as db:
        db.get(Admin, 1).is_super_admin = True
    options = client.get("/api/admin/team-agents/1/workflow/member-options", headers=headers()).json()["agents"]
    assert {item["id"] for item in options} == {1, 2, 3, 4}
    assert members(client, [1, 2, 4], 1).status_code == 200
    with get_db() as db:
        assert db.get(TeamAgentMember, (2, 2)).role == "starting"
        assert db.get(Agent, 2).instructions == "outside"


def test_legacy_no_user_memberships_retains_all_access(populated):
    client, get_db = populated
    with get_db() as db:
        db.query(TeamUserMembership).delete()
    assert members(client, [1, 2, 4], 4).status_code == 200
    assert snapshot(client)["fallback_agent_id"] == 4


@pytest.mark.parametrize("user", ["viewer", "other"])
def test_scoped_optimizer_requires_team_admin(populated, user):
    client, _ = populated
    response = client.post("/api/admin/agents/optimize-prompt?team_agent_id=1", headers=headers(user), json={
        "instructions": "Support customers", "llm_provider_id": 1})
    assert response.status_code == 403


def test_scoped_optimizer_preserves_legacy_behavior_and_does_not_save(populated, monkeypatch):
    from types import SimpleNamespace
    import openai
    calls = []

    def create(**arguments):
        calls.append(arguments)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=" Optimized instructions "))])

    monkeypatch.setattr(openai, "OpenAI", lambda **kwargs: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    client, get_db = populated
    for url in ["/api/admin/agents/optimize-prompt?team_agent_id=1", "/api/admin/agents/optimize-prompt"]:
        response = client.post(url, headers=headers(), json={"instructions": "Support customers", "llm_provider_id": 1})
        assert response.status_code == 200, response.text
        assert response.json() == {"optimized_instructions": "Optimized instructions"}
    assert len(calls) == 2
    with get_db() as db:
        assert db.get(Agent, 1).instructions == "old"


@pytest.mark.parametrize("model", ["luna", "gpt-6-luna", "gpt-4o-mini"])
@pytest.mark.parametrize("query", ["", "?team_agent_id=1"])
def test_optimizer_supports_provider_default_sampling(populated, monkeypatch, model, query):
    from types import SimpleNamespace
    import httpx
    import openai

    calls = []
    client_options = []

    def create(**arguments):
        calls.append(arguments)
        if "temperature" in arguments:
            message = "Unsupported value: 'temperature' does not support 0.7 with this model. Only the default (1) value is supported."
            raise openai.BadRequestError(
                message,
                response=httpx.Response(400, request=httpx.Request("POST", "https://provider.example/v1/chat/completions")),
                body={"error": {"message": message, "param": "temperature", "code": "unsupported_value"}},
            )
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=" Optimized instructions "))])

    def configured_client(**options):
        client_options.append(options)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setattr(openai, "OpenAI", configured_client)
    client, get_db = populated
    response = client.post(
        f"/api/admin/agents/optimize-prompt{query}",
        headers=headers(),
        json={"instructions": "Support customers", "llm_provider_id": 1, "model": model},
    )
    assert response.status_code == 200, response.text
    assert response.json() == {"optimized_instructions": "Optimized instructions"}
    assert client_options == [{"api_key": "secret", "base_url": "https://provider.example/v1"}]
    assert len(calls) == 1
    assert calls[0]["model"] == model
    assert "Support customers" in calls[0]["messages"][1]["content"]
    with get_db() as db:
        agent = db.get(Agent, 1)
        assert (agent.instructions, agent.model) == ("old", "test")
