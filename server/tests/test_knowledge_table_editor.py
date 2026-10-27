"""Editable workbook behavior with actual SQLite, source revisions and HTTP permissions."""
import copy
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text

from app import knowledge_table_editor as editor, okf_service
from app.auth import create_access_token
from app.orm_models import OKFBundle, TeamToolAssignment, Tool
from test_knowledge_images import store
from test_knowledge_tables import xlsx


@pytest.fixture
def workbook(store, tmp_path, monkeypatch):
    service, get_db = store
    monkeypatch.setenv('LOCAL_KNOWLEDGE_IMAGES_ENABLED', 'false')
    monkeypatch.setenv('LOCAL_KNOWLEDGE_AUDIO_ENABLED', 'false')
    path = tmp_path / 'ยอดขาย.csv'
    path.write_text('รหัส,สินค้า,จำนวน,ราคา\n001,โต๊ะ,2,1500\n002,เก้าอี้,3,500\n', encoding='utf-8-sig')
    policy = tmp_path / 'policy.txt'
    policy.write_text('รับประกันสิบปี', encoding='utf-8')
    bundle = service.import_knowledge_files([path, policy], 'Sales', 1, 'team', None, queryable=True)
    with get_db() as db:
        db.add(Tool(id=99, name='sales', type='okf_knowledge_graph', config={'okf_bundle_id': bundle['id']}, owner_team_agent_id=1, visibility='team'))
        db.add(TeamToolAssignment(team_agent_id=2, tool_id=99, relationship='shared_in'))
    return service, get_db, bundle['id'], path


def snapshot(workbook):
    service, _, bundle, _ = workbook
    return service.editable_tables(bundle, 1)


def request_for(snapshot, **changes):
    return editor.SaveEditableWorkbook(expected_revision=snapshot['revision'], tables=changes.get('tables', snapshot['tables']))


def source_path(workbook):
    _, get_db, bundle, _ = workbook
    with get_db() as db:
        return Path(db.get(OKFBundle, bundle).storage_path)


def test_snapshot_preserves_thai_and_identifier_and_scope(workbook):
    service, _, bundle, _ = workbook
    data = snapshot(workbook)
    assert len(data['revision']) == 64
    assert data['tables'] == [{'table_name':'data_1', 'name':'ยอดขาย', 'columns':['รหัส','สินค้า','จำนวน','ราคา'],
                               'rows':[['001','โต๊ะ','2','1500'],['002','เก้าอี้','3','500']]}]
    assert service.editable_tables(bundle, 2) == data
    with pytest.raises(KeyError):
        service.editable_tables(bundle, 99)
    with pytest.raises(PermissionError):
        service.save_editable_tables(bundle, 2, request_for(data))


def test_save_updates_sql_lexical_and_canonical_sources_and_preserves_mixed_docs(workbook):
    service, _, bundle, _ = workbook
    old_source = source_path(workbook)
    data = snapshot(workbook)
    data['tables'][0]['rows'][0][2] = '5'
    result = service.save_editable_tables(bundle, 1, request_for(data))
    assert result['revision'] != data['revision']
    assert old_source.exists()
    assert source_path(workbook) != old_source
    assert service.query_tables(bundle, 'SELECT SUM("จำนวน"*"ราคา") FROM data_1', 1)['rows'] == [[9000]]
    assert '5' in service.query_bundle(bundle, 'โต๊ะ', 1)['response']
    assert 'สิบปี' in service.query_bundle(bundle, 'รับประกัน', 1)['response']
    root = source_path(workbook)
    assert (root/'table_sources/1.csv').exists()
    assert '5' in (root/'table_sources/1.csv').read_text(encoding='utf-8-sig')
    service.reindex_bundle(bundle, 1)
    assert service.query_tables(bundle, 'SELECT SUM("จำนวน"*"ราคา") FROM data_1', 1)['rows'] == [[9000]]
    assert snapshot(workbook)['tables'][0]['rows'][0][2] == '5'


def test_schema_and_table_edits_keep_stable_sql_ids_and_support_empty_tables(workbook):
    service, _, bundle, _ = workbook
    data = snapshot(workbook)
    tables = [{'table_name':'data_3', 'name':'ราคาใหม่', 'columns':['สินค้า','ราคาใหม่'], 'rows':[['โต๊ะ','100']]},
              {'table_name':'data_1', 'name':'ว่าง', 'columns':['รหัส'], 'rows':[]}]
    result = service.save_editable_tables(bundle, 1, request_for(data, tables=tables))
    assert [table['table_name'] for table in result['tables']] == ['data_3','data_1']
    assert service.query_tables(bundle, 'SELECT COUNT(*) FROM data_1', 1)['rows'] == [[0]]
    assert service.query_tables(bundle, 'SELECT "ราคาใหม่" FROM data_3', 1)['rows'] == [[100]]
    result = service.save_editable_tables(bundle, 1, request_for(result, tables=tables[:1]))
    assert len(result['tables']) == 1
    assert [table['table_name'] for table in service.table_inventory(bundle, 1)] == ['data_3']


def test_stale_save_rejected_without_removing_winning_revision(workbook):
    service, _, bundle, _ = workbook
    first = snapshot(workbook)
    second = copy.deepcopy(first)
    first['tables'][0]['rows'][0][2] = '4'
    service.save_editable_tables(bundle, 1, request_for(first))
    winner = source_path(workbook)
    with pytest.raises(editor.TableRevisionConflict):
        service.save_editable_tables(bundle, 1, request_for(second))
    assert source_path(workbook) == winner
    assert service.query_tables(bundle, 'SELECT "จำนวน" FROM data_1 ORDER BY rowid', 1)['rows'][0] == [4]
    assert len(list((service.storage_root/str(bundle)/'source-revisions').iterdir())) == 1


def test_failure_after_staging_rolls_back_data_index_and_pointer(workbook, monkeypatch):
    service, _, bundle, _ = workbook
    initial = snapshot(workbook)
    root = source_path(workbook)
    def broken(*args):
        raise RuntimeError('simulated index write failure')
    monkeypatch.setattr(service, '_replace_index', broken)
    with pytest.raises(RuntimeError):
        service.save_editable_tables(bundle, 1, request_for(initial))
    assert source_path(workbook) == root
    assert snapshot(workbook) == initial
    assert not list((service.storage_root/str(bundle)/'source-revisions').iterdir())
    assert service.query_tables(bundle, 'SELECT COUNT(*) FROM data_1', 1)['rows'] == [[2]]


def test_second_revision_check_rejects_concurrent_writer_and_cleans_staging(workbook, monkeypatch):
    service, get_db, bundle, _ = workbook
    initial = snapshot(workbook)
    original = editor.write_drafts
    def racing(*args):
        result = original(*args)
        with get_db() as db:
            row = db.get(OKFBundle, bundle)
            from datetime import timedelta
            row.updated_at += timedelta(seconds=1)
        return result
    monkeypatch.setattr(editor, 'write_drafts', racing)
    with pytest.raises(editor.TableRevisionConflict):
        service.save_editable_tables(bundle, 1, request_for(initial))
    assert not list((service.storage_root/str(bundle)/'source-revisions').iterdir())


def test_save_invalidates_existing_text_vectors_transactionally(workbook):
    service, get_db, bundle, _ = workbook
    with get_db() as db:
        db.execute(text('CREATE TABLE okf_rag_chunks (bundle_id INTEGER, content TEXT)'))
        db.execute(text("INSERT INTO okf_rag_chunks VALUES (:bundle, 'old table value'), (999, 'unrelated')"), {'bundle':bundle})
    service.save_editable_tables(bundle, 1, request_for(snapshot(workbook)))
    with get_db() as db:
        assert db.execute(text('SELECT bundle_id FROM okf_rag_chunks')).all() == [(999,)]


def test_delete_removes_all_revisions(workbook):
    service, _, bundle, _ = workbook
    for _ in range(2):
        service.save_editable_tables(bundle, 1, request_for(snapshot(workbook)))
    assert service.delete_bundle(bundle, 1)
    assert not (service.storage_root/str(bundle)).exists()


def test_import_drafts_reads_xlsx_multiple_sheets_and_csv_without_creating_bundle(tmp_path):
    book = xlsx(tmp_path/'products.xlsx', {
        'สินค้า': '<row><c r="A1" t="inlineStr"><is><t>ชื่อ</t></is></c><c r="B1" t="inlineStr"><is><t>ราคา</t></is></c></row><row><c r="A2" t="inlineStr"><is><t>โต๊ะ</t></is></c><c r="B2"><v>120</v></c></row>',
        'คลัง': '<row><c r="A1" t="inlineStr"><is><t>จำนวน</t></is></c></row><row><c r="A2"><v>4</v></c></row>'})
    result = editor.import_drafts([book])
    assert [table.name for table in result.tables] == ['สินค้า','คลัง']
    assert result.tables[0].rows == [['โต๊ะ','120']]
    assert not list(tmp_path.rglob('queryable.sqlite'))


@pytest.mark.parametrize('tables', [[], [{'table_name':'bad;DROP','name':'A','columns':['x'],'rows':[]}],
    [{'table_name':'data_1','name':'A','columns':['x','X'],'rows':[]}],
    [{'table_name':'data_1','name':'A','columns':['x'],'rows':[['1','2']]}],
    [{'table_name':'data_1','name':'A','columns':['x'],'rows':[['x\x00']]}],
    [{'table_name':'data_1','name':'A','columns':[''],'rows':[]}],
    [{'table_name':'data_1','name':' ','columns':['x'],'rows':[]}],
    [{'table_name':'data_1','name':'A','columns':['x'],'rows':[[123]]}]])
def test_invalid_workbook_never_constructs(tables):
    with pytest.raises(ValidationError):
        editor.EditableWorkbook(tables=tables)


@pytest.fixture
def api(workbook, monkeypatch):
    service, get_db, _, _ = workbook
    with patch('app.db_config.init_database'):
        from app import admin_routes as routes
    roles = {('owner',1):'admin',('viewer',1):'viewer',('other',2):'admin'}
    monkeypatch.setattr(routes, 'OKFService', lambda: service)
    monkeypatch.setattr(routes, 'get_db', get_db)
    monkeypatch.setattr(routes.database, 'get_default_team_id', lambda: 1)
    monkeypatch.setattr(routes.database, 'get_admin_by_username', lambda user: {'is_super_admin':user=='super'})
    monkeypatch.setattr(routes.database, 'has_team_access', lambda user, team, role='viewer': user=='super' or roles.get((user,team))=='admin' or (roles.get((user,team))=='viewer' and role=='viewer'))
    app = FastAPI();app.include_router(routes.router)
    return TestClient(app)


def headers(user):
    return {'Authorization':'Bearer '+create_access_token({'sub':user})}


def test_http_read_write_permissions_and_stale_409(api, workbook):
    _, _, bundle, _ = workbook
    path=f'/api/admin/okf-bundles/{bundle}/tables'
    owner=api.get(path, headers=headers('owner')).json()
    assert owner['can_edit'] is True
    assert api.get(path, headers=headers('viewer')).json()['can_edit'] is False
    assert api.get(path, headers=headers('other'), params={'team_agent_id':2}).json()['can_edit'] is False
    body={'expected_revision':owner['revision'],'tables':owner['tables']}
    assert api.put(path,headers=headers('viewer'),json=body).status_code==403
    assert api.put(path,headers=headers('other'),params={'team_agent_id':2},json=body).status_code==403
    assert api.put(path,headers=headers('owner'),json=body).status_code==200
    assert api.put(path,headers=headers('owner'),json=body).status_code==409
    fresh=api.get(path,headers=headers('super'),params={'team_agent_id':2}).json()
    assert fresh['can_edit'] is True
    assert api.put(path,headers=headers('super'),params={'team_agent_id':2},json={'expected_revision':fresh['revision'],'tables':fresh['tables']}).status_code==200


def test_import_endpoint_permissions_and_validation(api):
    path='/api/admin/okf-bundles/table-drafts/import'
    files={'files':('test.csv','ชื่อ,ราคา\nโต๊ะ,10\n'.encode('utf-8'),'text/csv')}
    assert api.post(path,headers=headers('viewer'),files=files).status_code==403
    response=api.post(path,headers=headers('owner'),files=files)
    assert response.status_code==200,response.text
    assert response.json()['tables'][0]['rows']==[['โต๊ะ','10']]
    assert api.post(path,headers=headers('owner'),files={'files':('test.txt',b'text','text/plain')}).status_code==400


def test_http_body_bounded_before_json_parse(api, workbook, monkeypatch):
    from app import admin_routes as routes
    monkeypatch.setattr(routes,'MAX_ARCHIVE_BYTES',8)
    response=api.put(f'/api/admin/okf-bundles/{workbook[2]}/tables',headers=headers('owner'),content=b' '*9)
    assert response.status_code==413


def test_schema_signature_rejects_stale_quoted_columns_before_sql(workbook):
    from app.knowledge_tables import TableImportError, schema_signature
    service, _, bundle, _ = workbook
    signature = schema_signature(service.table_inventory(bundle, 1))
    data = snapshot(workbook)
    data['tables'][0]['rows'][0][2] = '4'
    first = service.save_editable_tables(bundle, 1, request_for(data))
    assert service.query_tables(bundle, 'SELECT SUM("จำนวน"*"ราคา") FROM data_1', 1, expected_schema=signature)['rows'] == [[7500]]
    first['tables'][0]['columns'][3] = 'ราคาขาย'
    service.save_editable_tables(bundle, 1, request_for(first))
    with pytest.raises(TableImportError, match='sql=SCHEMA'):
        service.query_tables(bundle, 'SELECT SUM("จำนวน"*"ราคา") FROM data_1', 1, expected_schema=signature)
    refreshed = schema_signature(service.table_inventory(bundle, 1))
    assert service.query_tables(bundle, 'SELECT SUM("จำนวน"*"ราคาขาย") FROM data_1', 1, expected_schema=refreshed)['rows'] == [[7500]]


def test_ambiguous_commit_failure_never_deletes_referenced_revision(workbook, monkeypatch):
    from sqlalchemy.orm import Session
    service, _, bundle, _ = workbook
    initial = snapshot(workbook)
    initial['tables'][0]['rows'][0][2] = '4'
    original_commit = Session.commit
    failed = False
    def uncertain_commit(session):
        nonlocal failed
        current = session.get(OKFBundle, bundle)
        should_fail = not failed and current is not None and 'source-revisions' in current.storage_path
        original_commit(session)
        if should_fail:
            failed = True
            raise RuntimeError('connection lost after server commit')
    monkeypatch.setattr(Session, 'commit', uncertain_commit)
    with pytest.raises(RuntimeError):
        service.save_editable_tables(bundle, 1, request_for(initial))
    assert source_path(workbook).exists()
    assert service.query_tables(bundle, 'SELECT "จำนวน" FROM data_1 ORDER BY rowid', 1)['rows'][0] == [4]


def test_table_text_edit_cannot_diverge_from_sql_before_or_after_grid_save(workbook):
    service, _, bundle, _ = workbook
    for saved in (False, True):
        if saved:
            service.save_editable_tables(bundle, 1, request_for(snapshot(workbook)))
        concept = next(item for item in service.list_concepts(bundle, 1) if item['resource'].endswith('.csv'))
        with pytest.raises(okf_service.OKFValidationError, match='Tables tab'):
            service.update_concept(bundle, concept['concept_id'], 1, title=None, description=None, tags=None, body='incorrect price 99999')
    assert service.query_tables(bundle, 'SELECT SUM("จำนวน"*"ราคา") FROM data_1', 1)['rows'] == [[4500]]


def test_table_display_names_do_not_become_filesystem_paths(workbook):
    service, _, bundle, _ = workbook
    data = snapshot(workbook)
    data['tables'][0]['name'] = 'สินค้า/ราคา'
    saved = service.save_editable_tables(bundle, 1, request_for(data))
    assert saved['tables'][0]['name'] == 'สินค้า/ราคา'
    assert snapshot(workbook)['tables'][0]['name'] == 'สินค้า/ราคา'
    assert service.query_tables(bundle, 'SELECT COUNT(*) FROM data_1', 1)['rows'] == [[2]]
