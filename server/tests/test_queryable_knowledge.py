"""Queryable Knowledge lifecycle, HTTP imports and actual Agent tool execution."""
import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from agents import RunContextWrapper
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import agent_config, okf_service
from app.orm_models import OKFBundle, TeamToolAssignment, Tool
from test_knowledge_images import store


@pytest.fixture
def tabular(store, tmp_path, monkeypatch):
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGES_ENABLED', 'false')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_AUDIO_ENABLED', 'false')
    path = tmp_path / 'ยอดขาย.csv'
    path.write_text('รหัส,สินค้า,จำนวน,ราคา\n001,โต๊ะ,2,1500\n002,เก้าอี้,3,500\n003,โต๊ะ,1,1500\n', encoding='utf-8-sig')
    return store[0], store[1], path


def upload(tabular, **kwargs):
    service, _, path = tabular
    return service.import_knowledge_files([path], 'ยอดขาย', 1, 'team', None, **kwargs)


def invoke(tool, **args):
    return asyncio.run(tool.on_invoke_tool(RunContextWrapper(context=None), json.dumps(args, ensure_ascii=False)))


def test_default_import_retains_text_search_without_database(tabular):
    service, _, _ = tabular
    bundle = upload(tabular)
    assert not bundle['validation_summary'].get('queryable')
    assert not (service.storage_root / str(bundle['id']) / 'source/queryable.sqlite').exists()
    assert 'โต๊ะ' in service.query_bundle(bundle['id'], 'โต๊ะ', 1)['response']
    tool = agent_config.create_okf_knowledge_graph_tool('sales', {'okf_bundle_id': bundle['id']}, runtime_team_agent_id=1)
    assert set(tool.params_json_schema['properties']) == {'query'}


def test_preview_import_agent_query_uses_complete_rows_and_thai_columns(tabular):
    service, _, path = tabular
    preview = service.preview_knowledge_files([path], 1, queryable=True)
    assert preview['tables'][0]['row_count'] == 3
    assert preview['tables'][0]['columns'][0] == {'name': 'รหัส', 'type': 'TEXT'}
    bundle = upload(tabular, queryable=True)
    tool = agent_config.create_okf_knowledge_graph_tool('sales', {
        'okf_bundle_id': bundle['id'], 'queryable': True, 'team_agent_id': 99,
    }, runtime_team_agent_id=1)
    assert set(tool.params_json_schema['properties']) == {'query', 'sql'}
    assert 'ยอดขาย.csv' in tool.description
    assert 'จำนวน' in tool.description
    assert json.loads(invoke(tool, query='ยอดขายรวม', sql='SELECT SUM("จำนวน" * "ราคา") AS total FROM data_1'))['rows'] == [[6000]]
    result = json.loads(invoke(tool, query='สรุปสินค้า', sql='SELECT "สินค้า", SUM("จำนวน") FROM data_1 GROUP BY "สินค้า" ORDER BY 1'))
    assert sorted(result['rows']) == sorted([['โต๊ะ', 3], ['เก้าอี้', 3]])
    assert result['source'] == 'ยอดขาย'
    assert json.loads(invoke(tool, query='', sql='SCHEMA'))['tables'][0]['row_count'] == 3
    assert 'โต๊ะ' in invoke(tool, query='โต๊ะ', sql='')


def test_excel_worksheets_can_be_joined_for_calculation_with_mixed_documents(tabular, tmp_path):
    from test_knowledge_tables import xlsx
    service, _, _ = tabular
    book = xlsx(tmp_path / 'sales.xlsx', {
        'orders': '<row><c r="A1" t="inlineStr"><is><t>code</t></is></c><c r="B1" t="inlineStr"><is><t>qty</t></is></c></row><row><c r="A2"><v>1</v></c><c r="B2"><v>3</v></c></row>',
        'products': '<row><c r="A1" t="inlineStr"><is><t>code</t></is></c><c r="B1" t="inlineStr"><is><t>price</t></is></c></row><row><c r="A2"><v>1</v></c><c r="B2"><v>125</v></c></row>',
    })
    policy = tmp_path / 'policy.txt'
    policy.write_text('คืนสินค้าได้ภายในเจ็ดวัน', encoding='utf-8')
    bundle = service.import_knowledge_files([book, policy], 'Sales and policy', 1, 'team', None, queryable=True)
    catalog = service.table_inventory(bundle['id'], 1)
    assert [table['sheet_name'] for table in catalog] == ['orders', 'products']
    assert service.query_tables(bundle['id'], 'SELECT SUM(a.qty*b.price) FROM data_1 a JOIN data_2 b ON a.code=b.code', 1)['rows'] == [[375]]
    assert 'เจ็ดวัน' in service.query_bundle(bundle['id'], 'คืนสินค้า', 1)['response']


def test_queries_recheck_runtime_team_and_revoked_shares(tabular):
    service, get_db, _ = tabular
    bundle = upload(tabular, queryable=True)
    config = {'type': 'okf_knowledge_graph', 'okf_bundle_id': bundle['id'], 'queryable': True, 'team_agent_id': 1}
    with pytest.raises(KeyError):
        service.query_tables(bundle['id'], 'SELECT * FROM data_1', 2)
    with pytest.raises(KeyError):
        service.query_tables(bundle['id'], 'SELECT * FROM data_1', None)
    with get_db() as db:
        db.add(Tool(id=100, name='sales', type='okf_knowledge_graph', config=config, owner_team_agent_id=1, visibility='team'))
        db.add(TeamToolAssignment(team_agent_id=2, tool_id=100, relationship='shared_in'))
    tool = agent_config.create_okf_knowledge_graph_tool('sales', config, runtime_team_agent_id=2)
    assert json.loads(invoke(tool, query='', sql='SELECT COUNT(*) FROM data_1'))['rows'] == [[3]]
    with get_db() as db:
        db.query(TeamToolAssignment).filter_by(team_agent_id=2).delete()
    denied = invoke(tool, query='', sql='SELECT SUM("จำนวน" * "ราคา") FROM data_1')
    assert '6000' not in denied and 'unavailable' in denied
    assert 'ยอดขาย.csv' not in invoke(tool, query='', sql='SCHEMA')


def test_reindex_preserves_queryable_artifacts_and_delete_removes_them(tabular):
    service, _, path = tabular
    bundle = upload(tabular, queryable=True)
    root = service.storage_root / str(bundle['id']) / 'source'
    originals = list((root / 'table_sources').iterdir())
    assert len(originals) == 1 and originals[0].read_bytes() == path.read_bytes()
    before = (root / 'queryable.sqlite').read_bytes()
    reindexed = service.reindex_bundle(bundle['id'], 1)
    assert reindexed['validation_summary']['queryable'] is True
    assert (root / 'queryable.sqlite').read_bytes() == before
    assert service.query_tables(bundle['id'], 'SELECT COUNT(*) FROM data_1', 1)['rows'] == [[3]]
    assert service.delete_bundle(bundle['id'], 1)
    assert not root.exists()
    with pytest.raises(KeyError):
        service.query_tables(bundle['id'], 'SELECT * FROM data_1', 1)


def test_failed_queryable_import_never_creates_ready_bundle(tabular):
    service, get_db, path = tabular
    path.write_text('商品,個数\nA,1,extra\n', encoding='utf-8')
    with pytest.raises(okf_service.OKFValidationError):
        upload(tabular, queryable=True)
    with get_db() as db:
        assert db.query(OKFBundle).count() == 0
    assert not list(service.storage_root.glob('*/source/queryable.sqlite'))


@pytest.fixture
def api(tabular, monkeypatch):
    service, get_db, _ = tabular
    with patch('app.db_config.init_database'):
        from app import admin_routes as routes
    monkeypatch.setattr(routes, 'OKFService', lambda: service)
    monkeypatch.setattr(routes, 'get_db', get_db)
    monkeypatch.setattr(routes, '_require_resolved_team_access', lambda *args: 1)
    monkeypatch.setattr(routes.database, 'get_admin_by_username', lambda user: None)
    monkeypatch.setattr(routes.database, 'create_custom_tool', lambda *args, **kwargs: 123)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[routes.get_current_user] = lambda: 'owner'
    yield TestClient(app), routes


@pytest.mark.parametrize('endpoint', ['/preview', '', '/import-jobs'])
def test_http_queryable_flag_reaches_preview_and_both_import_paths(api, tabular, endpoint):
    client, _ = api
    service, _, path = tabular
    response = client.post('/api/admin/okf-bundles' + endpoint,
        data={'display_name': 'ยอดขาย', 'queryable': 'true', 'create_tool': 'true'},
        files={'files': (path.name, path.read_bytes(), 'text/csv')})
    assert response.status_code == 200, response.text
    body = response.json()
    if endpoint == '/preview':
        assert body['tables'][0]['row_count'] == 3
        assert not list(service.storage_root.glob('*/source/queryable.sqlite'))
        return
    if endpoint == '/import-jobs':
        body = client.get('/api/admin/okf-bundles/import-jobs/' + body['job_id']).json()
        assert body['status'] == 'succeeded', body
        body = body['bundle']
    assert body['validation_summary']['queryable'] is True
    assert service.query_tables(body['id'], 'SELECT SUM("จำนวน"*"ราคา") FROM data_1', 1)['rows'] == [[6000]]


def test_created_capability_marks_queryable_only_when_opted_in(api):
    _, routes = api
    captured = []
    with patch.object(routes.database, 'create_custom_tool', side_effect=lambda name, config, **kwargs: captured.append(config) or 123):
        for summary in ({}, {'queryable': True}):
            routes._create_okf_tool_for_bundle({'id': 1, 'validation_summary': summary}, 'sales', 1, 'team', 'owner', None)
    assert [item['queryable'] for item in captured] == [False, True]


@pytest.mark.parametrize('endpoint', ['/preview', '', '/import-jobs'])
@pytest.mark.parametrize('mode', ['archive', 'urls', 'knowledge'])
def test_http_rejects_queryable_without_direct_table_upload(api, endpoint, mode):
    client, _ = api
    response = client.post('/api/admin/okf-bundles' + endpoint,
        data={'display_name': 'test', 'import_mode': mode, 'queryable': 'true', 'pasted_text': 'plain text'})
    assert response.status_code == 400


def test_duplicate_queryable_filenames_cannot_silently_replace_input(api):
    client, _ = api
    response = client.post('/api/admin/okf-bundles/preview', data={'queryable': 'true'}, files=[
        ('files', ('same.csv', b'a,b\n1,2')), ('files', ('same.csv', b'a,b\n3,4'))])
    assert response.status_code == 400
    assert 'unique' in response.text
