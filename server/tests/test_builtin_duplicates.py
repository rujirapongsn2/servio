"""Disposable PostgreSQL only. Never use the application DATABASE_URL for this suite."""
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app import agent_config, db_config
from app.builtin_tools import aliases, ensure_builtin_tools, runtime_tools
from app.orm_models import Base, Tool, Agent, AgentTool, TeamAgent, TeamAgentMember, TeamToolAssignment, WorkflowCreationReceipt
from app.models import UpdateWorkflowAgentRequest
from migrations import builtin_duplicates as migration


@pytest.fixture
def pg(monkeypatch):
    raw = os.environ.get('SERVIO_TEST_POSTGRES_DSN')
    if not raw:
        pytest.skip('Set SERVIO_TEST_POSTGRES_DSN to the disposable PostgreSQL sandbox')
    url = make_url(raw)
    if url.host != '127.0.0.1' or url.port != 15439 or url.database != 'servio_builtin_test':
        pytest.fail('Only the dedicated localhost:15439/servio_builtin_test sandbox is accepted')
    admin = create_engine(url, isolation_level='AUTOCOMMIT')
    name = 'builtin_case_' + uuid4().hex
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE {name}'))
    engine = create_engine(url.set(database=name))
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    @contextmanager
    def get_db():
        with sessions.begin() as db:
            yield db
    with patch('app.db_config.init_database'):
        from app import database, team_workflow
    monkeypatch.setattr(database, 'get_db', get_db)
    monkeypatch.setattr(db_config, 'engine', engine)
    monkeypatch.setattr(db_config, 'SessionLocal', sessions)
    try:
        yield engine, get_db, database, team_workflow
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE {name} WITH (FORCE)'))
        admin.dispose()


def seed(pg, ids=(1, 266, 2, 267)):
    engine, get_db, *_ = pg
    with engine.begin() as conn:
        conn.execute(text('ALTER TABLE tools DROP CONSTRAINT tools_name_key'))
        # A healthy nonunique index with duplicate data must not be reported as corruption.
        conn.execute(text('CREATE INDEX tools_name_key ON tools(name)'))
    with get_db() as db:
        db.add_all([TeamAgent(id=11,name='Owner',slug='default'),TeamAgent(id=12,name='Shared',slug='shared'),TeamAgent(id=13,name='Outside',slug='outside')])
        db.add_all([Agent(id=21,name='Agent',instructions='Test',model='test'),Agent(id=22,name='Shared agent',instructions='Test',model='test')]);db.flush()
        for ident, name in zip(ids, ['DateTimeTool','DateTimeTool','WebSearchTool','WebSearchTool']):
            db.add(Tool(id=ident,name=name,type='builtin',config={'description':name},owner_team_agent_id=11,visibility='team'))
        db.flush()
        db.add_all([TeamAgentMember(team_agent_id=11,agent_id=21,role='starting'),TeamAgentMember(team_agent_id=11,agent_id=22),TeamAgentMember(team_agent_id=12,agent_id=22,role='starting')])
        db.add_all([AgentTool(agent_id=21,tool_id=ident) for ident in ids])
        db.add_all([AgentTool(agent_id=22,tool_id=ids[1])])
        for ident in ids:
            db.add(TeamToolAssignment(team_agent_id=11,tool_id=ident,relationship='owned'))
            db.add(TeamToolAssignment(team_agent_id=12,tool_id=ident,relationship='shared_in'))
        db.add(WorkflowCreationReceipt(team_agent_id=11,request_id=str(uuid4()),payload_hash='a'*64,resource_kind='tool',resource_id=ids[1]))
        db.flush()
        db.execute(text("SELECT setval(pg_get_serial_sequence('tools','id'), (SELECT max(id) FROM tools), true)"))


@pytest.mark.parametrize('ids',[(1,266,2,267),(41,144,42,145)])
def test_repair_remaps_relations_grants_receipts_and_is_repeatable(pg,tmp_path,ids):
    seed(pg,ids);engine,get_db,database,_=pg
    with engine.begin() as conn:
        before=migration.snapshot(conn,'public');plan=migration.audit(conn)
        assert plan['blockers']==[]
        assert plan['mapping']=={str(ids[1]):ids[0],str(ids[3]):ids[2]}
        assert all(scan['equal'] for scan in plan['diagnostics']['name_scans'].values())
        assert not plan['diagnostics']['name_uniqueness_enforced']
    backup=tmp_path/'backup.json'
    with engine.begin() as conn:assert migration.apply(conn,plan,backup)=='applied'
    assert backup.stat().st_mode & 0o777 == 0o600
    with engine.begin() as conn:
        after=migration.snapshot(conn,'public')
        assert len(after['tools'])==2 and len(after['agent_tools'])==3
        assert len(after['team_tool_assignments'])==4
        assert after['workflow_creation_receipts'][0]['resource_id']==ids[0]
        assert migration.apply(conn,plan,tmp_path/'unused.json')=='already_applied'
        assert migration.audit(conn)['mapping']=={}
    with get_db() as db:
        assert database._tool_available_to_team(db,ids[0],11)
        assert database._tool_available_to_team(db,ids[0],12)
        assert not database._tool_available_to_team(db,ids[0],13)
    with engine.begin() as conn:assert migration.rollback(conn,json.loads(backup.read_text()))=='restored'
    with engine.begin() as conn:
        assert migration.snapshot(conn,'public')==before
        assert migration.rollback(conn,json.loads(backup.read_text()))=='already_restored'


def test_workflow_normalizes_available_ids_and_keeps_shared_agents_readonly(pg):
    seed(pg);_,get_db,_,workflow=pg
    snap=workflow.get_snapshot(11)
    assert [tool['id'] for tool in snap['tools']]==[1,2]
    agent=next(row for row in snap['agents'] if row['id']==21)
    assert agent['tool_ids']==[1,2]
    request=UpdateWorkflowAgentRequest(name=agent['name'],instructions=agent['instructions'],model=agent['model'],
        tool_ids=[266,267],handoff_agent_ids=[],is_fallback=True,expected_updated_at=agent['updated_at'],expected_fallback_agent_id=21)
    workflow.update_workflow_agent(11,21,request)
    with get_db() as db:assert sorted(row.tool_id for row in db.query(AgentTool).filter_by(agent_id=21))==[1,2]
    assert [row['id'] for row in workflow.get_snapshot(12)['tools']]==[1,2]
    assert workflow.get_snapshot(13)['tools']==[]
    with pytest.raises(workflow.WorkflowConflict,match='Shared agents'):
        workflow.update_workflow_agent(11,22,request)
    with get_db() as db:
        with pytest.raises(ValueError,match='not available'):
            workflow._validate_agent(db,13,request,{21})


def test_runtime_builds_each_builtin_once_with_deterministic_config():
    raw={'name':'Test','model':'test','instructions':'Test','tools':[
        {'id':266,'name':'DateTimeTool','type':'builtin','config':'{"description":"duplicate"}'},
        {'id':1,'name':'DateTimeTool','type':'builtin','config':'{"description":"canonical"}'},
        {'id':267,'name':'WebSearchTool','type':'builtin','config':'{}'},
        {'id':2,'name':'WebSearchTool','type':'builtin','config':'{}'}]}
    agent=agent_config.build_agent_from_db(raw,runtime_team_agent_id=11)
    from agents import WebSearchTool
    assert len(agent.tools)==2
    assert sum(isinstance(tool,WebSearchTool) for tool in agent.tools)==1
    assert agent.tools[0].name=='DateTimeTool'
    assert agent.tools[0].description=='canonical'
    assert len(list(runtime_tools(raw['tools'])))==2


@pytest.mark.parametrize('field,value',[('config',{'location':{'country':'TH'}}),('owner_team_agent_id',12),('visibility','global')])
def test_conflicts_abort_without_deleting_or_expanding_scope(pg,tmp_path,field,value):
    seed(pg);engine,get_db,*_=pg
    with get_db() as db:setattr(db.get(Tool,266),field,value)
    with engine.begin() as conn:
        before=migration.snapshot(conn,'public');plan=migration.audit(conn)
        assert any(field in error for error in plan['blockers'])
    with pytest.raises(ValueError,match='Unsafe migration plan'):
        with engine.begin() as conn:migration.apply(conn,plan,tmp_path/'backup.json')
    with engine.begin() as conn:assert migration.snapshot(conn,'public')==before


@pytest.mark.parametrize('kind',['foreign_key','json','polymorphic'])
def test_unknown_schema_and_data_references_block_deletion(pg,tmp_path,kind):
    seed(pg);engine,*_=pg
    with engine.begin() as conn:
        if kind=='foreign_key':
            conn.execute(text('CREATE SCHEMA extra'))
            conn.execute(text('CREATE TABLE extra.other_bindings(tool_id integer REFERENCES tools(id))'))
            conn.execute(text('INSERT INTO extra.other_bindings VALUES (266)'))
        elif kind=='json':
            conn.execute(text('CREATE TABLE drafts(payload text)'))
            conn.execute(text('INSERT INTO drafts VALUES (:payload)'),{'payload':json.dumps({'tool_ids':[266]})})
        else:
            conn.execute(text('CREATE TABLE references_without_fk(resource_kind text,resource_id int)'))
            conn.execute(text("INSERT INTO references_without_fk VALUES ('tool',266)"))
        plan=migration.audit(conn)
        assert plan['blockers']
    with pytest.raises(ValueError,match='Unsafe migration plan'):
        with engine.begin() as conn:migration.apply(conn,plan,tmp_path/'backup.json')


def test_failed_transaction_stale_plan_and_changed_rollback_are_safe(pg,tmp_path,monkeypatch):
    seed(pg);engine,*_=pg
    with engine.begin() as conn:
        before=migration.snapshot(conn,'public');plan=migration.audit(conn)
    original=migration.insert_records
    def fail(*args,**kwargs):raise RuntimeError('simulated failure after DELETE')
    monkeypatch.setattr(migration,'insert_records',fail)
    with pytest.raises(RuntimeError):
        with engine.begin() as conn:migration.apply(conn,plan,tmp_path/'failed.json')
    with engine.begin() as conn:assert migration.snapshot(conn,'public')==before
    monkeypatch.setattr(migration,'insert_records',original)
    with engine.begin() as conn:migration.apply(conn,plan,tmp_path/'success.json')
    with engine.begin() as conn:
        conn.execute(text("UPDATE tools SET config='{}' WHERE id=1"))
    with pytest.raises(ValueError,match='changed after migration'):
        with engine.begin() as conn:migration.rollback(conn,json.loads((tmp_path/'success.json').read_text()))
    with pytest.raises(ValueError,match='Plan is stale'):
        with engine.begin() as conn:migration.apply(conn,plan,tmp_path/'stale.json')


@pytest.mark.parametrize('duplicates',[False,True])
def test_concurrent_initialization_across_processes(pg,duplicates):
    if duplicates:seed(pg)
    engine,_,_,_=pg
    url=engine.url.render_as_string(hide_password=False)
    env={**os.environ,'DATABASE_URL':url,'PYTHONPATH':str(Path(__file__).resolve().parents[1])}
    def run(_):
        return subprocess.run([sys.executable,'-c','from app.db_config import init_database; init_database()'],env=env,capture_output=True,text=True,timeout=60)
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(run,range(3)))
    assert all(item.returncode==0 for item in results),[item.stderr[-1500:] for item in results]
    with engine.begin() as conn:
        assert conn.execute(text("SELECT name,count(*) FROM tools WHERE type='builtin' GROUP BY name ORDER BY name")).all()==[('DateTimeTool',2 if duplicates else 1),('WebSearchTool',2 if duplicates else 1)]
        if duplicates:
            assert conn.execute(text("SELECT count(*) FROM tools WHERE type='builtin' AND visibility='team' AND owner_team_agent_id=11")).scalar()==4


def test_repeated_seeding_does_not_change_private_builtin_grants(pg):
    seed(pg);_,get_db,*_=pg
    with get_db() as db:
        before=[(row.id,row.owner_team_agent_id,row.visibility) for row in db.query(Tool).order_by(Tool.id)]
        ensure_builtin_tools(db,11,None)
        ensure_builtin_tools(db,11,None)
    with get_db() as db:assert before==[(row.id,row.owner_team_agent_id,row.visibility) for row in db.query(Tool).order_by(Tool.id)]


def test_postgresql_index_and_collation_diagnostics_on_synthetic_copy(pg):
    seed(pg);engine,*_=pg
    with engine.begin() as conn:
        conn.execute(text('CREATE EXTENSION amcheck'))
        report=migration.audit(conn)['diagnostics']
        assert report['amcheck_available']
        assert all(check['status']=='passed' for check in report['amcheck'])
        assert all(scan['equal'] for scan in report['name_scans'].values())
        assert report['database']['datcollate']
        assert report['column_collations']
        assert report['name_uniqueness_enforced'] is False


def test_legacy_assignment_normalizes_builtin_ids_without_changing_team_grants(pg):
    seed(pg);_,get_db,database,_=pg
    with get_db() as db:before=[(row.team_agent_id,row.tool_id,row.relationship) for row in db.query(TeamToolAssignment)]
    assert database.assign_tool_to_agent(21,266,team_agent_id=11)
    with get_db() as db:
        assert sorted(row.tool_id for row in db.query(AgentTool).filter_by(agent_id=21))==[1,2]
        assert before==[(row.team_agent_id,row.tool_id,row.relationship) for row in db.query(TeamToolAssignment)]
    assert not database.assign_tool_to_agent(22,266,team_agent_id=11)


def test_index_restoration_only_after_data_cleanup_and_rollback_fails_safely(pg,tmp_path):
    from sqlalchemy.exc import IntegrityError
    seed(pg);engine,*_=pg
    with engine.begin() as conn:plan=migration.audit(conn)
    with engine.begin() as conn:migration.apply(conn,plan,tmp_path/'backup.json')
    with engine.begin() as conn:
        conn.execute(text('DROP INDEX tools_name_key'))
        conn.execute(text('ALTER TABLE tools ADD CONSTRAINT tools_name_key UNIQUE(name)'))
        after=migration.snapshot(conn,'public')
        assert migration.audit(conn)['diagnostics']['name_uniqueness_enforced']
    with pytest.raises(IntegrityError):
        with engine.begin() as conn:migration.rollback(conn,json.loads((tmp_path/'backup.json').read_text()))
    with engine.begin() as conn:assert migration.snapshot(conn,'public')==after


def test_partial_unique_index_does_not_prove_name_integrity(pg,tmp_path):
    seed(pg);engine,*_=pg
    with engine.begin() as conn:
        before=migration.snapshot(conn,'public');plan=migration.audit(conn)
    with engine.begin() as conn:migration.apply(conn,plan,tmp_path/'backup.json')
    with engine.begin() as conn:
        conn.execute(text('DROP INDEX tools_name_key'))
        conn.execute(text('CREATE UNIQUE INDEX tools_name_key ON tools(name) WHERE id<200'))
        migration.insert_records(conn,'public','tools',[row for row in before['tools'] if row['id'] in (266,267)])
        result=migration.audit(conn)['diagnostics']
        assert result['name_uniqueness_enforced'] is False
        assert next(row for row in result['indexes'] if row['name']=='tools_name_key')['predicate']
        assert result['name_scans']['DateTimeTool']['sequential_ids']==[1,266]


def test_collation_equal_byte_distinct_names_require_review(pg):
    engine,*_=pg
    with engine.begin() as conn:
        conn.execute(text("CREATE COLLATION insensitive (provider=icu,locale='und-u-ks-level2',deterministic=false)"))
        conn.execute(text('ALTER TABLE tools ALTER COLUMN name TYPE varchar(255) COLLATE insensitive'))
    seed(pg)
    with engine.begin() as conn:
        conn.execute(text("UPDATE tools SET name='datetimetool' WHERE id=266"))
        plan=migration.audit(conn)
        assert any('Collation-equal' in error for error in plan['blockers'])
        assert any(row['collisdeterministic'] is False for row in plan['diagnostics']['column_collations'])


@pytest.mark.parametrize('kind',['view','trigger'])
def test_unreviewed_view_or_trigger_blocks_repair(pg,kind):
    seed(pg);engine,*_=pg
    with engine.begin() as conn:
        if kind=='view':
            conn.execute(text('CREATE VIEW clock_view AS SELECT id FROM tools WHERE id=266'))
        else:
            conn.execute(text('CREATE FUNCTION prevent_delete() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN OLD; END $$'))
            conn.execute(text('CREATE TRIGGER custom_delete BEFORE DELETE ON tools FOR EACH ROW EXECUTE FUNCTION prevent_delete()'))
        assert migration.audit(conn)['blockers']


def test_cli_dry_run_apply_replay_and_validation_have_auditable_outputs(pg,tmp_path):
    seed(pg);engine,*_=pg
    env={**os.environ,'SERVIO_BUILTIN_MIGRATION_URL':engine.url.render_as_string(hide_password=False)}
    root=Path(__file__).resolve().parents[1]
    def command(mode,*args):
        return subprocess.run([sys.executable,'-m','migrations.builtin_duplicates',mode,
            '--expected-database',engine.url.database,*map(str,args)],cwd=root,env=env,capture_output=True,text=True,timeout=40)
    plan=tmp_path/'plan.json';backup=tmp_path/'backup.json'
    with engine.begin() as conn:before=migration.snapshot(conn,'public')
    assert command('dry-run','--output',plan).returncode==0
    with engine.begin() as conn:assert before==migration.snapshot(conn,'public')
    assert command('apply','--plan',plan,'--backup',backup).stdout.strip()=='applied'
    assert command('apply','--plan',plan,'--backup',tmp_path/'unused.json').stdout.strip()=='already_applied'
    failed=tmp_path/'validation-before-index.json'
    assert command('validate','--output',failed).returncode==1
    assert not json.loads(failed.read_text())['diagnostics']['name_uniqueness_enforced']
    with engine.begin() as conn:
        conn.execute(text('DROP INDEX tools_name_key'))
        conn.execute(text('ALTER TABLE tools ADD CONSTRAINT tools_name_key UNIQUE(name)'))
    assert command('validate','--output',tmp_path/'validated.json').returncode==0
    wrong=subprocess.run([sys.executable,'-m','migrations.builtin_duplicates','dry-run','--expected-database','wrong_db'],cwd=root,env=env,capture_output=True,text=True)
    assert wrong.returncode!=0


def test_workflow_refuses_cross_scope_aliases_even_if_both_are_visible(pg):
    seed(pg);_,get_db,_,workflow=pg
    with get_db() as db:db.get(Tool,266).visibility='global'
    with pytest.raises(ValueError,match='Conflicting builtin visibility'):
        workflow.get_snapshot(11)


def test_reviewed_canonical_override_and_invalid_member(pg,tmp_path):
    seed(pg);engine,*_=pg
    with engine.begin() as conn:
        assert migration.audit(conn,canonical={'DateTimeTool':999})['blockers']
        plan=migration.audit(conn,canonical={'DateTimeTool':266,'WebSearchTool':267})
        assert plan['mapping']=={'1':266,'2':267} and not plan['blockers']
    with engine.begin() as conn:
        assert migration.apply(conn,plan,tmp_path/'override.json')=='applied'
        assert {row['id'] for row in migration.snapshot(conn,'public')['tools']}=={266,267}


def test_inbound_link_dependency_blocks_cascade_data_loss(pg,tmp_path):
    seed(pg);engine,*_=pg
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE link_notes (agent_id integer, tool_id integer, FOREIGN KEY(agent_id,tool_id) REFERENCES agent_tools(agent_id,tool_id) ON DELETE CASCADE)'))
        conn.execute(text('INSERT INTO link_notes VALUES(21,1)'))
        plan=migration.audit(conn)
        assert any('rewritten link table' in blocker for blocker in plan['blockers'])
    with pytest.raises(ValueError,match='Unsafe migration plan'):
        with engine.begin() as conn:migration.apply(conn,plan,tmp_path/'blocked.json')
    with engine.begin() as conn:
        assert conn.execute(text('SELECT count(*) FROM link_notes')).scalar()==1
        assert len(migration.snapshot(conn,'public')['tools'])==4


def test_expression_composite_index_is_not_name_uniqueness(pg,tmp_path):
    seed(pg);engine,*_=pg
    with engine.begin() as conn:plan=migration.audit(conn)
    with engine.begin() as conn:migration.apply(conn,plan,tmp_path/'clean.json')
    with engine.begin() as conn:
        conn.execute(text('DROP INDEX tools_name_key'))
        conn.execute(text('CREATE UNIQUE INDEX tools_name_key ON tools(name,(id % 2))'))
        assert not migration.diagnostics(conn,'public')['name_uniqueness_enforced']
