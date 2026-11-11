"""Capabilities API regressions on disposable PostgreSQL with duplicate rows."""
import json
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from test_builtin_duplicates import pg, seed
from app.orm_models import Admin, Agent, AgentTool, TeamAgentMember, TeamToolAssignment, TeamUserMembership, Tool
from app.auth import create_access_token
with patch('app.db_config.init_database'):
    from app import admin_routes

IDS = (41, 144, 42, 145)  # Deliberately unrelated to the Production evidence.


def headers(user='owner'):
    return {'Authorization': 'Bearer '+create_access_token({'sub':user})}


@pytest.fixture
def catalog(pg):
    seed(pg, IDS)
    _, get_db, database, workflow = pg
    with get_db() as db:
        db.add_all([Admin(id=1,username='owner',password_hash='unused'),Admin(id=2,username='outside',password_hash='unused'),Admin(id=3,username='viewer',password_hash='unused')]);db.flush()
        db.add_all([TeamUserMembership(admin_id=1,team_agent_id=11,role='admin'),TeamUserMembership(admin_id=1,team_agent_id=12,role='admin'),TeamUserMembership(admin_id=2,team_agent_id=13,role='admin'),TeamUserMembership(admin_id=3,team_agent_id=11,role='viewer')])
    app=FastAPI();app.include_router(admin_routes.router)
    with TestClient(app) as client: yield client, get_db, database, workflow


def listing(client, team=11, user='owner'):
    result=client.get(f'/api/admin/tools?team_agent_id={team}',headers=headers(user))
    assert result.status_code==200,result.text
    return result.json()


def edit_request(snapshot, agent_id, ids):
    agent=next(agent for agent in snapshot['agents'] if agent['id']==agent_id)
    return {'name':agent['name'],'instructions':agent['instructions'],'model':agent['model'],'llm_provider_id':None,
            'tool_ids':ids,'handoff_agent_ids':agent['handoff_agent_ids'],'is_fallback':snapshot['fallback_agent_id']==agent_id,
            'expected_updated_at':agent['updated_at'],'expected_fallback_agent_id':snapshot['fallback_agent_id']}


def test_equivalent_builtins_list_once_and_count_distinct_team_members(catalog):
    client,get_db,_,workflow=catalog
    with get_db() as db:
        # Another team's binding must not increase this team's count.
        db.add(Agent(id=99,name='Outside',instructions='test',model='test'));db.flush()
        db.add(TeamAgentMember(team_agent_id=13,agent_id=99));db.add(AgentTool(agent_id=99,tool_id=IDS[0]))
    for _ in range(3):
        rows=listing(client)
        assert [(r['id'],r['name']) for r in rows]==[(IDS[0],'DateTimeTool'),(IDS[2],'WebSearchTool')]
        assert rows[0]['alias_ids']==list(IDS[:2]) and rows[1]['alias_ids']==list(IDS[2:])
        assert [r['agent_usage_count'] for r in rows]==[2,1]
        assert all(r['agent_usage_scope']=='team' and r['agent_usage_team_agent_id']==11 for r in rows)
    snap=workflow.get_snapshot(11)
    assert [(r['id'],r['alias_ids']) for r in rows]==[(r['id'],r['alias_ids']) for r in snap['tools']]
    detail=client.get(f'/api/admin/tools/{IDS[1]}?team_agent_id=11',headers=headers()).json()
    assert detail['id']==IDS[0] and detail['agent_usage_count']==2
    with get_db() as db:assert db.query(Tool).count()==4  # Read projection never repairs data.


def test_production_shaped_overlap_counts_102_and_26_not_row_sums(catalog):
    client,get_db,_,_=catalog
    with get_db() as db:
        db.query(AgentTool).delete()
        for index in range(102):
            ident=1000+index
            db.add(Agent(id=ident,name=f'Fixture {index}',instructions='test',model='test'));db.flush()
            db.add(TeamAgentMember(team_agent_id=11,agent_id=ident))
            db.add(AgentTool(agent_id=ident,tool_id=IDS[0]))
            if index<10:db.add(AgentTool(agent_id=ident,tool_id=IDS[1]))
            if index<24:db.add(AgentTool(agent_id=ident,tool_id=IDS[2]))
            if 24<=index<26:db.add(AgentTool(agent_id=ident,tool_id=IDS[3]))
    rows=listing(client)
    assert [r['agent_usage_count'] for r in rows]==[102,26]


def test_only_accessible_aliases_participate_and_hidden_ids_cannot_be_normalized(catalog):
    client,get_db,_,workflow=catalog
    with get_db() as db:
        db.query(TeamToolAssignment).filter_by(team_agent_id=12).delete()
        db.add(TeamToolAssignment(team_agent_id=12,tool_id=IDS[1],relationship='shared_in'))
        db.add(AgentTool(agent_id=22,tool_id=IDS[0]))
        db.add(Agent(id=23,name='Editable here',instructions='test',model='test'));db.flush()
        db.add(TeamAgentMember(team_agent_id=12,agent_id=23))
    rows=listing(client,12)
    assert len(rows)==1 and rows[0]['id']==IDS[1] and rows[0]['alias_ids']==[IDS[1]]
    assert rows[0]['agent_usage_count']==1
    assert client.get(f'/api/admin/tools/{IDS[0]}?team_agent_id=12',headers=headers()).status_code==404
    snap=workflow.get_snapshot(12)
    assert next(a for a in snap['agents'] if a['id']==22)['tool_ids']==[IDS[1]]
    request=edit_request(snap,23,[IDS[0]])
    denied=client.put('/api/admin/team-agents/12/workflow/agents/23',headers=headers(),json=request)
    assert denied.status_code==400 and 'not available' in denied.json()['detail']
    request['tool_ids']=[IDS[1]]
    assert client.put('/api/admin/team-agents/12/workflow/agents/23',headers=headers(),json=request).status_code==200
    assert next(a for a in workflow.get_snapshot(12)['agents'] if a['id']==23)['tool_ids']==[IDS[1]]


def test_alias_save_round_trip_and_shared_or_viewer_agents_are_readonly(catalog):
    client,get_db,_,workflow=catalog
    snap=workflow.get_snapshot(11)
    request=edit_request(snap,21,[IDS[1],IDS[3]])
    response=client.put('/api/admin/team-agents/11/workflow/agents/21',headers=headers(),json=request)
    assert response.status_code==200,response.text
    with get_db() as db:
        assert sorted(row.tool_id for row in db.query(AgentTool).filter_by(agent_id=21))==[IDS[0],IDS[2]]
        before=[(row.agent_id,row.tool_id) for row in db.query(AgentTool).order_by(AgentTool.agent_id,AgentTool.tool_id)]
    snap=workflow.get_snapshot(11)
    assert next(a for a in snap['agents'] if a['id']==21)['tool_ids']==[IDS[0],IDS[2]]
    for ident,user,expected in [(22,'owner',409),(21,'viewer',403)]:
        response=client.put(f'/api/admin/team-agents/11/workflow/agents/{ident}',headers=headers(user),json=edit_request(snap,ident,[IDS[1]]))
        assert response.status_code==expected,response.text
    assert client.delete(f'/api/admin/tools/{IDS[0]}?team_agent_id=11',headers=headers()).status_code==404
    with get_db() as db:
        assert before==[(row.agent_id,row.tool_id) for row in db.query(AgentTool).order_by(AgentTool.agent_id,AgentTool.tool_id)]


@pytest.mark.parametrize('field,value',[('config',{'location':{'country':'TH'}}),('owner_team_agent_id',12),('visibility','global')])
def test_visible_conflicts_are_explicit_and_do_not_mutate(catalog,field,value):
    client,get_db,_,workflow=catalog
    request=edit_request(workflow.get_snapshot(11),21,[IDS[1]])
    with get_db() as db:
        setattr(db.get(Tool,IDS[1]),field,value)
        if field=='owner_team_agent_id':
            db.get(TeamToolAssignment,(11,IDS[1])).relationship='shared_in'
    for route in ('/api/admin/tools?team_agent_id=11','/api/admin/team-agents/11/workflow',f'/api/admin/tools/{IDS[0]}?team_agent_id=11'):
        response=client.get(route,headers=headers())
        assert response.status_code==409 and f'Conflicting builtin {field}' in response.json()['detail']
    response=client.put('/api/admin/team-agents/11/workflow/agents/21',headers=headers(),json=request)
    assert response.status_code==400 and f'Conflicting builtin {field}' in response.json()['detail']
    with get_db() as db:assert db.query(Tool).count()==4


def test_hidden_conflicts_do_not_leak_into_catalog(catalog):
    client,get_db,_,_=catalog
    with get_db() as db:
        db.add(Tool(id=900,name='DateTimeTool',type='builtin',config={'private':'different'},owner_team_agent_id=13,visibility='team'))
    assert len(listing(client))==2
    assert listing(client,13,'outside')[0]['alias_ids']==[900]


def test_non_builtin_and_unknown_identities_with_same_names_stay_distinct(catalog):
    client,get_db,_,_=catalog
    with get_db() as db:
        for index,kind in enumerate(('custom_api','mcp_streamable_http','okf_knowledge_graph')):
            db.add(Tool(id=300+index,name='Same catalog name',type=kind,config={},owner_team_agent_id=11,visibility='team'))
        for ident in (400,401):db.add(Tool(id=ident,name='UnknownBuiltin',type='builtin',config={},owner_team_agent_id=11,visibility='team'))
    rows=listing(client)
    assert {r['id'] for r in rows if r['name']=='Same catalog name'}=={300,301,302}
    assert {r['id'] for r in rows if r['name']=='UnknownBuiltin'}=={400,401}
    assert not any('alias_ids' in r for r in rows if r['id']>=300)


def test_api_authorizes_explicit_and_default_team_before_listing(catalog):
    client,_,_,_=catalog
    for route in ('/api/admin/tools?team_agent_id=11','/api/admin/tools',f'/api/admin/tools/{IDS[1]}?team_agent_id=11',f'/api/admin/tools/{IDS[1]}'):
        assert client.get(route,headers=headers('outside')).status_code==403
        assert client.get(route).status_code in (401,403)
    response=client.get('/api/admin/tools',headers=headers())
    assert response.status_code==200 and response.headers['Deprecation']=='true'


def test_canonical_is_lowest_available_id_with_equivalent_json_or_default_config():
    from app.builtin_tools import aliases
    rows=[Tool(id=87,name='DateTimeTool',type='builtin',config=None,visibility='global'),
          Tool(id=43,name='DateTimeTool',type='builtin',config={},visibility='global')]
    assert aliases(rows)=={43:43,87:43}
    rows=[Tool(id=87,name='WebSearchTool',type='builtin',config={'a':1,'b':2},visibility='global'),
          Tool(id=43,name='WebSearchTool',type='builtin',config={'b':2,'a':1},visibility='global')]
    assert aliases(rows)=={43:43,87:43}


def test_render_fixture_matches_real_api_projection(catalog):
    from pathlib import Path
    fixture = json.loads((Path(__file__).resolve().parents[2] / 'frontend/tests/fixtures/builtin-capabilities.json').read_text())
    client, _, _, _ = catalog
    rows = listing(client, fixture['team_id'])
    assert len(rows) == len(fixture['expected_tools'])
    for actual, expected in zip(rows, fixture['expected_tools']):
        assert {key: actual[key] for key in expected} == expected
