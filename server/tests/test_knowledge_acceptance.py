"""Opt-in acceptance checks against real PostgreSQL/pgvector and local embeddings.

Run this module alone with SERVIO_KNOWLEDGE_ACCEPTANCE=1, an empty disposable
DATABASE_URL named servio_knowledge_checks_*, embedding environment settings,
and a configured JWT_SECRET_KEY. The SDK model is deterministic; no cloud LLM
or tracing API is called. Embedding failures are simulated only in-process.
"""
import asyncio
import json
import os
import zipfile

import pytest

if os.getenv("SERVIO_KNOWLEDGE_ACCEPTANCE") != "1":
    pytest.skip("Opt-in PostgreSQL/embedding acceptance test; run separately on an empty disposable database", allow_module_level=True)

from sqlalchemy.engine import make_url

url = make_url(os.environ["DATABASE_URL"])
if not url.database or not url.database.startswith("servio_knowledge_checks_"):
    raise RuntimeError("Acceptance tests require a disposable servio_knowledge_checks_* database")
os.environ['OPENAI_AGENTS_DISABLE_TRACING'] = '1'

from fastapi.testclient import TestClient
from server import app
from app import database, local_rag
from app.auth import create_access_token
from app.db_config import get_db, engine
from app.orm_models import TeamAgent, Admin, TeamUserMembership, TeamToolAssignment, Tool
from app.okf_service import OKFService
from app.agent_config import get_runtime_starting_agent
from agents import RunContextWrapper, Model, ModelResponse, Usage, Runner, RunConfig
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputMessage, ResponseOutputText
from sqlalchemy import text

if engine.url.database != url.database:
    raise RuntimeError('Application database does not match the disposable acceptance database')


def auth(user):
    return {'Authorization': 'Bearer ' + create_access_token({'sub': user})}


@pytest.fixture(scope='module')
def isolated_storage(tmp_path_factory):
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv('OKF_STORAGE_DIR', str(tmp_path_factory.mktemp('knowledge-storage')))
        yield


@pytest.fixture(scope='module')
def setup(tmp_path_factory, isolated_storage):
    with TestClient(app) as client:
        with get_db() as db:
            a = db.query(TeamAgent).filter_by(slug='default').one()
            b = TeamAgent(name='Knowledge test B', slug='knowledge-test-b')
            db.add(b)
            db.flush()
            team_a, team_b = a.id, b.id
            for name, team, role in [('knowledge_owner', team_a, 'admin'), ('knowledge_other', team_b, 'admin'), ('knowledge_viewer', team_a, 'viewer')]:
                user = Admin(username=name, password_hash='unused-test-hash', is_super_admin=False)
                db.add(user)
                db.flush()
                db.add(TeamUserMembership(admin_id=user.id, team_agent_id=team, role=role))
        archive = tmp_path_factory.mktemp('archive') / 'knowledge.zip'
        with zipfile.ZipFile(archive, 'w') as z:
            z.writestr('policy.md', '---\ntype: knowledge\ntitle: นโยบายทดสอบ\nresource: policy.md\n---\nรหัสลับทีม ALPHA-7391 นโยบายคืนเงินเดิมคือ 15 วัน')
            z.writestr('hours.md', '---\ntype: knowledge\ntitle: เวลาบริการ\nresource: hours.md\n---\nสำนักงานเปิดวันจันทร์ถึงศุกร์ เวลา 9 ถึง 17 นาฬิกา')
        bundle = OKFService().import_archive(archive, 'Security acceptance', team_a, 'team', 'knowledge_owner')
        bundle_id = bundle['id']
        tool_id = database.create_custom_tool('security_acceptance_search', {'type':'okf_knowledge_graph','okf_bundle_id':bundle_id,'team_agent_id':team_a}, team_agent_id=team_a)
        agent_id = database.create_agent('Knowledge acceptance agent','Use local knowledge','gpt-4o-mini',[tool_id],[],team_agent_id=team_a)
        database.set_team_agent_members(team_b, [agent_id], agent_id)
        local_rag.index_bundle(bundle_id)
        yield client, team_a, team_b, bundle_id


def test_owner_and_viewer_read_but_other_team_cannot(setup):
    client,a,b,bundle = setup
    path = f'/api/admin/okf-bundles/{bundle}/test'
    for user in ['knowledge_owner','knowledge_viewer']:
        response = client.post(path,params={'team_agent_id':a},headers=auth(user),json={'query':'รหัสลับ'})
        assert response.status_code == 200
        assert 'ALPHA-7391' in response.text
        response = client.post(path,headers=auth(user),json={'query':'รหัสลับ'})
        assert response.status_code == 200
        assert 'ALPHA-7391' in response.text
    response = client.post(path,params={'team_agent_id':a},headers=auth('knowledge_other'),json={'query':'รหัสลับ'})
    assert response.status_code == 403
    response = client.post(path,params={'team_agent_id':b},headers=auth('knowledge_other'),json={'query':'รหัสลับ'})
    assert 'ALPHA-7391' not in response.text


def test_omitting_team_does_not_grant_default_team_access(setup):
    client,a,b,bundle = setup
    response = client.post(f'/api/admin/okf-bundles/{bundle}/test',headers=auth('knowledge_other'),json={'query':'รหัสลับ'})
    assert 'ALPHA-7391' not in response.text
    assert response.status_code in (403,404)


def invoke(team):
    agent = get_runtime_starting_agent(team)
    member = next((member for member in agent.handoffs if member.name == 'Knowledge acceptance agent'),None)
    if member is None:
        return 'Knowledge capability unavailable'
    tool = next((tool for tool in member.tools if tool.name == 'security_acceptance_search'),None)
    if tool is None:
        return 'Knowledge capability unavailable'
    return asyncio.run(tool.on_invoke_tool(RunContextWrapper(context=None), json.dumps({'query':'รหัสลับ'})))


def test_agent_in_foreign_team_cannot_use_owners_private_knowledge(setup):
    client,a,b,bundle = setup
    assert 'ALPHA-7391' in invoke(a)
    assert 'ALPHA-7391' not in invoke(b)


def test_viewer_cannot_edit_or_reindex(setup):
    client,a,b,bundle = setup
    response = client.patch(f'/api/admin/okf-bundles/{bundle}/concepts/policy',params={'team_agent_id':a},headers=auth('knowledge_viewer'),json={'body':'unauthorized'})
    assert response.status_code == 403
    response = client.post(f'/api/admin/okf-bundles/{bundle}/reindex-vectors',params={'team_agent_id':a},headers=auth('knowledge_viewer'))
    assert response.status_code == 403


def test_intentionally_shared_knowledge_is_available_to_recipient_agent(setup):
    client,a,b,bundle = setup
    with get_db() as db:
        tool = db.query(Tool).filter_by(name='security_acceptance_search').one()
        tool_id = tool.id
        db.add(TeamToolAssignment(team_agent_id=b,tool_id=tool_id,relationship='shared_in'))
    try:
        assert 'ALPHA-7391' in invoke(b)
        response = client.post(f'/api/admin/okf-bundles/{bundle}/test',params={'team_agent_id':b},headers=auth('knowledge_other'),json={'query':'รหัสลับ'})
        assert 'ALPHA-7391' in response.text
        response = client.patch(f'/api/admin/okf-bundles/{bundle}/concepts/policy',params={'team_agent_id':b},headers=auth('knowledge_other'),json={'body':'unauthorized shared edit'})
        assert response.status_code == 403
    finally:
        with get_db() as db:
            db.query(TeamToolAssignment).filter_by(team_agent_id=b,tool_id=tool_id).delete()


class KnowledgeCallModel(Model):
    async def get_response(self, system_instructions, input, model_settings, tools, output_schema, handoffs, tracing):
        outputs = [item for item in input if isinstance(item,dict) and item.get('type') == 'function_call_output'] if isinstance(input,list) else []
        if outputs:
            items = [ResponseOutputMessage(id='msg_acceptance',role='assistant',status='completed',type='message',content=[ResponseOutputText(type='output_text',text=str(outputs[-1]['output']),annotations=[])])]
        else:
            items = [ResponseFunctionToolCall(id='fc_acceptance',call_id='call_acceptance',name='security_acceptance_search',arguments=json.dumps({'query':'รหัสลับ'}),type='function_call')]
        return ModelResponse(output=items,usage=Usage(),referenceable_id=None)

    async def stream_response(self,*args,**kwargs):
        raise NotImplementedError
        yield


def test_sdk_runner_uses_team_bound_knowledge_tool(setup):
    client,a,b,bundle = setup
    for team,allowed in [(a,True),(b,False)]:
        coordinator = get_runtime_starting_agent(team)
        member = next(member for member in coordinator.handoffs if member.name == 'Knowledge acceptance agent')
        member.model = KnowledgeCallModel()
        result = asyncio.run(Runner.run(member,'รหัสลับ',run_config=RunConfig(tracing_disabled=True)))
        assert ('ALPHA-7391' in result.final_output) == allowed


def test_edit_updates_answers_and_stale_vectors_are_excluded(setup, monkeypatch):
    client,a,b,bundle = setup
    path = f'/api/admin/okf-bundles/{bundle}'
    with monkeypatch.context() as patch:
        patch.setenv('EMBEDDING_BASE_URL','http://127.0.0.1:1/v1')
        patch.setattr(local_rag.time,'sleep',lambda _:None)
        response = client.patch(path+'/concepts/policy',params={'team_agent_id':a},headers=auth('knowledge_owner'),json={'body':'รหัสลับทีม ALPHA-7391 นโยบายคืนเงินใหม่คือ 45 วัน'})
        assert response.status_code == 503
        with engine.connect() as conn:
            assert conn.execute(text('SELECT count(*) FROM okf_rag_chunks WHERE bundle_id=:b'),{'b':bundle}).scalar() > 0
        response = client.post(path+'/test',params={'team_agent_id':a},headers=auth('knowledge_viewer'),json={'query':'นโยบายคืนเงิน'})
        assert response.status_code == 200
        assert '45 วัน' in response.text
        assert '15 วัน' not in response.text
    response = client.post(path+'/test',params={'team_agent_id':a},headers=auth('knowledge_viewer'),json={'query':'นโยบายคืนเงิน'})
    assert '45 วัน' in response.text and '15 วัน' not in response.text
    assert 'hybrid vector/keyword' not in response.text
    response = client.post(path+'/reindex-vectors',params={'team_agent_id':a},headers=auth('knowledge_owner'))
    assert response.status_code == 200
    assert local_rag.indexed_count(bundle) > 0
    response = client.post(path+'/test',params={'team_agent_id':a},headers=auth('knowledge_viewer'),json={'query':'นโยบายคืนเงิน'})
    assert '45 วัน' in response.text and '15 วัน' not in response.text
    assert 'hybrid vector/keyword' in response.text


def test_successful_edit_automatically_reindexes(setup):
    client,a,b,bundle = setup
    path = f'/api/admin/okf-bundles/{bundle}'
    response = client.patch(path+'/concepts/policy',params={'team_agent_id':a},headers=auth('knowledge_owner'),json={'body':'รหัสลับทีม ALPHA-7391 นโยบายคืนเงินใหม่คือ 60 วัน'})
    assert response.status_code == 200
    response = client.post(path+'/test',params={'team_agent_id':a},headers=auth('knowledge_viewer'),json={'query':'นโยบายคืนเงิน'})
    assert '60 วัน' in response.text and '45 วัน' not in response.text
    assert 'hybrid vector/keyword' in response.text


def test_embedding_connection_failure_falls_back_to_keyword(setup, monkeypatch):
    client,a,b,bundle = setup
    monkeypatch.setenv('EMBEDDING_BASE_URL','http://127.0.0.1:1/v1')
    monkeypatch.setattr(local_rag.time,'sleep',lambda _:None)
    response = client.post(f'/api/admin/okf-bundles/{bundle}/test',params={'team_agent_id':a},headers=auth('knowledge_owner'),json={'query':'นโยบายคืนเงิน'})
    assert response.status_code == 200
    assert '60 วัน' in response.text
    assert 'hybrid vector/keyword' not in response.text


@pytest.mark.parametrize('failure',['timeout','server_error','malformed_vector'])
def test_embedding_failures_preserve_keyword_search(setup,monkeypatch,failure):
    import httpx
    client,a,b,bundle = setup
    def fail(url,**kwargs):
        if failure == 'timeout':
            raise httpx.ReadTimeout('simulated embedding timeout')
        request = httpx.Request('POST',url)
        if failure == 'server_error':
            return httpx.Response(503,request=request,json={'error':'simulated overload'})
        return httpx.Response(200,request=request,json={'data':[{'index':0,'embedding':[0.1]*3}]})
    monkeypatch.setattr(local_rag.httpx,'post',fail)
    monkeypatch.setattr(local_rag.time,'sleep',lambda _:None)
    response = client.post(f'/api/admin/okf-bundles/{bundle}/test',params={'team_agent_id':a},headers=auth('knowledge_owner'),json={'query':'นโยบายคืนเงิน'})
    assert response.status_code == 200
    assert '60 วัน' in response.text
    assert 'hybrid vector/keyword' not in response.text


def test_edit_during_indexing_cannot_replace_vectors_with_old_content(setup,monkeypatch):
    client,a,b,bundle = setup
    original = local_rag.LocalEmbeddingClient.documents
    def edit_while_embedding(self,texts):
        vectors = original(self,texts)
        OKFService().update_concept(bundle,'policy',a,None,None,None,'รหัสลับทีม ALPHA-7391 นโยบายคืนเงินใหม่คือ 90 วัน')
        return vectors
    with monkeypatch.context() as patch:
        patch.setattr(local_rag.LocalEmbeddingClient,'documents',edit_while_embedding)
        response = client.post(f'/api/admin/okf-bundles/{bundle}/reindex-vectors',params={'team_agent_id':a},headers=auth('knowledge_owner'))
        assert response.status_code == 503
    response = client.post(f'/api/admin/okf-bundles/{bundle}/test',params={'team_agent_id':a},headers=auth('knowledge_owner'),json={'query':'นโยบายคืนเงิน'})
    assert '90 วัน' in response.text and '60 วัน' not in response.text
    response = client.post(f'/api/admin/okf-bundles/{bundle}/reindex-vectors',params={'team_agent_id':a},headers=auth('knowledge_owner'))
    assert response.status_code == 200


def test_edit_while_query_embedding_runs_returns_latest_keyword_evidence(setup,monkeypatch):
    client,a,b,bundle = setup
    original = local_rag.LocalEmbeddingClient.query
    def embed_then_edit(self,query):
        vector = original(self,query)
        OKFService().update_concept(bundle,'policy',a,None,None,None,'รหัสลับทีม ALPHA-7391 นโยบายคืนเงินใหม่คือ 120 วัน')
        return vector
    with monkeypatch.context() as patch:
        patch.setattr(local_rag.LocalEmbeddingClient,'query',embed_then_edit)
        response = client.post(f'/api/admin/okf-bundles/{bundle}/test',params={'team_agent_id':a},headers=auth('knowledge_owner'),json={'query':'นโยบายคืนเงิน'})
        assert response.status_code == 200
        assert '120 วัน' in response.text and '90 วัน' not in response.text
        assert 'hybrid vector/keyword' not in response.text
    response = client.post(f'/api/admin/okf-bundles/{bundle}/reindex-vectors',params={'team_agent_id':a},headers=auth('knowledge_owner'))
    assert response.status_code == 200
