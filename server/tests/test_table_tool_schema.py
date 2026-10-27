"""An existing Agent must refresh schema after columns are renamed in the grid."""
import json

from app import agent_config
from app.knowledge_table_editor import SaveEditableWorkbook
from test_knowledge_images import store
from test_queryable_knowledge import tabular, upload, invoke


def test_existing_agent_rejects_stale_quoted_column_until_schema_refresh(tabular):
    service, _, _ = tabular
    bundle = upload(tabular, queryable=True)
    tool = agent_config.create_okf_knowledge_graph_tool('sales', {'okf_bundle_id': bundle['id'], 'queryable': True}, runtime_team_agent_id=1)
    draft = service.editable_tables(bundle['id'], 1)
    draft['tables'][0]['columns'][3] = 'ราคาขาย'
    service.save_editable_tables(bundle['id'], 1, SaveEditableWorkbook(expected_revision=draft['revision'], tables=draft['tables']))
    # SQLite would otherwise treat the obsolete double-quoted name as a string.
    rejected = invoke(tool, query='ยอดรวม', sql='SELECT SUM("จำนวน" * "ราคา") FROM data_1')
    assert 'SCHEMA' in rejected and 'schema changed' in rejected
    refreshed = json.loads(invoke(tool, query='', sql='SCHEMA'))
    assert refreshed['tables'][0]['columns'][3]['name'] == 'ราคาขาย'
    assert json.loads(invoke(tool, query='', sql='SELECT SUM("จำนวน" * "ราคาขาย") FROM data_1'))['rows'] == [[6000]]


def test_existing_agent_reads_new_values_without_unnecessary_schema_refresh(tabular):
    service, _, _ = tabular
    bundle = upload(tabular, queryable=True)
    tool = agent_config.create_okf_knowledge_graph_tool('sales', {'okf_bundle_id': bundle['id'], 'queryable': True}, runtime_team_agent_id=1)
    draft = service.editable_tables(bundle['id'], 1)
    draft['tables'][0]['rows'][0][2] = '10'
    service.save_editable_tables(bundle['id'], 1, SaveEditableWorkbook(expected_revision=draft['revision'], tables=draft['tables']))
    assert json.loads(invoke(tool, query='', sql='SELECT SUM("จำนวน" * "ราคา") FROM data_1'))['rows'] == [[18000]]
