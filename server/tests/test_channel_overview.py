from contextlib import contextmanager
from datetime import datetime, timedelta
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import channel_overview as overview
from app.orm_models import Base, TeamAgent, ApiKey, ChannelConfig


@pytest.fixture
def inventory(monkeypatch):
    from app import db_config
    with monkeypatch.context() as imports:
        imports.setattr(db_config, "init_database", lambda: None)
        from app import database
    engine = create_engine('sqlite:///:memory:', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    @contextmanager
    def get_db():
        with sessions.begin() as db:
            yield db
    monkeypatch.setattr(overview, 'get_db', get_db)
    monkeypatch.setattr(database, 'get_all_team_agents', lambda username: [dict(id=1,name='Tak',status='active')])
    monkeypatch.setattr(database, 'get_admin_by_username', lambda name: {'is_super_admin': name == 'root'})
    monkeypatch.setattr(database, 'has_team_access', lambda name, team, role: name != 'viewer')
    with get_db() as db:
        db.add_all([TeamAgent(id=1,name='Tak',slug='tak'),TeamAgent(id=2,name='Private',slug='private')])
        db.flush()
        db.add_all([ApiKey(id=1,name='Web',key='secret-key',team_agent_id=1,channel_type='web_widget',slug='tak-chat'),
                    ApiKey(id=2,name='Expired',key='expired-secret',team_agent_id=1,expires_at=datetime.utcnow()-timedelta(days=1)),
                    ApiKey(id=3,name='Forbidden',key='private-key',team_agent_id=2),
                    ApiKey(id=4,name='Legacy',key='legacy-key',team_agent_id=None),
                    ChannelConfig(id=1,name='LINE',type='line',team_agent_id=1,is_active=True,
                                  config={'channel_id':'123','channel_secret':'sensitive-secret','channel_access_token':'sensitive-token'}),
                    ChannelConfig(id=2,name='Empty default',type='facebook',team_agent_id=1,config={'webhook_url':'/api/public/webhook'})])
    yield get_db
    engine.dispose()


def test_inventory_is_scoped_read_only_and_contains_no_credentials(inventory):
    result = overview.channel_overview('admin')
    assert {r['name'] for r in result} == {'Web','Expired','LINE'}
    serialized = json.dumps(result)
    for secret in ['secret-key','expired-secret','private-key','legacy-key','sensitive-secret','sensitive-token']:
        assert secret not in serialized
    with inventory() as db:
        assert db.query(ChannelConfig).count() == 2
    line = next(r for r in result if r['kind']=='messaging')
    assert line['status']=='active' and line['identifier']=='123'
    assert next(r for r in result if r['name']=='Expired')['status']=='expired'


def test_viewers_cannot_edit_and_missing_credentials_are_not_enabled(inventory):
    with inventory() as db:
        db.get(ChannelConfig,1).config={'channel_id':'123'}
    result = overview.channel_overview('viewer')
    assert all(not r['can_edit'] for r in result)
    assert next(r for r in result if r['kind']=='messaging')['status']=='incomplete'


def test_only_super_admin_sees_legacy_unassigned_channels(inventory):
    assert 'Legacy' in {r['name'] for r in overview.channel_overview('root')}
    assert 'Legacy' not in {r['name'] for r in overview.channel_overview('admin')}


def test_no_team_access_returns_no_inventory(inventory,monkeypatch):
    from app import database
    monkeypatch.setattr(database,'get_all_team_agents',lambda username: [])
    assert overview.channel_overview('viewer') == []
