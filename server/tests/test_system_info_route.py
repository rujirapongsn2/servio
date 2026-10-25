from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

with patch('app.db_config.init_database'):
    from app import admin_routes, system_monitor
from app.auth import create_access_token


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(admin_routes.database, 'get_admin_by_username', lambda name: {'username': name, 'is_super_admin': False})
    calls = []

    def access(username, team_id, role):
        calls.append((username, team_id, role))
        if team_id == 9:
            raise HTTPException(403, 'Not allowed')

    monkeypatch.setattr(admin_routes, 'require_team_access', access)
    check = AsyncMock(return_value={
        'services': [system_monitor.row('postgresql', 'PostgreSQL', 'unavailable')],
        'checked_at': '2026-10-25T00:00:00Z', 'agents_count': None, 'tools_count': None,
    })
    monkeypatch.setattr(system_monitor, 'monitor', check)
    monkeypatch.setattr(admin_routes.database, 'get_all_agents', lambda: pytest.fail('legacy unbounded query'))
    monkeypatch.setattr(admin_routes.database, 'get_all_tools', lambda **kwargs: pytest.fail('legacy unbounded query'))
    app = FastAPI()
    app.include_router(admin_routes.router)
    with TestClient(app) as client:
        yield client, check, calls


def test_system_info_requires_authentication_and_team_access(client):
    client, check, calls = client
    assert client.get('/api/admin/system-info').status_code in {401, 403}
    check.assert_not_awaited()
    headers = {'Authorization': 'Bearer ' + create_access_token({'sub': 'viewer'})}
    assert client.get('/api/admin/system-info?team_agent_id=9', headers=headers).status_code == 403
    check.assert_not_awaited()
    response = client.get('/api/admin/system-info?team_agent_id=1', headers=headers)
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'private, no-store'
    payload = response.json()
    assert payload['agents_count'] is None and payload['tools_count'] is None
    assert payload['services'][0]['status'] == 'unavailable'
    assert payload['python_version'] and payload['server_time']
    assert calls[-1] == ('viewer', 1, 'viewer')
    check.assert_awaited_once_with(1)
